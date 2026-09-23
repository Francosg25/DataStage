"""Durable SQL job worker. Run separately: python -m app.worker."""
import hashlib
import json
import logging
import signal
import threading
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import configure_logging
from app.modules.engine import InputFile, detect_table_code, export_xlsx, parse_period, process_annual, process_monthly
from app.modules.engine.catalog import folio_from_name
from app.modules.identity.auth import Principal
from app.modules.ingestion.zip_reader import read_zip, scan_document
from app.modules.processing.service import (
    audit, create_annual, engine_options, get_or_create_period, json_text,
)
from app.modules.storage.filesystem import FileSystemStorage
from app.persistence import get_business_table, make_engine, persist_business_rows, session_factory
from app.persistence.models import (
    Issue, Job, OutboxMessage, Period, ProcessingFile, ProcessingTable, Run, StoredDocument, utcnow,
)

log = logging.getLogger("datastage.worker")


def job_guard(session, job_id, owner, fence, settings):
    now = utcnow()
    result = session.execute(update(Job).where(Job.id == job_id, Job.status == "running",
        Job.lease_owner == owner, Job.fence == fence, Job.lease_until > now).values(
        lease_until=now + timedelta(seconds=settings.job_lease_seconds)))
    if result.rowcount != 1:
        raise ApplicationError(409, "LEASE_LOST", "El trabajo fue reservado por otro worker")


def claim_job(factory, settings, owner):
    now = utcnow()
    eligible = or_(and_(Job.status == "pending", Job.available_at <= now),
                   and_(Job.status == "running", Job.lease_until < now))
    with factory() as session:
        candidates = list(session.scalars(select(Job).where(eligible).order_by(Job.available_at, Job.id).limit(10)))
        for job in candidates:
            result = session.execute(update(Job).where(Job.id == job.id, Job.fence == job.fence, eligible)
                .values(status="running", lease_owner=owner,
                        lease_until=now + timedelta(seconds=settings.job_lease_seconds),
                        fence=Job.fence + 1, attempts=Job.attempts + 1))
            if result.rowcount == 1:
                session.commit()
                return session.get(Job, job.id)
            session.rollback()
    return None


class Heartbeat:
    def __init__(self, factory, settings, job):
        self.factory, self.settings, self.job = factory, settings, job
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self):
        while not self.stop.wait(self.settings.job_lease_seconds / 3):
            try:
                with self.factory() as session:
                    job_guard(session, self.job.id, self.job.lease_owner, self.job.fence, self.settings)
                    session.commit()
            except (ApplicationError, OperationalError):
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=2)


def progress(factory, settings, job, phase, percent):
    with factory() as session:
        job_guard(session, job.id, job.lease_owner, job.fence, settings)
        run = session.get(Run, job.run_id)
        run.status, run.phase, run.progress = "running", phase, percent
        run.updated_at = utcnow()
        session.commit()


def _read_source_document(store, document, maximum, *, collect=True):
    """Bound actual reads and verify the immutable document before using it."""
    if document.size_bytes < 0 or document.size_bytes > maximum:
        raise ApplicationError(422, "SOURCE_SIZE_LIMIT", "Una fuente supera el límite de procesamiento")
    path = store.resolve(document.storage_key)
    if path.stat().st_size > maximum:
        raise ApplicationError(422, "SOURCE_SIZE_LIMIT", "Una fuente supera el límite de procesamiento")
    data, size, digest = bytearray(), 0, hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(min(1024 * 1024, maximum - size + 1)):
            size += len(chunk)
            if size > maximum:
                raise ApplicationError(422, "SOURCE_SIZE_LIMIT", "Se superó el límite al leer una fuente")
            digest.update(chunk)
            if collect:
                data.extend(chunk)
    if size != document.size_bytes or digest.hexdigest() != document.sha256:
        raise ApplicationError(422, "SOURCE_INTEGRITY_ERROR", "La fuente no coincide con su hash o tamaño registrado")
    return bytes(data) if collect else None


def inputs_for_run(factory, store, settings, run):
    snapshot = json.loads(run.options_json)
    encoding = snapshot.get("encoding", settings.asc_encoding)
    manifest = json.loads(run.source_manifest_json)
    inputs, documents, metadata, ingestion_issues = [], [], [], []
    seen = {}
    entries, planned = [], []
    maximum_total = settings.max_extracted_mb * 1024 * 1024
    maximum_file = settings.max_file_mb * 1024 * 1024
    with factory() as session:
        for source in manifest:
            if "zipDocumentId" in source:
                document = session.get(StoredDocument, source["zipDocumentId"])
                if not document or document.scope_id != run.scope_id:
                    raise ApplicationError(404, "SOURCE_NOT_FOUND", "No se encontró la fuente de la ejecución")
                planned.append({"kind": "zip", "document": document, "source": source})
            elif "monthlyRunId" in source:
                monthly = session.get(Run, source["monthlyRunId"])
                if not monthly or monthly.scope_id != run.scope_id or monthly.publication_status != "published":
                    raise ApplicationError(409, "SOURCE_NOT_PUBLISHED", "Una fuente mensual no está publicada")
                files = list(session.scalars(select(ProcessingFile).where(ProcessingFile.run_id == monthly.id)
                                            .order_by(ProcessingFile.ordinal)))
                for file in files:
                    if file.status == "SKIPPED_DUPLICATE":
                        continue
                    document = session.get(StoredDocument, file.document_id)
                    period = session.get(Period, file.period_id)
                    if not document or not period or document.scope_id != run.scope_id or document.kind != "asc":
                        raise ApplicationError(409, "SOURCE_INCOMPLETE", "Faltan fuentes inmutables del mes")
                    planned.append({"kind": "asc", "document": document, "name": file.file_name,
                                    "period": period.name, "code": file.table_code})
            else:
                document = session.get(StoredDocument, source["documentId"])
                if not document or document.scope_id != run.scope_id or document.kind != "asc":
                    raise ApplicationError(404, "SOURCE_NOT_FOUND", "No se encontró el ASC registrado")
                planned.append({"kind": "asc", "document": document, "name": source["fileName"],
                                "period": source["period"], "code": source.get("tableCode")})
    # Reject annual collections from metadata before reading the first byte.
    asc_documents = [item["document"] for item in planned if item["kind"] == "asc"]
    if any(doc.size_bytes < 0 or doc.size_bytes > maximum_file for doc in asc_documents):
        raise ApplicationError(422, "ASC_SIZE_LIMIT", "Un archivo ASC supera el límite")
    if sum(doc.size_bytes for doc in asc_documents) > maximum_total:
        raise ApplicationError(422, "SOURCE_SIZE_LIMIT", "El conjunto de fuentes supera el límite de procesamiento")
    total_bytes = 0
    for item in planned:
        document = item["document"]
        if item["kind"] == "zip":
            _read_source_document(store, document, settings.max_upload_mb * 1024 * 1024, collect=False)
            scan_document(store.resolve(document.storage_key), settings)
            source = item["source"]
            overrides, known_entries = source.get("tableCodes", {}), set()
            for name, data in read_zip(store.resolve(document.storage_key), settings):
                total_bytes += len(data)
                if total_bytes > maximum_total:
                    raise ApplicationError(422, "SOURCE_SIZE_LIMIT", "El conjunto de fuentes supera el límite de procesamiento")
                known_entries.add(name)
                entries.append((name, data, source["period"], overrides.get(name), None))
            if set(overrides) - known_entries:
                raise ApplicationError(422, "UNKNOWN_MANIFEST_ENTRY", "El manifiesto menciona archivos que no existen en el ZIP")
        else:
            data = _read_source_document(store, document, min(maximum_file, maximum_total - total_bytes))
            total_bytes += len(data)
            scan_document(store.resolve(document.storage_key), settings)
            entries.append((item["name"], data, item["period"], item["code"], document))
    for ordinal, (name, raw, period, code, existing_doc) in enumerate(entries):
        file_id = str(uuid5(NAMESPACE_URL, f"{run.id}:{ordinal}:{name}"))
        code = detect_table_code(name, code)
        if len(name) > 512 or len(code) > 100:
            raise ApplicationError(422, "SOURCE_NAME_LIMIT", "Un nombre de archivo o código de tabla excede el límite")
        sha = hashlib.sha256(raw).hexdigest()
        try:
            _, _, period = parse_period(period)
        except ValueError:
            pass  # Annual engine records the excluded source.
        identity = (period, code, sha)
        doc = existing_doc
        if doc is None:
            saved = store.put_bytes(raw, ".asc")
            doc = StoredDocument(id=str(uuid4()), scope_id=run.scope_id, run_id=run.id,
                                 kind="asc", original_name=name, **saved)
            documents.append(doc)
        meta = {"id": file_id, "run_id": run.id, "document_id": doc.id, "file_name": name,
                "table_code": code, "sha256": sha, "ordinal": ordinal, "period": period,
                "folio": folio_from_name(name, code)}
        if identity in seen:
            meta.update(status="SKIPPED_DUPLICATE", message="Archivo duplicado por contenido, periodo y tabla; no se cargó dos veces.")
            ingestion_issues.append({"fileId": file_id, "fileName": name, "code": "DUPLICATE_FILE",
                                     "message": meta["message"]})
        else:
            seen[identity] = file_id
            try:
                content = raw.decode(encoding, errors="strict")
            except UnicodeDecodeError:
                # The deterministic engine classifies non-text content as a per-file error.
                content = raw
                ingestion_issues.append({"fileId": file_id, "fileName": name, "code": "INVALID_ENCODING",
                                         "message": f"No se pudo interpretar el archivo con {encoding}."})
            inputs.append(InputFile(file_name=name, content=content, period=period, table_code=code, file_id=file_id))
        metadata.append(meta)
    return inputs, documents, metadata, ingestion_issues


def process_job(factory, store, settings, job):
    with factory() as session:
        run = session.get(Run, job.run_id)
        if run.result_document_id:
            # A committed engine result is never reinserted by a delivery retry.
            job_guard(session, job.id, job.lease_owner, job.fence, settings)
            session.get(Job, job.id).status = "completed"
            session.commit()
            return
    progress(factory, settings, job, "extracting", 10)
    inputs, documents, metadata, ingestion_issues = inputs_for_run(factory, store, settings, run)
    progress(factory, settings, job, "processing", 30)
    options = engine_options(json.loads(run.options_json))
    if run.kind == "monthly":
        with factory() as session:
            period_name = session.get(Period, run.period_id).name
        result = process_monthly(period_name, inputs, options)
    else:
        result = process_annual(run.year, run.range_name, inputs, options)
    result["warnings"].extend(ingestion_issues)
    duplicates = [meta for meta in metadata if meta.get("status") == "SKIPPED_DUPLICATE"]
    result["receivedFiles"] += len(duplicates)
    result["skippedFiles"] += len(duplicates)
    for meta in duplicates:
        row = {"Archivo": meta["file_name"], "Tabla": meta["table_code"], "Hoja": "",
               "Estatus": "OK", "Filas": 0, "Columnas": 0, "ColumnasFecha": 0, "Mensaje": meta["message"]}
        if run.kind == "annual":
            row = {"Periodo": meta["period"], **row}
        result["controlRows"].append(row)
    unknown = [table["tableCode"] for table in result["tables"] if get_business_table(table["tableCode"]) is None]
    for code in unknown:
        result["warnings"].append({"code": "SCHEMA_PENDING", "message": f"La tabla {code} requiere alta de esquema SQL."})
    progress(factory, settings, job, "persisting", 65)
    result_saved = store.put_bytes(json_text(result).encode("utf-8"), ".json")
    result_doc = StoredDocument(id=str(uuid4()), scope_id=run.scope_id, run_id=run.id,
                               kind="result", original_name=f"result-{run.id}.json", **result_saved)
    # One atomic publication includes accepted files, business rows, diagnostics and outbox.
    with factory() as session:
        job_guard(session, job.id, job.lease_owner, job.fence, settings)
        current = session.get(Run, run.id)
        periods = {}
        session.add_all(documents)
        session.add(result_doc)
        session.flush()
        outcomes = {item["fileId"]: item for item in result["files"]}
        for meta in metadata:
            period_text = meta.pop("period")
            try:
                period = get_or_create_period(session, run.scope_id, period_text)
                periods[period.name] = period
            except ApplicationError:
                period = None
            outcome = outcomes.get(meta["id"], {})
            row = ProcessingFile(**meta, period_id=period.id if period else None)
            if meta.get("status") != "SKIPPED_DUPLICATE":
                row.status = outcome.get("status", "SKIPPED")
                row.message = outcome.get("message", "Archivo excluido por periodo o rango")
            row.row_count = outcome.get("rowsCount", 0)
            row.column_count = outcome.get("columnsCount", 0)
            row.date_column_count = outcome.get("dateColumnsCount", 0)
            row.headers_json = json_text(outcome.get("headers", []))
            session.add(row)
        session.flush()
        direct_annual = run.kind == "annual" and any("documentId" in src for src in json.loads(run.source_manifest_json))
        for table in result["tables"]:
            session.add(ProcessingTable(run_id=run.id, table_code=table["tableCode"],
                        sheet_name=table["sheetName"], row_count=len(table["rows"]),
                        column_count=len(table["headers"]), date_column_count=len(table["dateColumns"]),
                        headers_json=json_text(table["headers"])))
            if run.kind == "monthly" or direct_annual:
                persist_business_rows(session, run.id, table, periods)
        known_files = {meta["id"] for meta in metadata}
        for severity, collection in (("error", result["errors"]), ("warning", result["warnings"])):
            for issue in collection:
                session.add(Issue(run_id=run.id, file_id=issue.get("fileId") if issue.get("fileId") in known_files else None,
                                  severity=severity, code=issue["code"], message=issue["message"],
                                  row_number=issue.get("rowNumber"), column_name=issue.get("column"),
                                  original_value=issue.get("original")))
        has_headers = bool(result["tables"])
        publication = "awaiting_schema" if unknown else "published" if has_headers else "rejected"
        if publication == "published" and run.kind == "monthly":
            swapped = session.execute(update(Period).where(Period.id == run.period_id,
                      Period.version == run.expected_period_version).values(
                      active_run_id=run.id, version=Period.version + 1))
            if swapped.rowcount != 1:
                raise ApplicationError(409, "VERSION_CONFLICT", "Otra ejecución publicó este periodo; solicita un reproceso controlado")
        current.result_document_id = result_doc.id
        current.functional_result = result["functionalResult"]
        current.publication_status = publication
        current.export_status, current.phase, current.progress = "pending", "exporting", 85
        current.status = "running" if publication == "published" else "needs_attention"
        current.error_message = None
        current.counts_json = json_text({
            **{key: result[key] for key in ("receivedFiles", "processedFiles", "skippedFiles", "failedFiles", "processedTables")},
            "rows": sum(len(table["rows"]) for table in result["tables"]),
            "warnings": len(result["warnings"]), "errors": len(result["errors"]),
        })
        session.add(OutboxMessage(run_id=run.id, event_type="export.requested"))
        if run.kind == "monthly" and publication == "published" and settings.auto_annual:
            session.add(OutboxMessage(run_id=run.id, event_type="monthly.published"))
        audit(session, run.scope_id, "worker", "run.published" if publication == "published" else "run.review_required",
              run.id, publication=publication, result=result["functionalResult"])
        session.get(Job, job.id).status = "completed"
        session.commit()


def export_job(factory, store, settings, job):
    with factory() as session:
        run = session.get(Run, job.run_id)
        document = session.get(StoredDocument, run.result_document_id) if run.result_document_id else None
        if not document:
            raise ApplicationError(409, "NO_RESULT", "La ejecución todavía no tiene resultado")
        result = json.loads(store.read_bytes(document.storage_key))
        if run.kind == "monthly":
            period = session.get(Period, run.period_id)
            name = f"DataStage_{period.name}.xlsx"
        else:
            safe_range = "".join(c for c in run.range_name if c.isalnum() or c in "-_") or "Anual"
            name = f"DataStage_{run.year}_{safe_range}.xlsx"
    output_key = f"{uuid4().hex}.xlsx"
    if hasattr(store, "track_output"):
        store.track_output(output_key)
    output_path = store.resolve(output_key)
    export_xlsx(result, output_path)
    with output_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    saved = {"storage_key": output_key, "sha256": digest, "size_bytes": output_path.stat().st_size}
    with factory() as session:
        job_guard(session, job.id, job.lease_owner, job.fence, settings)
        current = session.get(Run, run.id)
        doc = StoredDocument(id=str(uuid4()), scope_id=run.scope_id, run_id=run.id,
                             kind="excel", original_name=name, **saved)
        session.add(doc)
        session.flush()
        current.export_document_id = doc.id
        current.export_status, current.progress = "ready", 100
        current.status = "completed" if current.publication_status == "published" else "needs_attention"
        current.phase = "completed"
        current.error_message = None
        current.updated_at = utcnow()
        session.get(Job, job.id).status = "completed"
        audit(session, run.scope_id, "worker", "export.ready", run.id, documentId=doc.id)
        session.commit()


def dispatch_outbox(factory, settings):
    with factory() as session:
        ids = list(session.scalars(select(OutboxMessage.id).where(OutboxMessage.status == "pending")
                                   .order_by(OutboxMessage.created_at).limit(20)))
    for message_id in ids:
        try:
            with factory() as session:
                claimed = session.execute(update(OutboxMessage).where(OutboxMessage.id == message_id,
                          OutboxMessage.status == "pending").values(status="dispatched"))
                if claimed.rowcount != 1:
                    session.rollback()
                    continue
                message = session.get(OutboxMessage, message_id)
                run = session.get(Run, message.run_id)
                if message.event_type == "export.requested":
                    session.add(Job(run_id=run.id, kind="export"))
                elif message.event_type == "monthly.published":
                    periods = list(session.scalars(select(Period).where(Period.scope_id == run.scope_id,
                                   Period.year == run.year, Period.active_run_id.is_not(None))))
                    last_month = max(p.month for p in periods)
                    short = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
                    principal = Principal("system", "Consolidación automática", frozenset({"Operator"}), run.scope_id)
                    create_annual(session, settings, principal, f"auto-annual:{run.id}", run.year,
                                  f"Ene-{short[last_month-1]}")
                session.commit()
        except IntegrityError:
            # Another dispatcher may have committed this exact source snapshot.
            # The rolled-back outbox entry remains pending and replays next pass.
            log.info("Outbox reintentará un conflicto concurrente", extra={"message_id": message_id})
        except OperationalError:
            log.warning("Outbox temporalmente no disponible")


def fail_job(factory, settings, job, error):
    transient = isinstance(error, (OperationalError, OSError)) or (isinstance(error, ApplicationError) and error.status >= 500)
    message = error.detail if isinstance(error, ApplicationError) else (
        "Fallo temporal de infraestructura; se reintentará." if transient else
        "No fue posible completar la fase. Consulta el identificador de ejecución con soporte.")
    with factory() as session:
        claimed = session.execute(update(Job).where(Job.id == job.id, Job.status == "running",
                                  Job.lease_owner == job.lease_owner, Job.fence == job.fence,
                                  Job.lease_until > utcnow())
                                  .values(last_error=message))
        if claimed.rowcount != 1:
            session.rollback()
            return
        current = session.get(Job, job.id)
        run = session.get(Run, job.run_id)
        if transient and current.attempts < settings.max_job_attempts:
            current.status = "pending"
            current.available_at = utcnow() + timedelta(seconds=min(300, 2 ** current.attempts * 3))
            run.status, run.phase = "queued", "retry_pending"
        else:
            current.status = "failed"
            run.status, run.phase = "failed", "failed"
            if job.kind == "export":
                run.export_status = "failed"
            elif run.publication_status != "published":
                run.publication_status = "rejected"
            session.add(Issue(run_id=run.id, severity="error", code=getattr(error, "code", "WORKER_FAILURE"), message=message))
            audit(session, run.scope_id, "worker", "job.failed", run.id, jobId=job.id, phase=job.kind)
        run.error_message = message
        run.updated_at = utcnow()
        current.lease_until, current.lease_owner = None, None
        session.commit()


class DocumentWriteBatch:
    """Clean only this attempt's new blobs after its SQL transaction has ended."""
    def __init__(self, store, factory):
        self.store, self.factory, self.keys = store, factory, set()

    def __getattr__(self, name):
        return getattr(self.store, name)

    def put_bytes(self, content, suffix):
        saved = self.store.put_bytes(content, suffix)
        self.keys.add(saved["storage_key"])
        return saved

    def track_output(self, key):
        self.keys.add(key)

    def cleanup(self):
        if not self.keys:
            return
        try:
            with self.factory() as session:
                referenced = set()
                ordered = list(self.keys)
                # Remain below SQL Server's parameter limit for large ZIPs.
                for start in range(0, len(ordered), 500):
                    referenced.update(session.scalars(select(StoredDocument.storage_key).where(
                        StoredDocument.storage_key.in_(ordered[start:start + 500]))))
            for key in self.keys - referenced:
                self.store.resolve(key).unlink(missing_ok=True)
        except (OperationalError, OSError):
            # Never delete when SQL cannot confirm ownership. Recovery is an
            # offline storage reconciliation task with API/worker stopped.
            log.warning("No fue posible reconciliar documentos del intento")


def run_once(factory, settings, store=None, owner=None):
    store = store or FileSystemStorage(settings.document_root)
    owner = owner or str(uuid4())
    dispatch_outbox(factory, settings)
    job = claim_job(factory, settings, owner)
    if not job:
        return False
    batch = DocumentWriteBatch(store, factory)
    try:
        if job.attempts > settings.max_job_attempts:
            raise ApplicationError(500, "RETRY_EXHAUSTED", "Se agotaron los intentos del trabajo")
        with Heartbeat(factory, settings, job):
            if job.kind == "process":
                process_job(factory, batch, settings, job)
            elif job.kind == "export":
                export_job(factory, batch, settings, job)
            else:
                raise ApplicationError(422, "UNKNOWN_JOB", "Tipo de trabajo no registrado")
    except Exception as error:
        log.error("Fallo de trabajo", extra={"run_id": job.run_id, "job_id": job.id}, exc_info=True)
        fail_job(factory, settings, job, error)
    finally:
        batch.cleanup()
    return True


def main():
    configure_logging()
    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = session_factory(engine)
    store = FileSystemStorage(settings.document_root)
    stopping = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopping.set())
    owner = str(uuid4())
    while not stopping.is_set():
        try:
            if not run_once(factory, settings, store, owner):
                stopping.wait(settings.worker_poll_seconds)
        except OperationalError:
            log.warning("SQL no disponible; worker esperando")
            stopping.wait(min(30, settings.worker_poll_seconds * 5))
    engine.dispose()


if __name__ == "__main__":
    main()
