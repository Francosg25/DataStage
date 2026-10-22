"""Bounded, parameterized business queries shared by chat previews and exports.

The model supplies a declarative specification, never SQL, Python or a connection.
Aggregations run on the complete authorized selection, never on the preview.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json

from sqlalchemy import select

from app.core.errors import ApplicationError
from app.modules.engine import TABLE_NAMES, normalize_header, parse_period
from app.modules.engine.exporter import CODE_HEADERS, COUNT_HEADERS, MEASURE_HEADERS, MONEY_HEADERS, TIME_HEADERS, _number_cell
from app.persistence.business import BUSINESS_TABLES, HEADER_COLUMNS, is_date
from app.persistence.catalog import BUSINESS_HEADERS
from app.persistence.models import Period, ProcessingTable, Run
from .tools import DataQuery

MAX_SOURCE_ROWS = 50_000
MAX_EXPORT_CELLS = 500_000
META_HEADERS = ["Periodo", "ArchivoOrigen", "FolioOrigen"]
GRAINS = {"501": "pedimento", "505": "factura", "551": "partida",
          "510": "contribución por pedimento", "557": "contribución por partida",
          "702": "contribución de rectificación", "701": "rectificación"}


def fail(code, message, status=400):
    raise ApplicationError(status, code, message)


def column_type(header):
    key = normalize_header(header)
    if is_date(header):
        return "date"
    if key in MONEY_HEADERS | MEASURE_HEADERS | COUNT_HEADERS:
        return "number"
    if key in TIME_HEADERS:
        return "time"
    if key in CODE_HEADERS:
        return "code"
    return "text"


def describe_data(code):
    from .relational_queries import column_info, relations_for
    if not code:
        return {"tables": [{"tableCode": key, "name": TABLE_NAMES.get(key, key),
                            "grain": GRAINS.get(key, "fila de la tabla de origen")}
                           for key in BUSINESS_HEADERS],
                "source": "active_published_monthly_runs", "maxSourceRows": MAX_SOURCE_ROWS,
                "rules": ["Un consolidado anual no prueba que estén todos sus meses.",
                          "count_rows cuenta filas; usa count_distinct PedimentoCompleto para pedimentos.",
                          "510, 557 y 702 son niveles distintos; 505 y 551 tampoco se suman entre sí.",
                          "Los cruces usan relaciones verificadas del catálogo: consulta describe_data para la tabla base.",
                          "Elige la tabla de mayor detalle como base. No se unen facturas con partidas sin una relación verificable."]}
    if code not in BUSINESS_HEADERS:
        fail("agent_table_unknown", "La tabla no está en el catálogo autorizado.")
    return {"tableCode": code, "name": TABLE_NAMES.get(code, code),
            "grain": GRAINS.get(code, "fila de la tabla de origen"),
            "columns": [{"name": header, "qualifiedName": f"{code}.{header}", "type": column_type(header),
                         "unit": column_info(code, header).unit}
                        for header in META_HEADERS + BUSINESS_HEADERS[code]],
            "filters": "eq/ne/contains; rangos numéricos y fechas ISO; is_empty/not_empty. Todos se combinan con AND.",
            "aggregation": "columns vacío; groupBy y metrics. count_rows usa column vacío. No se omiten valores numéricos inválidos.",
            "periods": "Nombres exactos del inventario mensual publicado; máximo 24.",
            "relationships": relations_for(code),
            "calculations": "add/subtract/multiply/divide/percent_of/percent_change por fila; alias reutilizable. Sin dato o división por cero: null, nunca cero inventado.",
            "joinRules": "Usa columnas calificadas (501.TipoCambio). Los cruces conservan como máximo una fila por fila base. Duplicados o llaves incompletas se rechazan. No sumes importes repetidos de una tabla de menor detalle.",
            "extensionColumns": "Las columnas no promovidas al catálogo requieren una incorporación explícita."}


def published_sources(session, scope, names):
    canonical = []
    for name in names:
        try:
            canonical.append(parse_period(name)[2])
        except ValueError:
            fail("agent_period_invalid", "Utiliza nombres de periodos válidos del inventario publicado.")
    if len(set(canonical)) != len(canonical):
        fail("agent_period_duplicate", "No repitas periodos en la misma consulta.")
    rows = session.execute(select(Period, Run).join(Run, Period.active_run_id == Run.id).where(
        Period.scope_id == scope, Run.scope_id == scope, Period.name.in_(canonical),
        Run.kind == "monthly", Run.publication_status == "published", Run.period_id == Period.id)
        .order_by(Period.year, Period.month)).all()
    if {period.name for period, _ in rows} != set(canonical):
        fail("agent_period_unavailable", "Uno o más periodos solicitados no tienen una versión mensual publicada en tu ámbito. Consulta list_runs.", 404)
    return [{"period": period.name, "periodId": period.id, "runId": run.id, "version": period.version}
            for period, run in rows]


@dataclass
class QueryResult:
    headers: list[str]
    types: list[str]
    rows: list[list]
    sources: list[dict]
    scanned_rows: int
    matched_rows: int
    specification: dict
    diagnostics: dict = field(default_factory=dict)
    units: list[str] = field(default_factory=list)

    def preview(self, limit):
        def value(item):
            return item.isoformat() if isinstance(item, datetime) else float(item) if isinstance(item, Decimal) else item
        result = {"headers": self.headers, "types": self.types,
                "items": [dict(zip(self.headers, [value(item) for item in row])) for row in self.rows[:limit]],
                "totalResultRows": len(self.rows), "matchedSourceRows": self.matched_rows,
                "scannedSourceRows": self.scanned_rows, "previewLimited": len(self.rows) > limit,
                "complete": True, "sources": self.sources, "query": self.specification}
        if self.diagnostics:
            result["diagnostics"] = self.diagnostics
        if self.units:
            result["units"] = dict(zip(self.headers, self.units))
        return result


def query_data(session, scope, specification):
    query = DataQuery.model_validate(specification)
    references = [*query.columns, *query.groupBy, *(item.column for item in query.filters),
                  *(item.column for item in query.metrics), *(item.column for item in query.orderBy)]
    if query.joins or query.calculations or any(name.startswith(f"{query.tableCode}.") for name in references):
        from .relational_queries import query_related
        return query_related(session, scope, query)
    code = query.tableCode
    table = BUSINESS_TABLES.get(code)
    if table is None:
        fail("agent_table_unknown", "La tabla no está en el catálogo autorizado.")
    headers = META_HEADERS + BUSINESS_HEADERS[code]
    lookup = {normalize_header(header): header for header in headers}

    def canonical(name):
        header = lookup.get(normalize_header(name))
        if header is None:
            fail("agent_column_unknown", "Una columna no existe en esta tabla. Consulta describe_data.")
        return header

    columns = [canonical(name) for name in query.columns]
    groups = [canonical(name) for name in query.groupBy]
    filters = [(canonical(item.column), item.operator, item.value) for item in query.filters]
    metrics = [(item.function, canonical(item.column) if item.column else "", item.alias) for item in query.metrics]
    if query.metrics:
        if columns:
            fail("agent_query_ambiguous", "En una agregación utiliza groupBy y metrics, con columns vacío.")
        for function, header, _ in metrics:
            if (function == "count_rows") != (not header):
                fail("agent_metric_invalid", "count_rows usa column vacío; las demás métricas requieren una columna.")
            if function in {"sum", "mean"} and column_type(header) != "number":
                fail("agent_metric_invalid", "Las sumas y promedios requieren una columna numérica del catálogo.")
        output_headers = groups + [alias for _, _, alias in metrics]
        types = [column_type(header) for header in groups] + [
            "number" if function in {"count_rows", "count_distinct", "sum", "mean"} else column_type(header)
            for function, header, _ in metrics]
        if any(header == "ValorMonedaExtranjera" and function in {"sum", "mean"} for function, header, _ in metrics):
            if "MonedaFacturacion" not in groups and not any(h == "MonedaFacturacion" and op == "eq" for h, op, _ in filters):
                fail("agent_mixed_currencies", "Agrupa por MonedaFacturacion o filtra una moneda antes de sumar valores en moneda extranjera.")
    else:
        if groups or not columns:
            fail("agent_query_ambiguous", "Indica columns para detalle o metrics para una agregación.")
        output_headers, types = columns, [column_type(header) for header in columns]
    if len(set(normalize_header(h) for h in output_headers)) != len(output_headers):
        fail("agent_column_duplicate", "Las columnas y alias del resultado deben ser únicos.")
    sources = published_sources(session, scope, query.periods)
    covered = set(session.scalars(select(ProcessingTable.run_id).where(
        ProcessingTable.run_id.in_([source["runId"] for source in sources]), ProcessingTable.table_code == code)))
    if covered != {source["runId"] for source in sources}:
        fail("agent_table_unavailable", "La tabla solicitada no tiene cobertura en todos los periodos seleccionados. Una tabla ausente no equivale a cero.", 404)
    # Select immutable run IDs once: replacements cannot cause mixed versions.
    source_names = {source["runId"]: source["period"] for source in sources}
    required = set(columns + groups + [h for h, _, _ in filters] + [h for _, h, _ in metrics if h])
    selected = [table.c.processing_run_id]
    for header in sorted(required - {"Periodo"}):
        column = {"ArchivoOrigen": "archivo_origen", "FolioOrigen": "folio_origen"}.get(header)
        column = column or HEADER_COLUMNS[code][normalize_header(header)]
        selected.append(table.c[column].label(header))
    if any(is_date(header) for header in required):
        selected.append(table.c.original_dates_json)
    raw_rows = session.execute(select(*selected).where(table.c.processing_run_id.in_(source_names))
                               .order_by(table.c.id).limit(MAX_SOURCE_ROWS + 1)).mappings().all()
    if len(raw_rows) > MAX_SOURCE_ROWS:
        fail("agent_query_too_large", "La selección supera 50,000 filas de origen. Reduce los meses; no se ha calculado un total parcial.", 413)
    records = []
    for raw in raw_rows:
        record = {"Periodo": source_names[raw["processing_run_id"]]}
        originals = json.loads(raw.get("original_dates_json", "{}"))
        for header in required - {"Periodo"}:
            record[header] = raw[header]
            if record[header] is None and is_date(header):
                record[header] = originals.get(normalize_header(header), originals.get(header, ""))
        if all(matches(record[header], column_type(header), operator, value) for header, operator, value in filters):
            records.append(record)
    if not metrics:
        result_rows = [[typed(record[header], column_type(header), strict=False) for header in columns] for record in records]
    else:
        grouped = {}
        for record in records:
            key = tuple(normalized_code(record[header]) if column_type(header) == "code" else record[header] for header in groups)
            grouped.setdefault(key, []).append(record)
        if not groups and not records:
            grouped[()] = []
        result_rows = []
        for key, members in grouped.items():
            values = []
            for function, header, _ in metrics:
                if function == "count_rows":
                    values.append(len(members))
                elif function == "count_distinct":
                    values.append(len({normalized_code(row[header]) if column_type(header) == "code" else str(row[header]).strip()
                                       for row in members if not empty(row[header])}))
                else:
                    actual = [typed(row[header], column_type(header), strict=True) for row in members if not empty(row[header])]
                    if not actual:
                        values.append(None)
                    elif function == "sum":
                        values.append(sum(actual, Decimal(0)))
                    elif function == "mean":
                        values.append(sum(actual, Decimal(0)) / len(actual))
                    elif function == "min":
                        values.append(min(actual))
                    else:
                        values.append(max(actual))
            result_rows.append([typed(value, column_type(header), strict=False) for header, value in zip(groups, key)] + values)
    output_lookup = {normalize_header(header): index for index, header in enumerate(output_headers)}
    for order in reversed(query.orderBy):
        index = output_lookup.get(normalize_header(order.column))
        if index is None:
            fail("agent_sort_unknown", "Ordena por una columna o alias del resultado.")
        # Nulls always last; all other keys are comparable even with invalid source text.
        populated = [row for row in result_rows if not empty(row[index])]
        missing = [row for row in result_rows if empty(row[index])]
        populated.sort(key=lambda row: sort_key(row[index]), reverse=order.direction == "desc")
        result_rows = populated + missing
    return QueryResult(output_headers, types, result_rows, sources, len(raw_rows), len(records), query.model_dump())


def empty(value):
    return value is None or isinstance(value, str) and not value.strip()


def typed(value, kind, *, strict):
    if empty(value):
        return None
    if kind == "number":
        numeric = _number_cell(value, money=True)
        if numeric is not None:
            return Decimal(str(numeric))
    elif kind == "date":
        if isinstance(value, datetime):
            return value
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                return parsed
        except ValueError:
            pass
    else:
        return str(value)
    if strict:
        fail("agent_invalid_source_value", "Hay valores no válidos para el cálculo solicitado. Consulta el detalle; no se han omitido ni convertido a cero.")
    return str(value)


def matches(value, kind, operator, expected):
    if operator == "is_empty":
        return empty(value)
    if operator == "not_empty":
        return not empty(value)
    if operator == "contains":
        if kind != "text":
            fail("agent_filter_invalid", "contains sólo se admite en columnas de texto.")
        return expected.casefold() in str(value or "").casefold()
    if empty(value):
        return False
    left, right = typed(value, kind, strict=True), typed(expected, kind, strict=True)
    if right is None:
        fail("agent_filter_invalid", "El filtro requiere un valor; usa is_empty/not_empty para celdas vacías.")
    if kind in {"text", "code", "time"}:
        if operator not in {"eq", "ne"}:
            fail("agent_filter_invalid", "Los rangos se aplican a números y fechas, no a identificadores de texto.")
        left, right = left.strip().casefold(), right.strip().casefold()
        if kind == "code":
            left, right = normalized_code(left), normalized_code(right)
    return {"eq": lambda: left == right, "ne": lambda: left != right, "gt": lambda: left > right,
            "gte": lambda: left >= right, "lt": lambda: left < right, "lte": lambda: left <= right}[operator]()


def sort_key(value):
    if isinstance(value, (int, float, Decimal)):
        return (0, value)
    if isinstance(value, datetime):
        return (1, value)
    return (2, str(value).casefold())


def normalized_code(value):
    if empty(value):
        return None
    numeric = _number_cell(value)
    return format(Decimal(str(numeric)).normalize(), "f") if numeric is not None else str(value).strip().casefold()
