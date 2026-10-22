"""Read-only joins at a declared grain. No model-supplied keys, SQL or programs."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext
import json
import re

from sqlalchemy import select

from app.modules.engine import normalize_header
from app.modules.engine.exporter import MONEY_HEADERS
from app.persistence.business import BUSINESS_TABLES, HEADER_COLUMNS, is_date
from app.persistence.catalog import BUSINESS_HEADERS
from app.persistence.models import ProcessingTable
from . import data_queries as data

DECLARATION_KEYS = ("Patente", "Pedimento", "SeccionAduanera")
ITEM_KEYS = (*DECLARATION_KEYS, "Fraccion", "SecuenciaFraccion")
MXN_FIELDS = {"ImportePago", "ValorAduana", "ValorComercial", "TotalFletes", "TotalSeguros",
              "TotalEmbalajes", "TotalIncrementables", "TotalDeducibles"}


def relations_for(code):
    headers = set(BUSINESS_HEADERS.get(code, []))
    return [{"tableCode": target, "keys": ["Periodo", *keys], "cardinality": "many-to-one",
             "kinds": ["left", "inner"], "requiresUniqueTarget": True}
            for target, keys in (("501", DECLARATION_KEYS), ("551", ITEM_KEYS))
            if code != target and set(keys).issubset(headers)]


@dataclass(frozen=True)
class Column:
    kind: str
    unit: str
    dependencies: frozenset[str]
    currencies: frozenset[str] = frozenset()


def column_info(code, header):
    ref = f"{code}.{header}"
    kind = data.column_type(header)
    currencies = frozenset({f"{code}.MonedaFacturacion"}) if header == "ValorMonedaExtranjera" else frozenset()
    unit = ("USD" if header == "ValorDolares" else "MXN" if header in MXN_FIELDS else
            "MXN/USD" if header == "TipoCambio" else f"currency:{code}.MonedaFacturacion" if currencies else
            f"source:{ref}" if normalize_header(header) in MONEY_HEADERS else "")
    return Column(kind, unit, frozenset({ref}), currencies)


def calculated_unit(left, right, operator, literal):
    a, b = left.unit, right.unit
    if operator in {"add", "subtract", "percent_of", "percent_change"}:
        if a != b and not literal:
            data.fail("agent_mixed_units", "El cálculo combina monedas o unidades distintas. Usa el tipo de cambio o métricas oficiales.")
        return "%" if operator.startswith("percent_") else a
    if operator == "multiply":
        if not a or not b:
            return a or b
        if {a, b} == {"USD", "MXN/USD"}:
            return "MXN"
    elif operator == "divide":
        if not b:
            return a
        if a == b:
            return ""
        if a == "MXN" and b == "MXN/USD":
            return "USD"
    data.fail("agent_mixed_units", "No hay una conversión de unidades definida para ese cálculo.")


def load_rows(session, code, required, sources, budget):
    target = BUSINESS_TABLES[code]
    source_names = {source["runId"]: source["period"] for source in sources}
    covered = set(session.scalars(select(ProcessingTable.run_id).where(
        ProcessingTable.run_id.in_(source_names), ProcessingTable.table_code == code)))
    if covered != set(source_names):
        data.fail("agent_table_unavailable", "Una tabla del cruce no tiene cobertura en todos los meses seleccionados.", 404)
    selected = [target.c.id, target.c.processing_run_id]
    for header in sorted(required - {"Periodo"}):
        column = {"ArchivoOrigen": "archivo_origen", "FolioOrigen": "folio_origen"}.get(header)
        column = column or HEADER_COLUMNS[code][normalize_header(header)]
        selected.append(target.c[column].label(header))
    if any(is_date(header) for header in required):
        selected.append(target.c.original_dates_json)
    rows = session.execute(select(*selected).where(target.c.processing_run_id.in_(source_names))
                           .order_by(target.c.id).limit(budget + 1)).mappings().all()
    if len(rows) > budget:
        data.fail("agent_query_too_large", "El cruce supera 50,000 filas de origen entre todas sus tablas. Reduce los meses; no se calculó un resultado parcial.", 413)
    output = []
    for raw in rows:
        record = {"Periodo": source_names[raw["processing_run_id"]], "_run": raw["processing_run_id"], "_id": raw["id"]}
        original = json.loads(raw.get("original_dates_json", "{}"))
        for header in required - {"Periodo"}:
            value = raw[header]
            if value is None and is_date(header):
                value = original.get(normalize_header(header), original.get(header, ""))
            record[header] = value
        output.append(record)
    return output


def identity(record, keys):
    values = [data.normalized_code(record[key]) for key in keys]
    if any(value is None for value in values):
        data.fail("agent_join_key_invalid", "Una relación tiene llaves incompletas. Corrige la fuente antes de cruzar; no se han omitido esas filas.")
    return (record["_run"], *values)


def query_related(session, scope, query):
    base = query.tableCode
    if base not in BUSINESS_HEADERS:
        data.fail("agent_table_unknown", "La tabla no está en el catálogo autorizado.")
    allowed = {relation["tableCode"]: relation for relation in relations_for(base)}
    targets = [join.tableCode for join in query.joins]
    if len(set(targets)) != len(targets) or any(code not in allowed for code in targets):
        data.fail("agent_join_forbidden", "El cruce no está en el catálogo de relaciones de la tabla base. Usa la tabla de mayor detalle y consulta describe_data.")
    codes = [base, *targets]
    info, lookup = {}, {}
    required = {code: set() for code in codes}
    for code in codes:
        for header in data.META_HEADERS + BUSINESS_HEADERS[code]:
            ref = f"{code}.{header}"
            info[ref] = column_info(code, header)
            lookup[normalize_header(ref)] = ref
            if code == base:
                lookup[normalize_header(header)] = ref

    def canonical(name):
        ref = lookup.get(normalize_header(name))
        if ref is None:
            data.fail("agent_column_unknown", "Una columna no existe en las tablas del cruce. Consulta describe_data y usa tabla.Campo.")
        return ref

    # Plan every calculation before reading data; expressions reference only prior fields.
    calculations = []
    for calculation in query.calculations:
        left = canonical(calculation.left)
        right = canonical(calculation.right) if calculation.rightIsColumn else None
        literal = None
        if right is None:
            if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", calculation.right):
                data.fail("agent_calculation_invalid", "La constante debe ser un decimal sin separadores, código ni fórmulas.")
            literal = Decimal(calculation.right)
        a, b = info[left], info[right] if right else Column("number", "", frozenset())
        if a.kind != "number" or b.kind != "number":
            data.fail("agent_calculation_invalid", "Las operaciones requieren columnas numéricas del catálogo.")
        if normalize_header(calculation.alias) in lookup:
            data.fail("agent_column_duplicate", "El alias de cálculo coincide con otra columna o alias.")
        unit = calculated_unit(a, b, calculation.operator, right is None)
        info[calculation.alias] = Column("number", unit, a.dependencies | b.dependencies, a.currencies | b.currencies)
        lookup[normalize_header(calculation.alias)] = calculation.alias
        calculations.append((calculation.alias, calculation.operator, left, right, literal))

    columns, groups = [canonical(name) for name in query.columns], [canonical(name) for name in query.groupBy]
    filters = [(canonical(item.column), item.operator, item.value) for item in query.filters]
    metrics = [(item.function, canonical(item.column) if item.column else "", item.alias) for item in query.metrics]
    if metrics:
        if columns:
            data.fail("agent_query_ambiguous", "Una agrupación utiliza groupBy y metrics, con columns vacío.")
        for function, ref, _ in metrics:
            if (function == "count_rows") != (not ref):
                data.fail("agent_metric_invalid", "count_rows usa column vacío; las demás métricas requieren columna.")
            if function in {"sum", "mean"}:
                if info[ref].kind != "number":
                    data.fail("agent_metric_invalid", "Las sumas y promedios requieren columnas numéricas.")
                if function == "sum" and info[ref].unit in {"%", "MXN/USD"}:
                    data.fail("agent_metric_invalid", "No se suman porcentajes ni tipos de cambio. Selecciona el detalle o calcula una razón de totales.")
                for currency in info[ref].currencies:
                    if currency not in groups and not any(h == currency and op == "eq" for h, op, _ in filters):
                        data.fail("agent_mixed_currencies", "Agrupa o filtra MonedaFacturacion antes de agregar importes en moneda extranjera, también los calculados.")
            elif ref:
                for currency in info[ref].currencies:
                    if currency not in groups and not any(h == currency and op == "eq" for h, op, _ in filters):
                        data.fail("agent_mixed_currencies", "Separa MonedaFacturacion antes de comparar importes de distintas monedas.")
        headers = groups + [alias for _, _, alias in metrics]
        types = [info[ref].kind for ref in groups] + ["number" if function in {"count_rows", "count_distinct", "sum", "mean"} else info[ref].kind for function, ref, _ in metrics]
        units = [info[ref].unit for ref in groups] + [info[ref].unit if ref and function != "count_distinct" else "" for function, ref, _ in metrics]
    else:
        if groups or not columns:
            data.fail("agent_query_ambiguous", "Selecciona columnas de detalle o métricas de agrupación.")
        headers, types, units = columns, [info[ref].kind for ref in columns], [info[ref].unit for ref in columns]
    if len({normalize_header(header) for header in headers}) != len(headers):
        data.fail("agent_column_duplicate", "Los nombres del resultado deben ser únicos.")
    referenced = set(columns + groups + [ref for _, ref, _ in metrics if ref] + [ref for ref, _, _ in filters])
    referenced.update(alias for alias, *_ in calculations)
    for ref in referenced:
        for dependency in info[ref].dependencies:
            code, header = dependency.split(".", 1)
            required[code].add(header)
    for target in targets:
        keys = allowed[target]["keys"][1:]
        required[base].update(keys)
        required[target].update(keys)

    sources = data.published_sources(session, scope, query.periods)
    raw = load_rows(session, base, required[base], sources, data.MAX_SOURCE_ROWS)
    scanned = len(raw)
    records = [{**{f"{base}.{header}": row[header] for header in required[base]},
                "_base": row, "_joined": {}} for row in raw]
    diagnostics = {"baseTable": base, "baseGrain": data.GRAINS.get(base, "fila de origen"), "joins": [],
                   "unavailableCalculations": {}, "zeroDenominators": {}, "calculationSignificantDigits": 15}
    for join in query.joins:
        target, keys = join.tableCode, allowed[join.tableCode]["keys"][1:]
        related = load_rows(session, target, required[target], sources, data.MAX_SOURCE_ROWS - scanned)
        scanned += len(related)
        index = {}
        for row in related:
            key = identity(row, keys)
            if key in index:
                data.fail("agent_join_ambiguous", "La tabla relacionada tiene varias filas para la misma llave. El cruce duplicaría información; requiere depurar o agregar previamente la fuente.")
            index[key] = row
        matched, unmatched, joined = 0, 0, []
        for record in records:
            key = identity(record["_base"], keys)
            row = index.get(key)
            matched += row is not None
            unmatched += row is None
            if row is None and join.kind == "inner":
                continue
            record.update({f"{target}.{header}": row[header] if row else None for header in required[target]})
            record["_joined"][target] = key if row else None
            joined.append(record)
        records = joined
        diagnostics["joins"].append({"tableCode": target, "kind": join.kind, "keys": ["Periodo", *keys],
                                     "matchedBaseRows": matched, "unmatchedBaseRows": unmatched,
                                     "targetRows": len(related), "cardinality": "many-to-one"})

    for record in records:
        for alias, operator, left, right, literal in calculations:
            a = data.typed(record[left], "number", strict=True)
            b = data.typed(record[right], "number", strict=True) if right else literal
            if any(value is not None and value <= 0 and info[ref].unit == "MXN/USD"
                   for ref, value in ((left, a), (right, b)) if ref):
                data.fail("agent_invalid_source_value", "El tipo de cambio debe ser positivo. Corrige la fuente antes de convertir importes.")
            if a is None or b is None or b == 0 and operator in {"divide", "percent_of", "percent_change"}:
                record[alias] = None
                diagnostics["unavailableCalculations"][alias] = diagnostics["unavailableCalculations"].get(alias, 0) + 1
                if b == 0 and operator in {"divide", "percent_of", "percent_change"}:
                    diagnostics["zeroDenominators"][alias] = diagnostics["zeroDenominators"].get(alias, 0) + 1
                continue
            try:
                with localcontext() as context:
                    context.prec = 40
                    value = (a + b if operator == "add" else a - b if operator == "subtract" else
                             a * b if operator == "multiply" else a / b if operator == "divide" else
                             a / b * 100 if operator == "percent_of" else (a - b) / abs(b) * 100)
                if not value.is_finite() or abs(value.adjusted()) > 300:
                    raise ValueError("Unbounded result")
                # Excel supports 15 significant digits. Calculated outputs are explicitly
                # rounded to that precision; original source values are never rewritten.
                with localcontext() as context:
                    context.prec = 15
                    record[alias] = +value
            except (DecimalException, ValueError):
                data.fail("agent_calculation_invalid", "El resultado numérico excede los límites del cálculo.")
    records = [record for record in records if all(data.matches(record[ref], info[ref].kind, operator, value)
                                                   for ref, operator, value in filters)]
    for join in diagnostics["joins"]:
        keys = [record["_joined"][join["tableCode"]] for record in records
                if record["_joined"].get(join["tableCode"]) is not None]
        join["repeatedTargetRowsInDetail"] = sum(count - 1 for count in Counter(keys).values())
    rows = aggregate(records, groups, metrics, info) if metrics else [
        [data.typed(record[ref], info[ref].kind, strict=False) for ref in columns] for record in records]
    output_lookup = {normalize_header(header): index for index, header in enumerate(headers)}
    for order in reversed(query.orderBy):
        index = output_lookup.get(normalize_header(order.column))
        if index is None:
            index = output_lookup.get(normalize_header(canonical(order.column)))
        if index is None:
            data.fail("agent_sort_unknown", "Ordena por una columna o alias del resultado.")
        populated = [row for row in rows if not data.empty(row[index])]
        missing = [row for row in rows if data.empty(row[index])]
        populated.sort(key=lambda row: data.sort_key(row[index]), reverse=order.direction == "desc")
        rows = populated + missing
    return data.QueryResult(headers, types, rows, [source | {"tables": codes} for source in sources],
                            scanned, len(records), query.model_dump(), diagnostics, units)


def aggregate(records, groups, metrics, info):
    # Check across the ENTIRE filtered selection, not just each group: splitting
    # one declaration into two tariff groups must not allocate its full freight twice.
    for function, ref, _ in metrics:
        if function not in {"sum", "mean"}:
            continue
        for dependency in info[ref].dependencies:
            target, _ = dependency.split(".", 1)
            if info[dependency].kind != "number" or info[dependency].unit == "MXN/USD":
                continue
            keys = [record["_joined"].get(target) for record in records if record["_joined"].get(target) is not None]
            if any(count > 1 for count in Counter(keys).values()):
                data.fail("agent_join_repeated_measure", "El importe o medida de la tabla relacionada se repite en varias filas base. Agrégalo desde su propia tabla; no se ha inflado el total.")
    grouped = {}
    for record in records:
        key = tuple(data.normalized_code(record[ref]) if info[ref].kind == "code" else record[ref] for ref in groups)
        grouped.setdefault(key, []).append(record)
    if not groups and not records:
        grouped[()] = []
    rows = []
    for key, members in grouped.items():
        result = [data.typed(value, info[ref].kind, strict=False) for value, ref in zip(key, groups)]
        for function, ref, _ in metrics:
            if function == "count_rows":
                result.append(len(members))
                continue
            if function == "count_distinct":
                result.append(len({data.normalized_code(record[ref]) if info[ref].kind == "code" else str(record[ref]).strip()
                                   for record in members if not data.empty(record[ref])}))
                continue
            values = [data.typed(record[ref], info[ref].kind, strict=True) for record in members]
            if not values or any(value is None for value in values):
                result.append(None)
            elif function == "sum":
                result.append(sum(values, Decimal(0)))
            elif function == "mean":
                result.append(sum(values, Decimal(0)) / len(values))
            elif function == "min":
                result.append(min(values))
            else:
                result.append(max(values))
        rows.append(result)
    return rows
