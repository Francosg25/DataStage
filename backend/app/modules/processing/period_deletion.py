"""Elimina un mes y los consolidados derivados en una transacción."""
import json

from sqlalchemy import delete, func, select, update

from app.core.errors import ApplicationError
from app.modules.processing.service import audit
from app.persistence.business import BUSINESS_TABLES, EXTENSION_TABLES
from app.persistence.models import (
    AnnualSource, AuditEvent, IdempotencyRequest, Issue, Job, OutboxMessage,
    Period, ProcessingFile, ProcessingTable, Run, StoredDocument,
)


def _targets(session, scope: str, period: Period) -> dict[str, Run]:
    runs = {
        run.id: run for run in session.scalars(
            select(Run).where(Run.scope_id == scope, Run.period_id == period.id)
        )
    }

    documents = {
        doc.id for doc in session.scalars(
            select(StoredDocument).where(
                StoredDocument.scope_id == scope,
                StoredDocument.run_id.in_(runs),
            )
        )
    } if runs else set()

    for run in session.scalars(
        select(Run).where(Run.scope_id == scope, Run.kind == "annual")
    ):
        sources = json.loads(run.source_manifest_json or "[]")
        if any(
            source.get("monthlyRunId") in runs
            or source.get("documentId") in documents
            or source.get("period", source.get("periodo")) == period.name
            for source in sources
        ):
            runs[run.id] = run

    for run in session.scalars(
        select(Run)
        .join(AnnualSource, AnnualSource.annual_run_id == Run.id)
        .where(Run.scope_id == scope, AnnualSource.period_id == period.id)
    ):
        runs[run.id] = run

    for run in session.scalars(
        select(Run)
        .join(ProcessingFile, ProcessingFile.run_id == Run.id)
        .where(Run.scope_id == scope, ProcessingFile.period_id == period.id)
    ):
        runs[run.id] = run

    while runs:
        children = list(session.scalars(
            select(Run).where(
                Run.scope_id == scope,
                Run.parent_run_id.in_(runs),
            )
        ))
        new_children = [run for run in children if run.id not in runs]
        if not new_children:
            break
        runs.update((run.id, run) for run in new_children)

    return runs


def deletion_preview(
    session, principal, period_id: str, *, lock: bool = False
) -> tuple[Period, dict, dict[str, Run]]:
    principal.require("Admin")

    query = select(Period).where(
        Period.id == period_id,
        Period.scope_id == principal.scope_id,
    )
    period = session.scalar(query.with_for_update() if lock else query)
    if period is None:
        raise ApplicationError(404, "PERIOD_NOT_FOUND", "No se encontró el mes")

    runs = _targets(session, principal.scope_id, period)
    ids = list(runs)

    if any(run.status in ("queued", "running") for run in runs.values()):
        raise ApplicationError(
            409, "PERIOD_BUSY",
            "Hay procesos activos para este mes; espera a que terminen",
        )

    if ids and session.scalar(
        select(Job.id).where(
            Job.run_id.in_(ids),
            Job.status.in_(("pending", "running")),
        ).limit(1)
    ):
        raise ApplicationError(
            409, "PERIOD_BUSY", "Hay trabajos pendientes para este mes"
        )

    rows = sum(
        session.scalar(
            select(func.count()).select_from(table).where(
                table.c.processing_run_id.in_(ids)
            )
        ) or 0
        for table in BUSINESS_TABLES.values()
    ) if ids else 0

    preview = {
        "periodId": period.id,
        "periodName": period.name,
        "version": period.version,
        "monthlyRuns": sum(r.kind == "monthly" for r in runs.values()),
        "annualRuns": sum(r.kind == "annual" for r in runs.values()),
        "businessRows": rows,
        "documents": session.scalar(
            select(func.count()).select_from(StoredDocument).where(
                StoredDocument.run_id.in_(ids)
            )
        ) if ids else 0,
    }
    return period, preview, runs


def delete_period(
    session,
    principal,
    period_id: str,
    expected_version: int,
    confirmation: str,
    reason: str,
    expected_impact: dict[str, int],
) -> tuple[dict, list[str]]:
    period, preview, runs = deletion_preview(
        session, principal, period_id, lock=True
    )

    if period.version != expected_version:
        raise ApplicationError(
            409, "VERSION_CONFLICT", "El mes cambió; actualiza antes de eliminar"
        )
    if confirmation != period.name:
        raise ApplicationError(
            400, "CONFIRMATION_MISMATCH",
            "Escribe exactamente el nombre del mes",
        )
    if any(preview[key] != value for key, value in expected_impact.items()):
        raise ApplicationError(
            409, "IMPACT_CHANGED",
            "El impacto cambió; vuelve a revisar antes de eliminar",
        )

    ids = list(runs)
    documents = list(session.scalars(
        select(StoredDocument).where(
            StoredDocument.scope_id == principal.scope_id,
            StoredDocument.run_id.in_(ids),
        )
    )) if ids else []
    document_ids = {doc.id for doc in documents}

    # Conserva documentos que otra ejecución todavía utiliza.
    shared = set()
    if document_ids:
        shared.update(session.scalars(
            select(ProcessingFile.document_id).where(
                ProcessingFile.document_id.in_(document_ids),
                ProcessingFile.run_id.not_in(ids),
            )
        ))
        for run in session.scalars(
            select(Run).where(
                Run.scope_id == principal.scope_id,
                Run.id.not_in(ids),
            )
        ):
            shared.update(
                doc_id
                for doc_id in (run.result_document_id, run.export_document_id)
                if doc_id in document_ids
            )
            shared.update(
                source["documentId"]
                for source in json.loads(run.source_manifest_json or "[]")
                if source.get("documentId") in document_ids
            )

    storage_keys = [
        doc.storage_key for doc in documents if doc.id not in shared
    ]

    period.active_run_id = None
    session.flush()

    if ids:
        for code, table in BUSINESS_TABLES.items():
            extension = EXTENSION_TABLES[code]
            session.execute(
                delete(extension).where(
                    extension.c.business_row_id.in_(
                        select(table.c.id).where(
                            table.c.processing_run_id.in_(ids)
                        )
                    )
                )
            )
            session.execute(
                delete(table).where(table.c.processing_run_id.in_(ids))
            )

        session.execute(
            update(AuditEvent)
            .where(AuditEvent.run_id.in_(ids))
            .values(run_id=None)
        )
        session.execute(
            delete(AnnualSource).where(
                (AnnualSource.annual_run_id.in_(ids))
                | (AnnualSource.monthly_run_id.in_(ids))
                | (AnnualSource.period_id == period.id)
            )
        )
        session.execute(delete(Issue).where(Issue.run_id.in_(ids)))
        session.execute(
            delete(ProcessingTable).where(ProcessingTable.run_id.in_(ids))
        )
        session.execute(
            delete(ProcessingFile).where(ProcessingFile.run_id.in_(ids))
        )
        session.execute(
            delete(IdempotencyRequest).where(
                IdempotencyRequest.run_id.in_(ids)
            )
        )
        session.execute(
            delete(OutboxMessage).where(OutboxMessage.run_id.in_(ids))
        )
        session.execute(delete(Job).where(Job.run_id.in_(ids)))

        session.execute(
            update(Run)
            .where(Run.id.in_(ids))
            .values(
                result_document_id=None,
                export_document_id=None,
                parent_run_id=None,
            )
        )
        session.flush()

        for doc in documents:
            if doc.id in shared:
                doc.run_id = None
            else:
                session.delete(doc)
        session.flush()

        session.execute(delete(Run).where(Run.id.in_(ids)))

    audit(
        session, principal.scope_id, principal.id, "period.deleted",
        period=period.name,
        reason=reason,
        runIds=ids,
        **preview,
    )
    session.delete(period)
    session.flush()
    return preview, storage_keys