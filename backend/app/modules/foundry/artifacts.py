"""Generate real, versioned files from approved queries, outside the model."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import json
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import xlsxwriter

from app.core.errors import ApplicationError
from app.modules.engine.exporter import EXCEL_MAX_TEXT, _code_cell, _number_cell
from app.modules.processing.service import audit, fingerprint
from app.modules.reporting.pdf_report import render_report
from app.persistence.models import AgentArtifact, StoredDocument
from .data_queries import MAX_EXPORT_CELLS, query_data

MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
FORMATS = {
    "xlsx": ("agent_excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pdf": ("agent_pdf", "application/pdf"),
    "docx": ("agent_docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "pptx": ("agent_pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "csv": ("agent_csv", "text/csv; charset=utf-8"), "json": ("agent_json", "application/json"),
    "png": ("agent_png", "image/png"), "svg": ("agent_svg", "image/svg+xml"),
    "html": ("agent_html", "text/html; charset=utf-8"), "zip": ("agent_zip", "application/zip"),
}


def attachment(document, conversation_id):
    return {"documentId": document.id, "name": document.original_name,
            "format": next(name for name, (kind, _) in FORMATS.items() if kind == document.kind),
            "sizeBytes": document.size_bytes, "sha256": document.sha256,
            "downloadUrl": f"/api/v1/agent/conversations/{conversation_id}/artifacts/{document.id}"}


def store_artifact(session, storage, principal, conversation_id, content, suffix, title, manifest):
    if suffix.lstrip(".") not in FORMATS:
        raise ApplicationError(400, "agent_format_unknown", "Formato de descarga no admitido.")
    request_hash = fingerprint({"format": suffix, "title": title, "manifest": manifest})
    existing = session.scalar(select(AgentArtifact).where(AgentArtifact.conversation_id == conversation_id,
                                                         AgentArtifact.request_hash == request_hash))
    if existing:
        doc = session.get(StoredDocument, existing.document_id)
        if doc.status != "available" or not storage.resolve(doc.storage_key).is_file():
            raise ApplicationError(503, "agent_artifact_unavailable", "El archivo generado no está disponible; solicita una nueva conversación.")
        return {"attachment": attachment(doc, conversation_id), "manifest": json.loads(existing.manifest_json)}
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ApplicationError(413, "agent_artifact_too_large", "El reporte supera 20 MiB. Reduce las columnas o periodos.")
    stored = storage.put_bytes(content, suffix)
    title = re.sub(r"[^\w -]+", "", title).strip().replace(" ", "_")[:80] or "DataStage"
    doc = StoredDocument(id=str(uuid4()), scope_id=principal.scope_id, kind=FORMATS[suffix.lstrip(".")][0],
                         original_name=f"{title}{suffix}", status="available", **stored)
    try:
        with session.begin_nested():
            session.add(doc)
            session.flush()
            session.add(AgentArtifact(document_id=doc.id, conversation_id=conversation_id,
                                      request_hash=request_hash, manifest_json=json.dumps(manifest, ensure_ascii=False)))
            session.flush()
    except IntegrityError:
        storage.resolve(stored["storage_key"]).unlink(missing_ok=True)
        existing = session.scalar(select(AgentArtifact).where(AgentArtifact.conversation_id == conversation_id,
                                                             AgentArtifact.request_hash == request_hash))
        if existing is None:
            raise
        doc = session.get(StoredDocument, existing.document_id)
    except BaseException:
        storage.resolve(stored["storage_key"]).unlink(missing_ok=True)
        raise
    audit(session, principal.scope_id, principal.id, "agent.artifact", documentId=doc.id,
          conversationId=conversation_id, format=suffix, sources=manifest.get("sources", []))
    return {"attachment": attachment(doc, conversation_id), "manifest": manifest}


def create_excel(session, storage, principal, conversation_id, specification, language):
    queries, sheets = [], []
    names = set()
    cells = 0
    metadata_name = "Sources" if language == "en" else "Fuentes"
    for sheet in specification["sheets"]:
        name = sheet["name"]
        if re.search(r"[\[\]:*?/\\]", name) or name.startswith("'") or name.endswith("'") or name.casefold() in names | {metadata_name.casefold()}:
            raise ApplicationError(400, "agent_sheet_name", "Utiliza nombres únicos de hoja, sin []:*?/\\ ni el nombre de la hoja de fuentes.")
        names.add(name.casefold())
        result = query_data(session, principal.scope_id, sheet["query"])
        cells += (len(result.rows) + 1) * len(result.headers)
        if cells > MAX_EXPORT_CELLS:
            raise ApplicationError(413, "agent_export_too_large", "El libro supera 500,000 celdas. Reduce columnas o periodos; no se ha truncado.")
        if any(len(str(value)) > EXCEL_MAX_TEXT for row in [result.headers, *result.rows] for value in row):
            raise ApplicationError(413, "agent_cell_too_large", "Un valor excede el tamaño de celda de Excel; no se ha truncado.")
        queries.append(result)
        table_codes = [result.specification["tableCode"], *(join["tableCode"] for join in result.specification.get("joins", []))]
        sheets.append({"name": name, "tableCode": result.specification["tableCode"], "tableCodes": table_codes, "rows": len(result.rows),
                       "matchedSourceRows": result.matched_rows, "scannedSourceRows": result.scanned_rows,
                       "query": result.specification, "sources": result.sources,
                       "diagnostics": result.diagnostics, "columnUnits": dict(zip(result.headers, result.units))})
    sources = {}
    for sheet in sheets:
        for source in sheet["sources"]:
            previous = sources.get(source["runId"], {})
            tables = set(previous.get("tables", [])) | set(sheet["tableCodes"])
            sources[source["runId"]] = source | {"tables": sorted(tables)}
    manifest = {"title": specification["title"], "language": language, "complete": True, "sheets": sheets,
                "sources": list(sources.values())}
    stream = BytesIO()
    preserved_as_text = 0
    with xlsxwriter.Workbook(stream, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}) as book:
        number = book.add_format({"num_format": "#,##0.##########"})
        date = book.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
        text = book.add_format({"num_format": "@"})
        code_formats = {}
        heading = book.add_format({"bold": True, "font_color": "white", "bg_color": "#145C56"})
        for index, (sheet, result) in enumerate(zip(sheets, queries)):
            page = book.add_worksheet(sheet["name"])
            for column, header in enumerate(result.headers):
                page.write_string(0, column, header, heading)
            for row_index, row in enumerate(result.rows, start=1):
                for column, (value, kind) in enumerate(zip(row, result.types)):
                    if value is None:
                        continue
                    if isinstance(value, datetime):
                        page.write_datetime(row_index, column, value, date)
                    elif kind == "number" and isinstance(value, (int, Decimal)) and _number_cell(value) is not None:
                        page.write_number(row_index, column, float(value), number)
                    elif kind == "code" and _code_cell(value) is not None:
                        raw = str(value).strip()
                        width = len(raw) if raw.startswith("0") else 1
                        if width not in code_formats:
                            code_formats[width] = book.add_format({"num_format": "0" * width})
                        page.write_number(row_index, column, _code_cell(value), code_formats[width])
                    else:
                        page.write_string(row_index, column, str(value), text)
                        preserved_as_text += int(kind in {"number", "date"})
            page.freeze_panes(1, 0)
            page.set_row(0, 30)
            page.set_column(0, len(result.headers) - 1, 23)
            if result.rows:
                page.add_table(0, 0, len(result.rows), len(result.headers) - 1,
                               {"name": f"DataStage{index + 1}", "style": "Table Style Medium 2",
                                "columns": [{"header": header} for header in result.headers]})
            else:
                page.autofilter(0, 0, 0, len(result.headers) - 1)
        manifest["preservedAsTextCells"] = preserved_as_text
        source_page = book.add_worksheet(metadata_name)
        source_headers = ["Sheet", "Table", "Period", "Run ID", "Version", "Result rows", "Query"]
        for column, header in enumerate(source_headers):
            source_page.write_string(0, column, header, heading)
        row_index = 1
        for sheet in sheets:
            for source in sheet["sources"]:
                row = [sheet["name"], " + ".join(sheet["tableCodes"]), source["period"], source["runId"], source["version"],
                       sheet["rows"], json.dumps(sheet["query"], ensure_ascii=False)]
                for column, value in enumerate(row):
                    if isinstance(value, int):
                        source_page.write_number(row_index, column, value)
                    else:
                        source_page.write_string(row_index, column, str(value), text)
                row_index += 1
        source_page.set_column(0, 5, 25)
        source_page.set_column(6, 6, 70)
        source_page.write_string(row_index + 1, 0, f"Values preserved as text (invalid date/number or Excel precision): {preserved_as_text}")
        for sheet in sheets:
            if sheet["diagnostics"]:
                row_index += 1
                source_page.write_string(row_index + 2, 0, sheet["name"], text)
                source_page.write_string(row_index + 2, 1, json.dumps(sheet["diagnostics"], ensure_ascii=False), text)
                source_page.write_string(row_index + 2, 2, json.dumps(sheet["columnUnits"], ensure_ascii=False), text)
    return store_artifact(session, storage, principal, conversation_id, stream.getvalue(), ".xlsx", specification["title"], manifest)


def create_analysis_report(session, storage, principal, conversation_id, report, language):
    sources = list(report["sources"]) + [
        {"year": report["year"], "month": month["month"], "runId": month["runId"], "version": month["version"]}
        for month in report["monthly"] if month["available"] and month.get("runId")]
    manifest = {"snapshotId": report["snapshotId"], "year": report["year"], "startMonth": report["startMonth"],
                "endMonth": report["endMonth"], "currency": report["currency"], "language": language,
                "sources": sources}
    title = f"DataStage_{report['year']}_{report['startMonth']:02d}-{report['endMonth']:02d}_{report['currency']}"
    return store_artifact(session, storage, principal, conversation_id, render_report(report, language), ".pdf", title, manifest)
