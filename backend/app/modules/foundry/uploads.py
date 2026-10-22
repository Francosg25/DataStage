"""Conversation-owned source files, bounded parsing and declarative data queries."""
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
from uuid import uuid4

from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.core.errors import ApplicationError
from app.modules.processing.service import audit
from app.persistence.models import AgentUpload, StoredDocument
from .conversations import own_conversation
from .data_queries import QueryResult, empty, fail, matches, sort_key, typed
from .file_parser import FORMATS, normalize
from .tools import AttachmentQuery

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_CONVERSATION_BYTES = 25 * 1024 * 1024
MAX_FILES = 5
PARSERS = threading.BoundedSemaphore(2)


def parse_file(path, suffix):
    if not PARSERS.acquire(blocking=False):
        raise ApplicationError(429, "attachment_reader_busy", "El lector de archivos está ocupado; vuelve a intentarlo.")
    try:
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, "-m", "app.modules.foundry.file_parser", str(path), suffix],
                                cwd=Path(__file__).resolve().parents[3], env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        if result.returncode or len(result.stdout) > 16 * 1024 * 1024:
            raise ValueError("La estructura del archivo excede los límites de lectura.")
        parsed = json.loads(result.stdout)
        if not parsed.get("ok"):
            raise ValueError(parsed.get("error", "No se pudo leer el archivo."))
        return parsed["data"]
    except OSError as error:
        raise ApplicationError(503, "attachment_reader_unavailable", "No se pudo iniciar el lector con el intérprete Python autorizado.") from error
    except (ValueError, subprocess.TimeoutExpired) as error:
        detail = str(error) if isinstance(error, ValueError) else "El archivo tardó demasiado en analizarse; reduce su tamaño."
        raise ApplicationError(422, "attachment_invalid", detail) from error
    finally:
        PARSERS.release()


def public_file(document, upload):
    return {"fileId": document.id, "name": document.original_name, "format": Path(document.original_name).suffix[1:].lower(),
            "sizeBytes": document.size_bytes, "sha256": document.sha256,
            "createdAt": document.created_at.isoformat() + "Z", **json.loads(upload.metadata_json)}


def list_files(session, principal, conversation_id):
    own_conversation(session, principal, conversation_id)
    rows = session.execute(select(StoredDocument, AgentUpload).join(AgentUpload,
        AgentUpload.document_id == StoredDocument.id).where(AgentUpload.conversation_id == conversation_id,
        StoredDocument.scope_id == principal.scope_id, StoredDocument.status == "available", StoredDocument.kind == "agent_upload")
        .order_by(StoredDocument.created_at, StoredDocument.id))
    return {"items": [public_file(document, upload) for document, upload in rows],
            "maxFiles": MAX_FILES, "maxFileBytes": MAX_UPLOAD_BYTES, "maxTotalBytes": MAX_CONVERSATION_BYTES}


def own_file(session, principal, conversation_id, file_id):
    own_conversation(session, principal, conversation_id)
    row = session.execute(select(StoredDocument, AgentUpload).join(AgentUpload,
        AgentUpload.document_id == StoredDocument.id).where(AgentUpload.conversation_id == conversation_id,
        AgentUpload.document_id == file_id, StoredDocument.scope_id == principal.scope_id,
        StoredDocument.kind == "agent_upload", StoredDocument.status == "available")).first()
    if row is None:
        raise ApplicationError(404, "attachment_not_found", "No se encontró el adjunto de esta conversación.")
    return row


async def upload_file(session, storage, principal, conversation_id, file):
    own_conversation(session, principal, conversation_id)
    name = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in FORMATS or len(name) > 180 or any(ord(c) < 32 for c in name):
        raise ApplicationError(400, "attachment_format", "Adjunta un XLSX, CSV, PDF, DOCX o PPTX con nombre válido.")
    session.rollback()  # Do not keep a database transaction open during parsing.
    written = []
    try:
        saved = await storage.put_upload(file, MAX_UPLOAD_BYTES)
        written.append(saved)
        parsed = await run_in_threadpool(parse_file, storage.resolve(saved["storage_key"]), suffix)
        own_conversation(session, principal, conversation_id, lock=True)
        duplicate = session.execute(select(StoredDocument, AgentUpload).join(AgentUpload,
            AgentUpload.document_id == StoredDocument.id).where(AgentUpload.conversation_id == conversation_id,
            StoredDocument.scope_id == principal.scope_id, StoredDocument.sha256 == saved["sha256"],
            StoredDocument.status == "available")).first()
        if duplicate:
            session.rollback()
            return public_file(*duplicate)
        count, size = session.execute(select(func.count(), func.coalesce(func.sum(StoredDocument.size_bytes), 0))
            .select_from(AgentUpload).join(StoredDocument, AgentUpload.document_id == StoredDocument.id)
            .where(AgentUpload.conversation_id == conversation_id)).one()
        if count >= MAX_FILES or size + saved["size_bytes"] > MAX_CONVERSATION_BYTES:
            raise ApplicationError(413, "attachment_conversation_limit", "La conversación admite 5 adjuntos y 25 MiB en total. Retira alguno antes de añadir otro.")
        parsed_saved = storage.put_bytes(json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8"), ".parsed.json")
        written.append(parsed_saved)
        document = StoredDocument(id=str(uuid4()), scope_id=principal.scope_id, kind="agent_upload", original_name=name,
                                  status="available", **saved)
        extracted = StoredDocument(id=str(uuid4()), scope_id=principal.scope_id, kind="agent_upload_data",
                                   original_name="attachment-data.json", status="available", **parsed_saved)
        session.add_all([document, extracted])
        session.flush()
        metadata = {"sheets": [{"name": page["name"], "headers": page["headers"], "types": page["types"],
                               "rows": len(page["rows"])} for page in parsed["sheets"]],
                    "warnings": parsed["warnings"], "complete": True}
        if len(json.dumps(metadata, ensure_ascii=False).encode("utf-8")) > 60_000:
            raise ApplicationError(413, "attachment_catalog_large", "Las cabeceras y hojas del archivo superan el límite de catálogo.")
        upload = AgentUpload(document_id=document.id, conversation_id=conversation_id,
                             parsed_document_id=extracted.id, metadata_json=json.dumps(metadata, ensure_ascii=False))
        session.add(upload)
        audit(session, principal.scope_id, principal.id, "agent.attachment.upload", conversationId=conversation_id,
              documentId=document.id, format=suffix, sizeBytes=document.size_bytes)
        response = public_file(document, upload)
        session.commit()
        written.clear()
        return response
    except BaseException:
        session.rollback()
        raise
    finally:
        await file.close()
        for saved_file in written:
            try:
                storage.resolve(saved_file["storage_key"]).unlink(missing_ok=True)
            except OSError:
                # A failed parse/duplicate can also be locked by OneDrive. Keep
                # a discoverable tombstone so the existing worker can retry.
                try:
                    session.add(StoredDocument(id=str(uuid4()), scope_id=principal.scope_id, kind="agent_upload_data",
                        original_name="Discarded attachment", status="pending_delete", **saved_file))
                    session.commit()
                except Exception:
                    session.rollback()
                    logging.getLogger("datastage.agent").error("No se pudo registrar la limpieza de un adjunto", exc_info=True)


def remove_file(session, principal, conversation_id, file_id):
    own_conversation(session, principal, conversation_id, lock=True)
    document, upload = own_file(session, principal, conversation_id, file_id)
    parsed = session.get(StoredDocument, upload.parsed_document_id)
    if parsed is None or parsed.scope_id != principal.scope_id or parsed.kind != "agent_upload_data" or parsed.run_id:
        raise ApplicationError(409, "attachment_conflict", "No fue posible retirar el adjunto.")
    document.status = parsed.status = "pending_delete"
    session.delete(upload)
    audit(session, principal.scope_id, principal.id, "agent.attachment.delete", conversationId=conversation_id, documentId=file_id)
    session.commit()


def query_file(session, storage, principal, conversation_id, specification):
    query = AttachmentQuery.model_validate(specification)
    document, upload = own_file(session, principal, conversation_id, query.fileId)
    parsed = session.get(StoredDocument, upload.parsed_document_id)
    if parsed is None or parsed.status != "available" or parsed.scope_id != principal.scope_id or parsed.kind != "agent_upload_data":
        raise ApplicationError(503, "attachment_unavailable", "El contenido del adjunto no está disponible.")
    try:
        content = storage.read_bytes(parsed.storage_key)
    except OSError as error:
        raise ApplicationError(503, "attachment_unavailable", "El contenido del adjunto no está disponible.") from error
    if hashlib.sha256(content).hexdigest() != parsed.sha256:
        raise ApplicationError(503, "attachment_changed", "La copia analizada del archivo cambió; vuelve a adjuntarlo.")
    page = next((page for page in json.loads(content)["sheets"] if page["name"] == query.sheet), None)
    if page is None:
        fail("attachment_sheet_unknown", "Consulta las hojas del archivo con describe_attachment.")
    lookup = {normalize(header): i for i, header in enumerate(page["headers"])}
    def index(name):
        if normalize(name) not in lookup:
            fail("attachment_column_unknown", "Una columna no existe en el archivo adjunto.")
        return lookup[normalize(name)]
    columns = [index(name) for name in query.columns]
    groups = [index(name) for name in query.groupBy]
    filters = [(index(item.column), item.operator, item.value) for item in query.filters]
    metrics = [(item.function, index(item.column) if item.column else None, item.alias) for item in query.metrics]
    currency_columns = [i for i, header in enumerate(page["headers"]) if normalize(header) in {"currency", "moneda", "monedafacturacion"}]
    if any(function in {"sum", "mean"} for function, _, _ in metrics):
        for i in currency_columns:
            if i not in groups and not any(column == i and op == "eq" for column, op, _ in filters):
                fail("agent_mixed_currencies", "Agrupa o filtra la moneda del archivo antes de sumar o promediar sus importes.")
    selected = [row for row in page["rows"] if all(matches(row[i], page["types"][i], op, value) for i, op, value in filters)]
    if metrics:
        if columns:
            fail("agent_query_ambiguous", "Usa columns vacío para agrupar.")
        for function, i, _ in metrics:
            if (function == "count_rows") != (i is None) or function in {"sum", "mean"} and page["types"][i] != "number":
                fail("agent_metric_invalid", "Selecciona una columna numérica para sumar/promediar; count_rows usa column vacío.")
        grouped = {}
        for row in selected:
            grouped.setdefault(tuple(row[i] for i in groups), []).append(row)
        if not groups and not selected:
            grouped[()] = []
        output = []
        for key, members in grouped.items():
            values = [typed(value, page["types"][i], strict=False) for value, i in zip(key, groups)]
            for function, i, _ in metrics:
                if function == "count_rows":
                    value = len(members)
                elif function == "count_distinct":
                    value = len({str(row[i]) for row in members if not empty(row[i])})
                else:
                    candidates = [typed(row[i], page["types"][i], strict=True) for row in members]
                    value = None if not candidates or any(item is None for item in candidates) else (
                        sum(candidates, Decimal(0)) if function == "sum" else
                        sum(candidates, Decimal(0)) / len(candidates) if function == "mean" else
                        min(candidates) if function == "min" else max(candidates))
                values.append(value)
            output.append(values)
        headers = [page["headers"][i] for i in groups] + [alias for _, _, alias in metrics]
        types = [page["types"][i] for i in groups] + ["number" if function in {"count_rows", "count_distinct", "sum", "mean"} else page["types"][i] for function, i, _ in metrics]
    else:
        if groups or not columns:
            fail("agent_query_ambiguous", "Selecciona columnas o métricas para el archivo adjunto.")
        headers, types = [page["headers"][i] for i in columns], [page["types"][i] for i in columns]
        output = [[typed(row[i], page["types"][i], strict=False) for i in columns] for row in selected]
    if len({normalize(header) for header in headers}) != len(headers):
        fail("agent_column_duplicate", "Los nombres del resultado deben ser únicos.")
    positions = {normalize(header): i for i, header in enumerate(headers)}
    for item in reversed(query.orderBy):
        if normalize(item.column) not in positions:
            fail("agent_sort_unknown", "Ordena por una columna del resultado.")
        i = positions[normalize(item.column)]
        output = sorted([row for row in output if not empty(row[i])], key=lambda row: sort_key(row[i]), reverse=item.direction == "desc") + [row for row in output if empty(row[i])]
    source = {"source": "conversation_attachment", "attachmentId": document.id, "name": document.original_name,
              "sha256": document.sha256, "sheet": page["name"], "warnings": json.loads(upload.metadata_json)["warnings"]}
    def unit(i):
        header = page["headers"][i]
        key = normalize(header)
        if page["types"][i] != "number":
            return ""
        return "USD" if key.endswith("usd") or key == "valordolares" else "MXN" if key.endswith("mxn") else "source:" + header
    units = ([unit(i) for i in groups] + [unit(i) if i is not None and function not in {"count_rows", "count_distinct"} else "" for function, i, _ in metrics]) if metrics else [unit(i) for i in columns]
    return QueryResult(headers, types, output, [source], len(page["rows"]), len(selected), query.model_dump(), units=units)


def preview_file(result, offset, limit, text_offset=0, text_limit=1000):
    preview = result.preview(0)
    # The underlying data and exports remain complete. Only tool text is capped.
    text_limited, budget, items, continuations = False, 20_000, [], []
    for row_index, row in enumerate(result.rows[offset:offset + limit], offset):
        item = {}
        for header, value in zip(result.headers, row):
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            if isinstance(value, Decimal):
                value = float(value)
            if isinstance(value, str):
                maximum = max(0, min(text_limit, budget))
                total = len(value)
                value = value[text_offset:text_offset + maximum]
                if total > text_offset + len(value):
                    continuations.append({"resultRow": row_index, "column": header,
                                          "nextTextOffset": text_offset + len(value), "totalCharacters": total})
                if text_offset or total > len(value):
                    text_limited = True
                budget -= len(value)
            item[header] = value
        items.append(item)
    preview.update(items=items, offset=offset, previewLimited=offset > 0 or offset + limit < len(result.rows),
                   nextOffset=offset + len(items) if offset + len(items) < len(result.rows) else None,
                   previewTextLimited=text_limited, textOffset=text_offset, textContinuations=continuations)
    return preview
