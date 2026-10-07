import json
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import logging

from app.modules.processing.period_deletion import (
    delete_period,
    deletion_preview,
    bulk_deletion_preview,
    delete_periods,
)

from app.core.errors import ApplicationError
from app.core.contracts import DataPage, FileRow, IssueRow, Page, Problem, RunResponse, TableRow
from app.modules.engine import ENGINE_VERSION, TABLE_NAMES, TABLE_ORDER
from app.modules.engine.models import ConsolidationRange
from app.modules.identity.auth import Principal, current_principal, require_reader
from app.modules.processing.service import (
    audit, commit_or_conflict, create_annual, create_monthly, fingerprint, get_document,
    get_run, remember, replay, reprocess, run_response, validate_key,
)
from app.modules.reporting.queries import compare_periods, data_page, overview
from app.modules.reporting.analytics import options as analytics_options, summarize as analytics_summary
from app.modules.reporting.project_maps import catalog as project_maps_catalog, image_path as project_map_image
from app.persistence.models import (
    AgentMessage, AuditEvent, Conversation, Issue, Job, OutboxMessage, Period,
    ProcessingFile, ProcessingTable, Run, StoredDocument,
)
router = APIRouter(prefix="/api/v1", responses={
    status: {"model": Problem, "description": description}
    for status, description in ((400, "Solicitud inválida"), (401, "Autenticación requerida"),
                                (403, "Permiso insuficiente"), (404, "Recurso no encontrado"),
                                (409, "Conflicto de versión o idempotencia"), (413, "Carga demasiado grande"),
                                (422, "Validación"), (503, "Servicio no disponible"))
})

def db_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session

DB = Annotated[object, Depends(db_session)]
Reader = Annotated[Principal, Depends(require_reader)]
Identity = Annotated[Principal, Depends(current_principal)]
Idempotency = Annotated[str, Header(alias="Idempotency-Key")]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SourceRef(StrictModel):
    documentId: str
    fileName: str | None = Field(default=None, max_length=512)
    periodo: str = Field(max_length=100)
    tableCode: str | None = Field(default=None, max_length=100)

class AnnualRequest(StrictModel):
    anio: int | None = Field(default=None, ge=1900, le=2100)
    rangoNombre: str | None = Field(default=None, min_length=1, max_length=100)
    startYear: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    startMonth: int | None = Field(default=None, ge=1, le=12, strict=True)
    endYear: int | None = Field(default=None, ge=1900, le=2100, strict=True)
    endMonth: int | None = Field(default=None, ge=1, le=12, strict=True)
    sourceRunIds: list[str] | None = Field(default=None, min_length=1, max_length=2412)
    files: list[SourceRef] | None = Field(default=None, min_length=1, max_length=2000)
    @model_validator(mode="after")
    def exclusive_sources(self):
        if self.sourceRunIds is not None and self.files is not None:
            raise ValueError("Selecciona versiones mensuales o archivos")
        endpoints = (self.startYear, self.startMonth, self.endYear, self.endMonth)
        if any(value is not None for value in endpoints):
            if any(value is None for value in endpoints):
                raise ValueError("Indica el año y mes inicial y el año y mes final.")
            if self.anio is not None or self.rangoNombre is not None:
                raise ValueError("No combines el rango explícito con el formato anual anterior.")
            self.period_range()
        elif self.anio is None or self.rangoNombre is None:
            raise ValueError("Indica los cuatro extremos del rango o el año y nombre del rango anual.")
        return self

    def period_range(self) -> ConsolidationRange | None:
        if self.startYear is None:
            return None
        return ConsolidationRange(self.startYear, self.startMonth, self.endYear, self.endMonth)

class ReprocessRequest(StrictModel):
    reason: str = Field(min_length=5, max_length=1000)
    expectedVersion: int = Field(ge=0)

class DeletePeriodRequest(StrictModel):
    expectedVersion: int = Field(ge=0)
    confirmation: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=1000)
    expectedMonthlyRuns: int = Field(ge=0)
    expectedAnnualRuns: int = Field(ge=0)
    expectedBusinessRows: int = Field(ge=0)
    expectedDocuments: int = Field(ge=0)

class MessageRequest(StrictModel):
    message: str = Field(min_length=1, max_length=8000)
    allowActions: bool = False
    language: Literal['es', 'en'] = 'es'

class BulkPeriodSelection(StrictModel):
    periodIds: list[str] = Field(min_length=1, max_length=24)

class BulkDeleteRequest(BulkPeriodSelection):
    expectedToken: str = Field(min_length=64, max_length=64)
    confirmation: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=1000)

def _leaf(name):
    result = PurePosixPath((name or "").replace("\\", "/")).name
    if not result or len(result) > 512:
        raise ApplicationError(400, "INVALID_FILENAME", "Nombre de archivo no válido")
    return result

def _accepted(response, run):
    response.status_code = 202
    response.headers["Location"] = f"/api/v1/runs/{run.id}"

@router.get("/config")
def config(request: Request):
    s = request.app.state.settings
    return {"environment": s.environment, "authMode": s.auth_mode,
            "entra": {"tenantId": s.entra_tenant_id, "clientId": s.entra_client_id, "apiScope": s.entra_api_scope},
            "foundryEnabled": s.foundry_enabled, "allowAgentCommands": s.allow_agent_commands, "engineVersion": ENGINE_VERSION,
            "maxUploadMb": s.max_upload_mb, "scopeId": s.scope_id}

@router.get("/me")
def me(principal: Identity):
    return {"id": principal.id, "name": principal.name, "roles": sorted(principal.roles), "scopeId": principal.scope_id}

@router.get("/catalog/tables")
def table_catalog(principal: Reader):
    return [{"code": code, "name": TABLE_NAMES[code], "order": order} for order, code in enumerate(TABLE_ORDER)]


@router.get("/project-maps")
def project_maps(request: Request, principal: Reader):
    return project_maps_catalog(principal, request.app.state.settings)


@router.get("/project-maps/{map_id}/image")
def project_map(map_id: str, request: Request, principal: Reader, thumbnail: bool = False):
    path = project_map_image(principal, request.app.state.settings, map_id, thumbnail)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-store"})

@router.get("/periods")
def periods(session: DB, principal: Reader):
    rows = session.scalars(select(Period).where(Period.scope_id == principal.scope_id).order_by(Period.year.desc(), Period.month.desc()))
    return [{"id": p.id, "year": p.year, "month": p.month, "name": p.name, "activeRunId": p.active_run_id, "version": p.version} for p in rows]

@router.get("/periods/{period_id}/deletion-preview")
def period_deletion_preview(
    period_id: str, session: DB, principal: Identity
):
    return deletion_preview(session, principal, period_id)[1]


@router.delete("/periods/{period_id}")
def remove_period(
    period_id: str,
    body: DeletePeriodRequest,
    request: Request,
    session: DB,
    principal: Identity,
):
    preview, keys = delete_period(
        session,
        principal,
        period_id,
        body.expectedVersion,
        body.confirmation,
        body.reason,
        {
            "monthlyRuns": body.expectedMonthlyRuns,
            "annualRuns": body.expectedAnnualRuns,
            "businessRows": body.expectedBusinessRows,
            "documents": body.expectedDocuments,
        },
    )
    commit_or_conflict(session)

    cleanup_failures = 0
    for key in keys:
        try:
            request.app.state.storage.resolve(key).unlink(missing_ok=True)
        except OSError:
            cleanup_failures += 1
            logging.getLogger(__name__).warning(
                "No se pudo eliminar un documento del mes"
            )

    return {
        **preview,
        "storageCleanupFailures": cleanup_failures,
    }


@router.post('/periods/bulk-deletion-preview')
def bulk_period_preview(body: BulkPeriodSelection, session: DB, principal: Identity):
    return bulk_deletion_preview(session, principal, body.periodIds)


@router.post('/periods/bulk-delete')
def remove_periods(body: BulkDeleteRequest, request: Request, session: DB, principal: Identity):
    if len(body.reason.strip()) < 8:
        raise ApplicationError(400, 'REASON_REQUIRED', 'Indica un motivo de al menos 8 caracteres')
    preview, keys = delete_periods(session, principal, body.periodIds, body.expectedToken, body.confirmation, body.reason.strip())
    commit_or_conflict(session)
    failures = 0
    for key in keys:
        try:
            request.app.state.storage.resolve(key).unlink(missing_ok=True)
        except OSError:
            failures += 1
            logging.getLogger(__name__).warning('No se pudo eliminar un documento de los meses seleccionados')
    return {**preview, 'storageCleanupFailures': failures}


@router.post("/monthly-runs", status_code=202, response_model=RunResponse)
async def monthly_run(request: Request, response: Response, principal: Identity, key: Idempotency, session: DB,
                      periodo: Annotated[str, Form(max_length=100)], zip: Annotated[UploadFile, File()],
                      manifest: Annotated[str | None, Form(max_length=200_000)] = None):
    principal.require("Operator")
    validate_key(key)
    name = _leaf(zip.filename)
    if not name.lower().endswith(".zip"):
        raise ApplicationError(415, "ZIP_REQUIRED", "Adjunta un archivo .zip")
    overrides = {}
    if manifest:
        try:
            overrides = json.loads(manifest)
            if not isinstance(overrides, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                     or len(k) > 512 or len(v) > 100 for k, v in overrides.items()):
                raise ValueError()
        except (ValueError, TypeError):
            raise ApplicationError(400, "INVALID_MANIFEST", "El manifiesto debe relacionar rutas ASC con códigos de tabla") from None
    stored = await request.app.state.storage.put_upload(zip, request.app.state.settings.max_upload_mb * 1024 * 1024)
    try:
        run = create_monthly(session, request.app.state.settings, principal, key, periodo, name, stored, overrides)
        commit_or_conflict(session)
        _accepted(response, run)
        return run_response(session, run)
    except IntegrityError:
        session.rollback()
        raise ApplicationError(409, "CONCURRENT_REQUEST", "Otra solicitud equivalente se registró; reintenta con la misma clave") from None
    except BaseException:
        session.rollback()
        raise
    finally:
        referenced = session.scalar(select(StoredDocument.id).where(StoredDocument.storage_key == stored["storage_key"]))
        if not referenced:
            request.app.state.storage.resolve(stored["storage_key"]).unlink(missing_ok=True)
        await zip.close()

@router.post("/source-files", status_code=201)
async def source_file(request: Request, principal: Identity, session: DB,
                      content: Annotated[UploadFile, File()], periodo: Annotated[str, Form(max_length=100)],
                      fileName: Annotated[str | None, Form(max_length=512)] = None,
                      tableCode: Annotated[str | None, Form(max_length=100)] = None):
    principal.require("Operator")
    name = _leaf(fileName or content.filename)
    if not name.lower().endswith(".asc"):
        raise ApplicationError(415, "ASC_REQUIRED", "La fuente debe ser un archivo .asc")
    stored = await request.app.state.storage.put_upload(content, request.app.state.settings.max_file_mb * 1024 * 1024)
    try:
        document = StoredDocument(id=str(uuid4()), scope_id=principal.scope_id, kind="asc", original_name=name, **stored)
        session.add(document)
        audit(session, principal.scope_id, principal.id, "source.registered", documentId=document.id)
        session.commit()
        return {"documentId": document.id, "fileName": name, "periodo": periodo, "tableCode": tableCode, "sha256": document.sha256}
    except BaseException:
        session.rollback()
        request.app.state.storage.resolve(stored["storage_key"]).unlink(missing_ok=True)
        raise
    finally:
        await content.close()

@router.post("/annual-runs", status_code=202, response_model=RunResponse)
def annual_run(body: AnnualRequest, request: Request, response: Response, session: DB, principal: Identity, key: Idempotency):
    run = create_annual(session, request.app.state.settings, principal, key, body.anio, body.rangoNombre,
                        body.sourceRunIds, [f.model_dump() for f in body.files] if body.files else None,
                        period_range=body.period_range())
    commit_or_conflict(session)
    _accepted(response, run)
    return run_response(session, run)

@router.get("/runs", response_model=Page[RunResponse])
def runs(session: DB, principal: Reader, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    query = select(Run).where(Run.scope_id == principal.scope_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(query.order_by(Run.created_at.desc(), Run.id).offset(offset).limit(limit))
    return {"items": [run_response(session, run) for run in items], "total": total}

@router.get("/runs/{run_id}", response_model=RunResponse)
def run_details(run_id: str, session: DB, principal: Reader):
    return run_response(session, get_run(session, run_id, principal.scope_id))

@router.get("/runs/{run_id}/files", response_model=Page[FileRow])
def run_files(run_id: str, session: DB, principal: Reader, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    get_run(session, run_id, principal.scope_id)
    query = select(ProcessingFile).where(ProcessingFile.run_id == run_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(ProcessingFile.ordinal).offset(offset).limit(limit))
    return {"items": [{"id": f.id, "fileName": f.file_name, "tableCode": f.table_code, "status": f.status,
                      "message": f.message, "rowCount": f.row_count, "columnCount": f.column_count,
                      "dateColumnCount": f.date_column_count} for f in rows], "total": total}

@router.get("/runs/{run_id}/tables", response_model=Page[TableRow])
def run_tables(run_id: str, session: DB, principal: Reader):
    get_run(session, run_id, principal.scope_id)
    rows = list(session.scalars(select(ProcessingTable).where(ProcessingTable.run_id == run_id)))
    order = {code: index for index, code in enumerate(TABLE_ORDER)}
    rows.sort(key=lambda t: (order.get(t.table_code, 999), t.table_code))
    return {"items": [{"tableCode": t.table_code, "sheetName": t.sheet_name, "rowCount": t.row_count,
                       "columnCount": t.column_count, "dateColumnCount": t.date_column_count,
                       "headers": json.loads(t.headers_json)} for t in rows], "total": len(rows)}

@router.get("/runs/{run_id}/issues", response_model=Page[IssueRow])
def run_issues(run_id: str, session: DB, principal: Reader, severity: str | None = None,
               offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    get_run(session, run_id, principal.scope_id)
    query = select(Issue).where(Issue.run_id == run_id)
    if severity:
        if severity not in ("error", "warning"):
            raise ApplicationError(400, "INVALID_SEVERITY", "Severidad no válida")
        query = query.where(Issue.severity == severity)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Issue.id).offset(offset).limit(limit))
    return {"items": [{"id": i.id, "severity": i.severity, "code": i.code, "message": i.message,
                       "fileId": i.file_id, "rowNumber": i.row_number, "columnName": i.column_name} for i in rows],
            "total": total}

@router.get("/runs/{run_id}/control")
def run_control(run_id: str, request: Request, session: DB, principal: Reader,
                offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000)):
    run = get_run(session, run_id, principal.scope_id)
    if not run.result_document_id:
        return {"items": [], "total": 0}
    document = get_document(session, run.result_document_id, principal.scope_id)
    result = json.loads(request.app.state.storage.read_bytes(document.storage_key))
    rows = result["controlRows"]
    return {"items": rows[offset:offset + limit], "total": len(rows)}

@router.post("/runs/{run_id}/reprocess", status_code=202, response_model=RunResponse)
def reprocess_run(run_id: str, body: ReprocessRequest, request: Request, response: Response,
                  session: DB, principal: Identity, key: Idempotency):
    run = reprocess(session, request.app.state.settings, principal, key, run_id, body.reason, body.expectedVersion)
    commit_or_conflict(session)
    _accepted(response, run)
    return run_response(session, run)

def ensure_export(session, principal, key, run_id):
    principal.require("Operator", "Reprocessor")
    run = get_run(session, run_id, principal.scope_id)
    request_hash = fingerprint({"action": "export", "run": run_id})
    previous = replay(session, principal.scope_id, key, request_hash)
    if previous:
        return previous
    if not run.result_document_id:
        raise ApplicationError(409, "NO_RESULT", "Espera a que finalice el procesamiento")
    if run.export_status != "ready":
        pending = session.scalar(select(Job.id).where(Job.run_id == run_id, Job.kind == "export", Job.status.in_(["pending", "running"])))
        pending_outbox = session.scalar(select(OutboxMessage.id).where(OutboxMessage.run_id == run_id,
                                 OutboxMessage.event_type == "export.requested", OutboxMessage.status == "pending"))
        if not pending and not pending_outbox:
            session.add(OutboxMessage(run_id=run_id, event_type="export.requested"))
        run.export_status, run.status, run.phase = "pending", "running", "exporting"
    remember(session, principal.scope_id, key, request_hash, run)
    audit(session, principal.scope_id, principal.id, "export.requested", run_id)
    return run

@router.post("/runs/{run_id}/exports", status_code=202, response_model=RunResponse)
def request_export(run_id: str, response: Response, session: DB, principal: Identity, key: Idempotency):
    run = ensure_export(session, principal, key, run_id)
    commit_or_conflict(session)
    _accepted(response, run)
    return run_response(session, run)

@router.get("/documents/{document_id}/download")
def download(document_id: str, request: Request, session: DB, principal: Reader):
    document = get_document(session, document_id, principal.scope_id)
    if document.kind != "excel" or document.status != "available":
        raise ApplicationError(403, "DOWNLOAD_UNAVAILABLE", "Este documento no está disponible para descarga")
    path = request.app.state.storage.resolve(document.storage_key)
    if not path.is_file():
        raise ApplicationError(503, "DOCUMENT_UNAVAILABLE", "El documento no está disponible temporalmente")
    audit(session, principal.scope_id, principal.id, "document.download", document.run_id, documentId=document_id)
    session.commit()
    return FileResponse(path, filename=document.original_name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.get("/data/{table_code}", response_model=DataPage)
def data(table_code: str, request: Request, session: DB, principal: Reader, period: str | None = None, runId: str | None = None,
         offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    return data_page(session, principal.scope_id, table_code, period, runId, offset, limit, request.app.state.storage)

@router.get("/reports/overview")
def report_overview(session: DB, principal: Reader):
    return overview(session, principal.scope_id)

@router.get("/reports/analytics/options")
def report_analytics_options(request: Request, session: DB, principal: Reader):
    return analytics_options(session, request.app.state.settings, principal.scope_id)

@router.get("/reports/analytics")
def report_analytics(request: Request, session: DB, principal: Reader,
                     source: str = Query('published', pattern='^(published|reference)$'),
                     year: int = Query(2026, ge=1900, le=2100),
                     startMonth: int = Query(1, ge=1, le=12), endMonth: int = Query(12, ge=1, le=12),
                     operation: str = Query('', max_length=10), customs: str = Query('', max_length=10),
                     document: str = Query('', max_length=10), currency: Literal['USD', 'MXN'] = 'USD'):
    return analytics_summary(session, request.app.state.settings, principal.scope_id, source=source, year=year,
                             start_month=startMonth, end_month=endMonth, operation=operation, customs=customs, document=document, currency=currency)

@router.get("/audit")
def events(session: DB, principal: Identity, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    principal.require("Auditor")
    query = select(AuditEvent).where(AuditEvent.scope_id == principal.scope_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit))
    return {"items": [{"id": e.id, "actor": e.actor, "action": e.action, "runId": e.run_id,
                       "details": json.loads(e.details_json), "createdAt": e.created_at.isoformat() + "Z"} for e in rows],
            "total": total}

@router.post("/agent/conversations", status_code=201)
def conversation(session: DB, principal: Reader, request: Request):
    if not request.app.state.settings.foundry_enabled:
        raise ApplicationError(503, "FOUNDRY_NOT_CONFIGURED", "Microsoft Foundry no está configurado en este entorno")
    row = Conversation(id=str(uuid4()), scope_id=principal.scope_id, user_id=principal.id)
    session.add(row)
    session.commit()
    return {"id": row.id}

@router.post("/agent/conversations/{conversation_id}/messages")
def agent_message(conversation_id: str, body: MessageRequest, request: Request, session: DB, principal: Reader):
    settings = request.app.state.settings
    if not settings.foundry_enabled:
        raise ApplicationError(503, "FOUNDRY_NOT_CONFIGURED", "Microsoft Foundry no está configurado en este entorno")
    conversation = session.get(Conversation, conversation_id)
    if not conversation or conversation.scope_id != principal.scope_id or conversation.user_id != principal.id:
        raise ApplicationError(404, "CONVERSATION_NOT_FOUND", "No se encontró la conversación")
    history = list(session.scalars(select(AgentMessage).where(AgentMessage.conversation_id == conversation_id)
                   .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc()).limit(20)))[::-1]
    history = [{"role": item.role, "content": item.content[:8000]} for item in history]
    history.append({"role": "user", "content": body.message})
    def execute_tool(name, args, call_id):
        if name in {"start_annual", "reprocess_run"} and not (body.allowActions and settings.allow_agent_commands):
            raise ApplicationError(403, "AGENT_ACTION_NOT_AUTHORIZED", "Esta conversación no tiene habilitadas acciones")
        key = "agent:" + fingerprint({"conversation": conversation_id, "call": call_id})
        if name == "get_run":
            output = run_response(session, get_run(session, args["runId"], principal.scope_id))
            query = select(Issue).where(Issue.run_id == args["runId"])
            output["issuesTotal"] = session.scalar(select(func.count()).select_from(query.subquery()))
            output["issues"] = [{"severity": row.severity, "code": row.code, "message": row.message,
                                 "rowNumber": row.row_number, "columnName": row.column_name}
                                for row in session.scalars(query.order_by(Issue.id).limit(20))]
        elif name == "list_runs":
            rows = session.scalars(select(Run).where(Run.scope_id == principal.scope_id)
                       .order_by(Run.created_at.desc()).limit(args.get("limit", 10)))
            output = {"items": [run_response(session, item) for item in rows]}
        elif name == "get_data":
            output = data_page(session, principal.scope_id, args["tableCode"], args.get("period"), limit=args.get("limit", 10))
        elif name == "compare_periods":
            output = compare_periods(session, principal.scope_id, args["firstPeriod"], args["secondPeriod"])
        elif name == 'get_analytics':
            output = analytics_summary(session, settings, principal.scope_id, source=args['source'], year=args['year'],
                                       start_month=args['startMonth'], end_month=args['endMonth'],
                                       operation=args['operation'], customs=args['customs'], document=args['document'])
        elif name == "search_documentation":
            documents = [
                {"title": "Procesamiento", "text": "Selecciona un periodo, adjunta un ZIP con ASC delimitados por pipe y consulta la ejecución. El periodo no se infiere por nombre del ZIP."},
                {"title": "Calidad", "text": "Fechas inválidas se conservan como texto y generan advertencia. WARNING funcional indica al menos un archivo con ERROR."},
                {"title": "Reprocesos", "text": "Los reprocesos requieren permiso Reprocessor y motivo. Crean una versión nueva y conservan la anterior."},
                {"title": "Compatibilidad", "text": "La paridad con Office Scripts requiere ASC originales y aprobación de diferencias. Fechas ambiguas usan la política configurada de la ejecución."}]
            terms = args["query"].casefold().split()
            output = {"items": [doc for doc in documents if any(term in (doc["title"]+" "+doc["text"]).casefold() for term in terms)]}
        elif name == "request_report":
            report_run = get_run(session, args["runId"], principal.scope_id)
            output = run_response(session, report_run)
            output["downloadUrl"] = f"/api/v1/documents/{report_run.export_document_id}/download" if report_run.export_document_id else None
        elif name == "start_annual":
            output = run_response(session, create_annual(session, settings, principal, key, args["anio"], args["rangoNombre"]))
        elif name == "reprocess_run":
            output = run_response(session, reprocess(session, settings, principal, key, args["runId"], args["reason"], args["expectedVersion"]))
        else:
            raise ApplicationError(403, "UNKNOWN_TOOL", "Herramienta no autorizada")
        evidence = {"tool": name, "scopeId": principal.scope_id}
        if "runId" in args:
            evidence["runId"] = args["runId"]
        if name == 'get_analytics':
            parts = output['partTaxes']
            output['partTaxes'] = {**parts, 'rows': parts['rows'][:20], 'alerts': [],
                                   'totalRows': len(parts['rows']), 'totalAlerts': len(parts['alerts']),
                                   'detailLimited': True}
            evidence.update(source=args['source'], year=args['year'], startMonth=args['startMonth'], endMonth=args['endMonth'],
                            operation=args['operation'], customs=args['customs'], document=args['document'],
                            sources=output['sources'], versions=[{'month':m['month'],'runId':m['runId'],'version':m['version']}
                            for m in output['monthly'] if m['available']],
                            url='/analytics')
        audit(session, principal.scope_id, principal.id, "agent.tool", tool=name, callId=call_id)
        commit_or_conflict(session)
        return {"data": output, "evidence": [evidence]}
    from app.modules.foundry import FoundryAgent
    answer = FoundryAgent(settings).respond(history, execute_tool, language=body.language)
    session.add(AgentMessage(conversation_id=conversation_id, role="user", content=body.message))
    session.add(AgentMessage(conversation_id=conversation_id, role="assistant", content=answer["message"]))
    audit(session, principal.scope_id, principal.id, "agent.message", conversationId=conversation_id)
    session.commit()
    return answer
