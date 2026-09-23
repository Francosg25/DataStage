"""Dedicated, typed DataStage tables and transactional bulk inserts.

Business columns are explicit and frozen in catalog.py. Schema additions go to a
separate extension table belonging to that type, until reviewed and promoted by
a migration. Dates always have a datetime column and their original text.
"""
from datetime import datetime
import json
import re
import unicodedata

from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Table, Unicode, UnicodeText, UniqueConstraint
from sqlalchemy.dialects.mssql import NVARCHAR

from . import Base
from .catalog import BUSINESS_HEADERS
from .models import UTCDateTime, utcnow

LargeText = UnicodeText().with_variant(NVARCHAR(None), "mssql")
RowId = BigInteger().with_variant(Integer(), "sqlite")


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower())


def column_name(header: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", ascii_name)
    ascii_name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", ascii_name)
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")


def is_date(header: str) -> bool:
    key = normalize_header(header)
    if "tipofecha" in key or key in {"numerofecha", "secuenciafecha"}:
        return False
    return key.startswith("fecha")


BUSINESS_TABLES: dict[str, Table] = {}
EXTENSION_TABLES: dict[str, Table] = {}
HEADER_COLUMNS: dict[str, dict[str, str]] = {}

for _code, _headers in BUSINESS_HEADERS.items():
    _name = "ds_" + _code
    _columns = [
        Column("id", RowId, primary_key=True, autoincrement=True),
        Column("period_id", String(36), ForeignKey("periods.id"), nullable=False),
        Column("processing_run_id", String(36), ForeignKey("processing_runs.id"), nullable=False),
        Column("processing_file_id", String(36), ForeignKey("processing_files.id"), nullable=False),
        Column("archivo_origen", Unicode(512), nullable=False),
        Column("folio_origen", Unicode(512), nullable=False),
        Column("table_code", Unicode(100), nullable=False),
        Column("ingested_at", UTCDateTime, nullable=False, default=utcnow),
        Column("source_row_number", Integer, nullable=False),
        Column("original_dates_json", LargeText, nullable=False, default="{}"),
    ]
    HEADER_COLUMNS[_code] = {}
    for _header in _headers:
        _column = column_name(_header)
        HEADER_COLUMNS[_code][normalize_header(_header)] = _column
        _type = UTCDateTime if is_date(_header) else Unicode(450) if _column == "pedimento_completo" else LargeText
        _columns.append(Column(_column, _type, nullable=True))
    _table = Table(
        _name, Base.metadata, *_columns,
        UniqueConstraint("processing_run_id", "processing_file_id", "source_row_number", name="uq_" + _name + "_source"),
        Index("ix_" + _name + "_period", "period_id"),
        Index("ix_" + _name + "_run", "processing_run_id"),
    )
    if "pedimento_completo" in _table.c:
        Index("ix_" + _name + "_pedimento", _table.c.pedimento_completo)
    BUSINESS_TABLES[_code] = _table
    # Per-type extension tables preserve novel columns without a catch-all data table.
    EXTENSION_TABLES[_code] = Table(
        _name + "_extensions", Base.metadata,
        Column("id", RowId, primary_key=True, autoincrement=True),
        Column("business_row_id", RowId, ForeignKey(_name + ".id"), nullable=False),
        Column("header_key", Unicode(200), nullable=False),
        Column("original_header", Unicode(512), nullable=False),
        Column("original_value", LargeText, nullable=False),
        Column("date_value", UTCDateTime, nullable=True),
        Column("value_kind", String(10), nullable=False),
        UniqueConstraint("business_row_id", "header_key", name="uq_" + _name + "_extension_header"),
    )


def get_business_table(code: str) -> Table | None:
    return BUSINESS_TABLES.get(str(code).strip().lower())


def _datetime_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise ValueError("Business dates cannot contain an implicit timezone conversion")
        return value if 1900 <= value.year <= 2100 else None
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value))
        return result if result.tzinfo is None and 1900 <= result.year <= 2100 else None
    except ValueError:
        return None


def persist_business_rows(session, run_id: str, table: dict, period_lookup: dict) -> int:
    """Insert one known DataStage table inside the caller's transaction.

    Expects engine rows aligned to headers and rowSources containing fileId,
    fileName, period, folio, rowNumber and originalDates. No commit is performed.
    Unknown table codes remain represented by the immutable result document.
    Repeating an insert raises an integrity error; callers roll back the unit of
    work and retain their prior published version.
    """
    code = str(table.get("tableCode", table.get("code", ""))).lower()
    target = get_business_table(code)
    if target is None:
        return 0
    rows = table.get("rows", [])
    sources = table.get("rowSources", [])
    headers = table.get("headers", [])
    if len(rows) != len(sources):
        raise ValueError("Each business row must have exactly one source record")
    header_columns = HEADER_COLUMNS[code]
    session.flush()
    pending = []
    count = 0
    for values, source in zip(rows, sources, strict=True):
        if len(values) != len(headers):
            raise ValueError("Business row is not aligned to table headers")
        period = period_lookup.get(source["period"])
        if period is None:
            raise ValueError(f"Missing registered period: {source['period']}")
        original_dates = dict(source.get("originalDates", {}))
        dates_by_key = {normalize_header(header): value for header, value in original_dates.items()}
        item = {
            "period_id": period.id if hasattr(period, "id") else period,
            "processing_run_id": run_id,
            "processing_file_id": source["fileId"],
            "archivo_origen": source["fileName"],
            "folio_origen": source.get("folio", ""),
            "table_code": code,
            "ingested_at": utcnow(),
            "source_row_number": source["rowNumber"],
            "original_dates_json": json.dumps(original_dates, ensure_ascii=False),
        }
        # Identical mapping keys are required for efficient executemany inserts.
        for name in header_columns.values():
            item[name] = None
        extras = []
        for header, value in zip(headers, values, strict=True):
            key = normalize_header(header)
            if key in {"periodo", "archivoorigen", "folioorigen"}:
                continue
            name = header_columns.get(key)
            if name:
                if is_date(header):
                    item[name] = _datetime_value(value)
                    if key not in dates_by_key and value is not None:
                        original_dates[key] = str(value)
                else:
                    text_value = "" if value is None else str(value)
                    if name == "pedimento_completo" and len(text_value) > 450:
                        raise ValueError("PedimentoCompleto exceeds the indexed column length (450)")
                    item[name] = text_value
            else:
                if len(key) > 200 or len(header) > 512:
                    raise ValueError("Extension header exceeds the schema limit")
                extras.append({
                    "header_key": key,
                    "original_header": header,
                    "original_value": dates_by_key.get(key, "" if value is None else str(value)),
                    "date_value": _datetime_value(value) if is_date(header) else None,
                    "value_kind": "date" if is_date(header) else "text",
                })
        item["original_dates_json"] = json.dumps(original_dates, ensure_ascii=False)
        if extras:
            if pending:
                session.execute(target.insert(), pending)
                pending.clear()
            row_id = session.execute(target.insert().values(**item)).inserted_primary_key[0]
            session.execute(EXTENSION_TABLES[code].insert(), [{"business_row_id": row_id, **extra} for extra in extras])
        else:
            pending.append(item)
            if len(pending) >= 500:
                session.execute(target.insert(), pending)
                pending.clear()
        count += 1
    if pending:
        session.execute(target.insert(), pending)
    return count
