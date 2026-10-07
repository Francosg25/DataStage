import hashlib
import json
import re
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.modules.engine import EngineOptions, parse_period
from app.modules.engine.models import ConsolidationRange, consolidation_range
from app.persistence.models import (
    AnnualSource, AuditEvent, IdempotencyRequest, Job, Period, Run, StoredDocument,
)


ENGINE_VERSION = "1.0.0"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value):
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def audit(session, scope, actor, action, run_id=None, **details):
    session.add(AuditEvent(scope_id=scope, actor=actor, action=action, run_id=run_id,
                           details_json=json_text(details)))


def engine_settings(settings):
    return {
        "ambiguous_date_order": settings.ambiguous_date_order,
        "preferred_date_headers": settings.preferred_date_headers,
        "max_rows": settings.max_rows,
        "max_columns": settings.max_columns,
        "encoding": settings.asc_encoding,
    }


def engine_options(snapshot):
    return EngineOptions(
        ambiguous_date_order=snapshot["ambiguous_date_order"],
        preferred_date_headers=tuple(snapshot["preferred_date_headers"]),
        max_rows=snapshot["max_rows"], max_columns=snapshot["max_columns"],
    )


def get_run(session, run_id, scope):
    run = session.get(Run, run_id)
    if not run or run.scope_id != scope:
        raise ApplicationError(404, "RUN_NOT_FOUND", "No se encontró la ejecución")
    return run


def get_document(session, document_id, scope):
    doc = session.get(StoredDocument, document_id)
    if not doc or doc.scope_id != scope:
        raise ApplicationError(404, "DOCUMENT_NOT_FOUND", "No se encontró el documento")
    return doc


def run_response(session, run):
    period = session.get(Period, run.period_id) if run.period_id else None
    period_range = consolidation_range(json.loads(run.options_json or "{}"))
    counts = {name: 0 for name in ("receivedFiles", "processedFiles", "skippedFiles", "failedFiles",
                                  "processedTables", "rows", "warnings", "errors")}
    counts.update(json.loads(run.counts_json or "{}"))
    return {
        "id": run.id, "kind": run.kind, "period": period.name if period else None,
        "year": run.year, "rangeName": run.range_name,
        "periodRange": period_range.payload() if period_range else None,
        "status": run.status, "phase": run.phase, "progress": run.progress,
        "functionalResult": run.functional_result, "publicationStatus": run.publication_status,
        "exportStatus": run.export_status,
        "createdAt": run.created_at.isoformat() + "Z", "updatedAt": run.updated_at.isoformat() + "Z",
        "counts": counts,
        "exportDocumentId": run.export_document_id, "errorMessage": run.error_message,
        "periodVersion": period.version if period else 0,
        "engineVersion": run.engine_version, "parentRunId": run.parent_run_id,
    }


def validate_key(key):
    if not key or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key):
        raise ApplicationError(400, "IDEMPOTENCY_KEY_REQUIRED",
                               "Envía Idempotency-Key de 8 a 128 caracteres")


def replay(session, scope, key, request_hash):
    validate_key(key)
    item = session.scalar(select(IdempotencyRequest).where(
        IdempotencyRequest.scope_id == scope, IdempotencyRequest.key == key))
    if item:
        if item.request_hash != request_hash:
            raise ApplicationError(409, "IDEMPOTENCY_CONFLICT",
                                   "La clave de idempotencia ya se usó con otra solicitud")
        return get_run(session, item.run_id, scope)
    return None


def get_or_create_period(session, scope, text):
    try:
        year, month, name = parse_period(text)
    except ValueError as exc:
        raise ApplicationError(400, "INVALID_PERIOD", str(exc)) from None
    period = session.scalar(select(Period).where(Period.scope_id == scope,
                             Period.year == year, Period.month == month))
    if not period:
        period = Period(id=str(uuid4()), scope_id=scope, year=year, month=month, name=name)
        session.add(period)
        session.flush()
    return period


def enqueue(session, run, kind="process"):
    session.add(Job(id=str(uuid4()), run_id=run.id, kind=kind))


def remember(session, scope, key, request_hash, run):
    session.add(IdempotencyRequest(scope_id=scope, key=key, request_hash=request_hash, run_id=run.id))


def create_monthly(session, settings, principal, key, period_text, original_name, stored, overrides=None):
    principal.require("Operator")
    period = get_or_create_period(session, principal.scope_id, period_text)
    options = engine_settings(settings)
    manifest_overrides = overrides or {}
    request = {"kind": "monthly", "period": period.name, "zipHash": stored["sha256"],
               "tableCodes": manifest_overrides}
    request_hash = fingerprint(request)
    execution_hash = fingerprint({**request, "engine": ENGINE_VERSION, "options": options})
    previous = replay(session, principal.scope_id, key, request_hash)
    if previous:
        return previous
    existing = session.scalar(select(Run).where(Run.scope_id == principal.scope_id,
                                               Run.input_fingerprint == execution_hash))
    if existing and period.active_run_id and existing.id != period.active_run_id and existing.status not in ('queued', 'running'):
        principal.require('Reprocessor')
        # Re-uploading an older file must create a replacement, not return an inactive run.
        execution_hash = fingerprint({'input': execution_hash, 'replaces': period.active_run_id})
        existing = session.scalar(select(Run).where(Run.scope_id == principal.scope_id,
                                                   Run.input_fingerprint == execution_hash))
    if existing:
        remember(session, principal.scope_id, key, request_hash, existing)
        return existing
    if period.active_run_id:
        principal.require("Reprocessor")
    run = Run(id=str(uuid4()), scope_id=principal.scope_id, kind="monthly", period_id=period.id,
              year=period.year, input_fingerprint=execution_hash, created_by=principal.id,
              expected_period_version=period.version, engine_version=ENGINE_VERSION,
              options_json=json_text(options))
    session.add(run)
    session.flush()
    doc = StoredDocument(id=str(uuid4()), scope_id=principal.scope_id, run_id=run.id, kind="zip",
                         original_name=original_name, **stored)
    session.add(doc)
    session.flush()
    run.source_manifest_json = json_text([{"zipDocumentId": doc.id, "period": period.name,
                                          "tableCodes": manifest_overrides}])
    enqueue(session, run)
    audit(session, principal.scope_id, principal.id, "monthly.submitted", run.id,
          period=period.name, replaces=period.active_run_id)
    remember(session, principal.scope_id, key, request_hash, run)
    session.flush()
    return run


def create_annual(session, settings, principal, key, year, range_name, source_run_ids=None, files=None,
                  *, period_range: ConsolidationRange | None = None):
    principal.require("Operator")
    if period_range:
        year, range_name = period_range.start_year, period_range.label
    if not 1900 <= year <= 2100:
        raise ApplicationError(400, "INVALID_YEAR", "El año debe estar entre 1900 y 2100")
    if source_run_ids and files:
        raise ApplicationError(400, "MIXED_SOURCES", "Selecciona versiones mensuales o archivos, no ambos")
    # Replay the caller's request before resolving mutable active-month pointers.
    # The execution fingerprint below separately fixes the selected source snapshot.
    request = {"kind": "annual", "year": year, "range": range_name,
               "sourceRunIds": source_run_ids, "files": files}
    if period_range:
        request["periodRange"] = period_range.payload()
    request_hash = fingerprint(request)
    previous = replay(session, principal.scope_id, key, request_hash)
    if previous:
        return previous
    options = engine_settings(settings)
    if period_range:
        options["consolidation_range"] = asdict(period_range)
    manifest = []
    sources = []
    if files:
        for item in files:
            document = get_document(session, item["documentId"], principal.scope_id)
            if document.kind != "asc" or document.status != "available":
                raise ApplicationError(400, "INVALID_SOURCE", "La fuente debe ser un ASC registrado")
            # Invalid periods are deliberately passed to the annual engine for skipped-file control.
            manifest.append({"documentId": document.id, "fileName": item.get("fileName") or document.original_name,
                             "period": item["periodo"], "tableCode": item.get("tableCode"),
                             "sha256": document.sha256})
    else:
        if source_run_ids is None:
            query = select(Run).join(Period, Period.active_run_id == Run.id).where(
                Period.scope_id == principal.scope_id, Run.scope_id == principal.scope_id)
            if period_range:
                query = query.where((Period.year * 12 + Period.month).between(
                    period_range.start_index, period_range.end_index))
            else:
                query = query.where(Period.year == year)
            sources = list(session.scalars(query.order_by(Period.year, Period.month)))
        else:
            if len(source_run_ids) != len(set(source_run_ids)):
                raise ApplicationError(400, "DUPLICATE_SOURCE", "Una versión mensual aparece más de una vez")
            sources = [get_run(session, rid, principal.scope_id) for rid in source_run_ids]
        seen_periods = set()
        for source in sources:
            if (source.kind != "monthly" or source.publication_status != "published"
                    or (not period_range and source.year != year)):
                raise ApplicationError(409, "SOURCE_NOT_PUBLISHED", "Cada fuente debe ser una versión mensual publicada del año")
            if period_range:
                period = session.get(Period, source.period_id)
                if not period or not period_range.contains(period.year, period.month):
                    raise ApplicationError(409, "SOURCE_OUTSIDE_RANGE", "Una fuente está fuera del rango seleccionado")
            if source.period_id in seen_periods:
                raise ApplicationError(400, "MULTIPLE_PERIOD_VERSIONS", "Selecciona una sola versión por periodo")
            seen_periods.add(source.period_id)
            manifest.append({"monthlyRunId": source.id})
    if not manifest:
        raise ApplicationError(409, "NO_ANNUAL_SOURCES", "No hay fuentes disponibles para consolidar")
    execution_hash = fingerprint({"kind": "annual", "year": year, "range": range_name, "manifest": manifest,
                                  "engine": ENGINE_VERSION, "options": options})
    existing = session.scalar(select(Run).where(Run.scope_id == principal.scope_id,
                                               Run.input_fingerprint == execution_hash))
    if existing:
        remember(session, principal.scope_id, key, request_hash, existing)
        return existing
    run = Run(id=str(uuid4()), scope_id=principal.scope_id, kind="annual", year=year,
              range_name=range_name, created_by=principal.id, input_fingerprint=execution_hash,
              engine_version=ENGINE_VERSION, options_json=json_text(options),
              source_manifest_json=json_text(manifest))
    session.add(run)
    session.flush()
    for source in sources:
        session.add(AnnualSource(annual_run_id=run.id, monthly_run_id=source.id, period_id=source.period_id))
    enqueue(session, run)
    audit(session, principal.scope_id, principal.id, "annual.submitted", run.id,
          year=year, range=range_name, sources=len(manifest))
    remember(session, principal.scope_id, key, request_hash, run)
    session.flush()
    return run


def reprocess(session, settings, principal, key, original_id, reason, expected_version):
    principal.require("Reprocessor")
    original = get_run(session, original_id, principal.scope_id)
    request_hash = fingerprint({"reprocess": original.id, "reason": reason, "expectedVersion": expected_version})
    previous = replay(session, principal.scope_id, key, request_hash)
    if previous:
        return previous
    period = session.get(Period, original.period_id) if original.period_id else None
    if period and period.version != expected_version:
        raise ApplicationError(409, "VERSION_CONFLICT", "El periodo cambió; actualiza antes de reprocesar")
    if original.status in ("queued", "running"):
        raise ApplicationError(409, "RUN_ACTIVE", "La ejecución todavía está en proceso")
    options = engine_settings(settings)
    period_range = consolidation_range(json.loads(original.options_json))
    if period_range:
        options["consolidation_range"] = asdict(period_range)
    run = Run(id=str(uuid4()), scope_id=principal.scope_id, kind=original.kind,
              period_id=original.period_id, year=original.year, range_name=original.range_name,
              parent_run_id=original.id, created_by=principal.id,
              input_fingerprint=fingerprint({"reprocess": original.id, "key": key}),
              expected_period_version=expected_version, engine_version=ENGINE_VERSION,
              source_manifest_json=original.source_manifest_json, options_json=json_text(options))
    session.add(run)
    session.flush()
    for source in session.scalars(select(AnnualSource).where(AnnualSource.annual_run_id == original.id)):
        session.add(AnnualSource(annual_run_id=run.id, monthly_run_id=source.monthly_run_id, period_id=source.period_id))
    enqueue(session, run)
    remember(session, principal.scope_id, key, request_hash, run)
    audit(session, principal.scope_id, principal.id, "run.reprocess", run.id, previousRun=original.id, reason=reason)
    session.flush()
    return run


def commit_or_conflict(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApplicationError(409, "CONCURRENT_REQUEST", "Otra solicitud equivalente se registró; reintenta con la misma clave") from None
