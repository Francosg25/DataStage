import json
from datetime import datetime
from sqlalchemy import func, select
from app.core.errors import ApplicationError
from app.modules.engine import TABLE_NAMES, normalize_header, parse_period
from app.modules.processing.service import get_document, get_run, run_response
from app.persistence import get_business_table
from app.persistence.business import EXTENSION_TABLES, HEADER_COLUMNS
from app.persistence.catalog import BUSINESS_HEADERS
from app.persistence.models import Period, ProcessingTable, Run

def overview(session, scope):
    periods = list(session.scalars(select(Period).where(Period.scope_id == scope).order_by(Period.year, Period.month)))
    monthly = []
    for period in periods:
        if period.active_run_id:
            run = session.get(Run, period.active_run_id)
            counts = json.loads(run.counts_json or "{}")
            monthly.append({"period": period.name, "rows": counts.get("rows", 0),
                            "files": counts.get("processedFiles", 0), "warnings": counts.get("warnings", 0),
                            "errors": counts.get("errors", 0)})
    recent = list(session.scalars(select(Run).where(Run.scope_id == scope).order_by(Run.created_at.desc()).limit(8)))
    return {"periodsCount": len(monthly),
            "runsCount": session.scalar(select(func.count()).select_from(Run).where(Run.scope_id == scope)),
            "rowsCount": sum(item["rows"] for item in monthly),
            "warningCount": sum(item["warnings"] for item in monthly),
            "errorCount": sum(item["errors"] for item in monthly),
            "monthly": monthly, "recentRuns": [run_response(session, run) for run in recent]}

def data_page(session, scope, code, period_text=None, run_id=None, offset=0, limit=100, storage=None):
    code = code.strip().lower()
    canonical = None
    if period_text:
        try:
            _, _, canonical = parse_period(period_text)
        except ValueError:
            raise ApplicationError(400, "INVALID_PERIOD", "Periodo no válido") from None
    table = get_business_table(code)
    if table is None:
        raise ApplicationError(404, "TABLE_NOT_REGISTERED", "La tabla no tiene un esquema SQL registrado")
    source = table.join(Run, table.c.processing_run_id == Run.id).join(Period, table.c.period_id == Period.id)
    conditions = [Run.scope_id == scope]
    if run_id:
        run = get_run(session, run_id, scope)
        if run.publication_status != "published":
            raise ApplicationError(409, "NOT_PUBLISHED", "La versión no está publicada")
        if run.kind == "annual":
            if storage is None:
                raise ApplicationError(503, "SNAPSHOT_UNAVAILABLE", "El resultado anual no está disponible")
            # The annual parser has its own frozen options and source versions.
            # Read its immutable result to match Excel without duplicating monthly SQL rows.
            document = get_document(session, run.result_document_id, scope)
            result = json.loads(storage.read_bytes(document.storage_key))
            output = next((item for item in result["tables"] if item["tableCode"] == code), None)
            if output is None:
                return {"headers": [], "items": [], "total": 0, "tableName": TABLE_NAMES[code]}
            headers = output["headers"]
            rows = output["rows"]
            if canonical:
                index = next(i for i, header in enumerate(headers) if normalize_header(header) == "periodo")
                rows = [row for row in rows if row[index] == canonical]
            return {"headers": headers, "items": [dict(zip(headers, row)) for row in rows[offset:offset + limit]],
                    "total": len(rows), "tableName": TABLE_NAMES[code]}
        conditions.append(Run.id == run_id)
    else:
        conditions.append(Period.active_run_id == Run.id)
    if canonical:
        conditions.append(Period.name == canonical)
    total = session.scalar(select(func.count()).select_from(source).where(*conditions))
    records = list(session.execute(select(table, Period.name.label("_period_name")).select_from(source)
                                  .where(*conditions).order_by(table.c.id).offset(offset).limit(limit)).mappings())
    run_ids = select(table.c.processing_run_id).select_from(source).where(*conditions).distinct()
    schemas = list(session.scalars(select(ProcessingTable).where(ProcessingTable.table_code == code,
                                   ProcessingTable.run_id.in_(run_ids)).order_by(ProcessingTable.run_id)))
    headers, seen = [], set()
    for schema in schemas:
        for header in json.loads(schema.headers_json):
            key = normalize_header(header)
            if key not in seen:
                seen.add(key)
                headers.append(header)
    if not headers:
        headers = ["Periodo", "ArchivoOrigen", "FolioOrigen", *BUSINESS_HEADERS[code]]
    extension = EXTENSION_TABLES[code]
    extra_by_row = {}
    if records:
        extras = session.execute(select(extension).where(extension.c.business_row_id.in_([r["id"] for r in records]))).mappings()
        for extra in extras:
            extra_by_row.setdefault(extra["business_row_id"], {})[extra["header_key"]] = extra
    items = []
    for record in records:
        originals = json.loads(record["original_dates_json"])
        item = {}
        for header in headers:
            key = normalize_header(header)
            if key in ("periodo", "archivoorigen", "folioorigen"):
                value = {"periodo": record["_period_name"], "archivoorigen": record["archivo_origen"],
                         "folioorigen": record["folio_origen"]}[key]
            elif key in HEADER_COLUMNS[code]:
                value = record[HEADER_COLUMNS[code][key]]
                if value is None:
                    value = originals.get(key, originals.get(header, ""))
            else:
                extra = extra_by_row.get(record["id"], {}).get(key)
                value = (extra["date_value"] or extra["original_value"]) if extra else ""
            item[header] = value.isoformat(timespec="seconds") if isinstance(value, datetime) else value
        items.append(item)
    return {"headers": headers, "items": items, "total": total, "tableName": TABLE_NAMES[code]}

def compare_periods(session, scope, first, second):
    output = []
    for text in (first, second):
        try:
            _, _, canonical = parse_period(text)
        except ValueError:
            raise ApplicationError(400, "INVALID_PERIOD", "Periodo no válido") from None
        period = session.scalar(select(Period).where(Period.scope_id == scope, Period.name == canonical))
        if not period or not period.active_run_id:
            raise ApplicationError(404, "PERIOD_UNAVAILABLE", f"No hay versión publicada de {canonical}")
        run = session.get(Run, period.active_run_id)
        output.append({"period": canonical, "runId": run.id, "version": period.version,
                       "counts": json.loads(run.counts_json)})
    return {"periods": output, "rowDifference": output[1]["counts"].get("rows", 0) - output[0]["counts"].get("rows", 0)}
