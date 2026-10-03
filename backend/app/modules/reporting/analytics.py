"""Read-only trade analytics. Aggregate each grain separately; never fan out joins."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path

from sqlalchemy import select

from app.core.errors import ApplicationError
from app.persistence.business import BUSINESS_TABLES
from app.persistence.models import Period, ProcessingTable, Run

KEY_FIELDS = ('patente', 'pedimento', 'seccion_aduanera')
FIELDS = {
    '501': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'tipo_pedimento',
            'peso_bruto_mercancia', 'total_fletes', 'total_seguros', 'total_embalajes',
            'total_incrementables', 'total_deducibles', 'medio_transporte_entrada_salida'),
    '551': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'fraccion', 'secuencia_fraccion',
            'valor_dolares', 'valor_aduana', 'valor_comercial', 'pais_origen_destino'),
    '505': (*KEY_FIELDS, 'proveedor_mercancia', 'pais_facturacion', 'termino_facturacion', 'valor_dolares'),
    '510': (*KEY_FIELDS, 'clave_contribucion', 'forma_pago', 'importe_pago'),
    '557': (*KEY_FIELDS, 'clave_contribucion', 'forma_pago', 'importe_pago'),
    '702': (*KEY_FIELDS, 'clave_contribucion', 'forma_pago', 'importe_pago'),
    '701': KEY_FIELDS,
    'sel': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'semaforo_fiscal'),
    'inci': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'grado_incidencia'),
}


def text_value(value):
    return '' if value is None else str(value).strip()


def identity(row):
    # Numeric identifiers in Excel and zero-padded ASC identifiers must agree.
    values = [text_value(row.get(f)) for f in KEY_FIELDS]
    if not all(values):
        return None
    return (row['year'], row['month'], *(v.lstrip('0') or '0' for v in values))


def number(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        parsed = Decimal(str(value).strip())
        return parsed if parsed.is_finite() else None
    except InvalidOperation:
        return None


def total(rows, field):
    values = [v for row in rows if (v := number(row.get(field))) is not None]
    return float(sum(values, Decimal(0))) if values else (0.0 if not rows else None)


def change(current, previous):
    return None if current is None or previous in (None, 0) else round((current - previous) / abs(previous) * 100, 2)


@lru_cache(maxsize=2)
def _reference(path, modified, size):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def reference_dataset(settings, scope):
    path = settings.analytics_reference_file
    if path is None or not path.is_file():
        return None
    stat = path.stat()
    data = _reference(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    return data if data.get('scopeId') == scope and data.get('schemaVersion') == 1 else None


def published_dataset(session, scope, year):
    pairs = list(session.execute(select(Period, Run).join(Run, Period.active_run_id == Run.id).where(
        Period.scope_id == scope, Run.scope_id == scope, Run.kind == 'monthly',
        Run.publication_status == 'published', Period.year == year)))
    periods = []
    lookup = {}
    for period, run in pairs:
        counts = json.loads(run.counts_json or '{}')
        meta = {'year': period.year, 'month': period.month, 'name': period.name, 'runId': run.id,
                'version': period.version, 'rows': counts.get('rows', 0),
                'warnings': counts.get('warnings', 0), 'errors': counts.get('errors', 0),
                'files': counts.get('processedFiles', 0), 'tables': {}}
        periods.append(meta)
        lookup[run.id] = meta
    if lookup:
        for table in session.scalars(select(ProcessingTable).where(ProcessingTable.run_id.in_(lookup))):
            lookup[table.run_id]['tables'][table.table_code] = table.row_count
    tables = {}
    for code, fields in FIELDS.items():
        target = BUSINESS_TABLES[code]
        rows = []
        if lookup:
            query = select(target.c.processing_run_id, *(target.c[f] for f in fields)).where(
                target.c.processing_run_id.in_(lookup))
            for record in session.execute(query).mappings():
                period = lookup[record['processing_run_id']]
                rows.append({f: record[f] for f in fields} | {'year': year, 'month': period['month']})
        tables[code] = rows
    return {'periods': periods, 'tables': tables, 'sources': [], 'reconciliation': None}


def options(session, settings, scope):
    years = list(session.scalars(select(Period.year).where(
        Period.scope_id == scope, Period.active_run_id.is_not(None)).distinct().order_by(Period.year.desc())))
    reference = reference_dataset(settings, scope)
    sources = [{'id': 'published', 'years': years}]
    if reference:
        sources.append({'id': 'reference', 'years': sorted({p['year'] for p in reference['periods']}, reverse=True)})
    return {'sources': sources, 'defaultSource': 'published' if years else 'reference' if reference else 'published'}


def ranking(rows, key, field=None, limit=8):
    groups = defaultdict(list)
    for row in rows:
        groups[text_value(row.get(key)) or 'unknown'].append(row)
    result = [{'key': k, 'value': total(v, field) if field else len(v), 'rows': len(v)} for k, v in groups.items()]
    result.sort(key=lambda x: (-(x['value'] or 0), x['key']))
    if len(result) > limit:
        tail = result[limit:]
        result = result[:limit] + [{'key': 'other', 'value': sum(x['value'] or 0 for x in tail), 'rows': sum(x['rows'] for x in tail)}]
    return result


def summarize(session, settings, scope, *, source='published', year=2026, start_month=1,
              end_month=12, operation='', customs='', document=''):
    if start_month > end_month:
        raise ApplicationError(400, 'INVALID_RANGE', 'El mes inicial debe ser anterior o igual al final.')
    if source == 'reference':
        data = reference_dataset(settings, scope)
        if data is None:
            raise ApplicationError(404, 'REFERENCE_UNAVAILABLE', 'No hay una referencia Excel disponible en este ámbito.')
    elif source == 'published':
        data = published_dataset(session, scope, year)
    else:
        raise ApplicationError(400, 'INVALID_SOURCE', 'La fuente de análisis no es válida.')
    periods = {p['month']: p for p in data['periods'] if p['year'] == year}
    raw = {code: [r for r in data['tables'].get(code, []) if r['year'] == year] for code in FIELDS}
    headers = raw['501']
    def matches(r):
        return ((not operation or text_value(r.get('tipo_operacion')) == operation)
                and (not customs or text_value(r.get('seccion_aduanera')) == customs)
                and (not document or text_value(r.get('clave_documento')) == document))
    eligible_keys = {identity(r) for r in headers if identity(r) is not None and matches(r)}
    all_keys = {identity(r) for r in headers if identity(r) is not None}
    filtered = {}
    dimensions = bool(operation or customs or document)
    for code, rows in raw.items():
        if code == '501':
            filtered[code] = [r for r in rows if matches(r)]
        elif dimensions:
            # Semi-join prevents invoice/tax/item multiplicity from inflating totals.
            filtered[code] = [r for r in rows if identity(r) in eligible_keys and
                              (code not in {'551', 'sel', 'inci'} or matches(r))]
        else:
            filtered[code] = rows

    def metrics(tables, coverage):
        general, items = tables['501'], tables['551']
        unique = {identity(r) for r in general if identity(r) is not None}
        red = sum(text_value(r.get('semaforo_fiscal')) == '0' for r in tables['sel'])
        green = sum(text_value(r.get('semaforo_fiscal')) == '1' for r in tables['sel'])
        return {
            'declarations': len(unique) if '501' in coverage else None,
            'imports': len({identity(r) for r in general if identity(r) is not None and text_value(r.get('tipo_operacion')) == '1'}) if '501' in coverage else None,
            'exports': len({identity(r) for r in general if identity(r) is not None and text_value(r.get('tipo_operacion')) == '2'}) if '501' in coverage else None,
            'items': len(items) if '551' in coverage else None,
            'tradeUsd': total(items, 'valor_dolares') if '551' in coverage else None,
            'customsMxn': total(items, 'valor_aduana') if '551' in coverage else None,
            'commercialMxn': total(items, 'valor_comercial') if '551' in coverage else None,
            'importUsd': total([r for r in items if text_value(r.get('tipo_operacion')) == '1'], 'valor_dolares') if '551' in coverage else None,
            'exportUsd': total([r for r in items if text_value(r.get('tipo_operacion')) == '2'], 'valor_dolares') if '551' in coverage else None,
            'headerPaymentsMxn': total(tables['510'], 'importe_pago') if '510' in coverage else None,
            'itemPaymentsMxn': total(tables['557'], 'importe_pago') if '557' in coverage else None,
            'paymentDifferencesMxn': total(tables['702'], 'importe_pago') if '702' in coverage else None,
            'invoiceUsd': total(tables['505'], 'valor_dolares') if '505' in coverage else None,
            'invoices': len(tables['505']) if '505' in coverage else None,
            'weightKg': total(general, 'peso_bruto_mercancia') if '501' in coverage else None,
            'freightMxn': total(general, 'total_fletes') if '501' in coverage else None,
            'insuranceMxn': total(general, 'total_seguros') if '501' in coverage else None,
            'packingMxn': total(general, 'total_embalajes') if '501' in coverage else None,
            'incrementsMxn': total(general, 'total_incrementables') if '501' in coverage else None,
            'deductionsMxn': total(general, 'total_deducibles') if '501' in coverage else None,
            'rectifications': len(tables['701']) if '701' in coverage else None,
            'red': red if 'sel' in coverage else None, 'green': green if 'sel' in coverage else None,
            'redRate': round(red / (red + green) * 100, 2) if red + green else None,
            'simpleIncidents': sum(text_value(r.get('grado_incidencia')) == 'S' for r in tables['inci']) if 'inci' in coverage else None,
            'seriousIncidents': sum(text_value(r.get('grado_incidencia')) == 'G' for r in tables['inci']) if 'inci' in coverage else None,
            'correctInspections': sum(text_value(r.get('grado_incidencia')) == 'C' for r in tables['inci']) if 'inci' in coverage else None,
        }

    monthly = []
    for month in range(1, 13):
        p = periods.get(month)
        tables = {code: [r for r in rows if r['month'] == month] for code, rows in filtered.items()}
        m = metrics(tables, p['tables'] if p else {})
        monthly.append({'month': month, 'available': p is not None, 'metrics': m,
                        'rows': p['rows'] if p else None, 'warnings': p.get('warnings') if p else None,
                        'errors': p.get('errors') if p else None, 'files': p.get('files') if p else None,
                        'tables': p['tables'] if p else {}, 'runId': p.get('runId') if p else None,
                        'version': p.get('version') if p else None})
    selected = {code: [r for r in rows if start_month <= r['month'] <= end_month] for code, rows in filtered.items()}
    selected_periods = [p for n, p in periods.items() if start_month <= n <= end_month]
    coverage = {c for p in selected_periods for c in p['tables']}
    summary = metrics(selected, coverage)
    available_months = sorted(p['month'] for p in selected_periods)
    latest = available_months[-1] if available_months else None
    last = monthly[latest - 1]['metrics'] if latest else {}
    previous = monthly[latest - 2]['metrics'] if latest and latest > 1 else {}
    deltas = {k: change(v, previous.get(k)) for k, v in last.items()}
    completeness = {code: sum(code in p['tables'] for p in selected_periods) for code in FIELDS}
    numeric_fields = {'501': ['peso_bruto_mercancia', 'total_fletes', 'total_seguros', 'total_embalajes', 'total_incrementables', 'total_deducibles'],
                      '551': ['valor_dolares', 'valor_aduana', 'valor_comercial'], '505': ['valor_dolares'],
                      '510': ['importe_pago'], '557': ['importe_pago'], '702': ['importe_pago']}
    invalid = sum(number(r.get(f)) is None for c, fields in numeric_fields.items() for r in selected[c] for f in fields)
    orphan_items = sum(identity(r) not in all_keys for r in raw['551'] if start_month <= r['month'] <= end_month)
    breakdowns = {
        'customs': ranking(selected['501'], 'seccion_aduanera'),
        'documents': ranking(selected['501'], 'clave_documento'),
        'operations': ranking(selected['501'], 'tipo_operacion'),
        'countries': ranking(selected['551'], 'pais_origen_destino', 'valor_dolares'),
        'tariffs': ranking(selected['551'], 'fraccion', 'valor_dolares'),
        'suppliers': ranking(selected['505'], 'proveedor_mercancia', 'valor_dolares'),
        'incoterms': ranking(selected['505'], 'termino_facturacion', 'valor_dolares'),
        'headerTaxes': ranking(selected['510'], 'clave_contribucion', 'importe_pago'),
        'itemTaxes': ranking(selected['557'], 'clave_contribucion', 'importe_pago'),
        'paymentMethods': ranking(selected['510'], 'forma_pago', 'importe_pago'),
        'transport': ranking(selected['501'], 'medio_transporte_entrada_salida'),
        'inspection': ranking(selected['inci'], 'grado_incidencia'),
    }
    return {
        'source': source, 'year': year, 'startMonth': start_month, 'endMonth': end_month,
        'generatedAt': datetime.now(timezone.utc).isoformat(), 'sources': data.get('sources', []),
        'reconciliation': data.get('reconciliation'), 'monthly': monthly, 'totals': summary,
        'latestMonth': latest, 'previousMonth': latest - 1 if latest and latest > 1 else None,
        'latest': last, 'previous': previous, 'deltas': deltas, 'breakdowns': breakdowns,
        'coverage': {'availableMonths': available_months, 'requestedMonths': end_month - start_month + 1,
                     'tables': completeness, 'invalidNumericValues': invalid, 'orphanItems': orphan_items,
                     'duplicateDeclarationRows': len(selected['501']) - len({identity(r) for r in selected['501'] if identity(r) is not None}),
                     'processingFiltersApplied': False},
        'filters': {name: sorted({text_value(r.get(field)) for r in headers if text_value(r.get(field))})
                    for name, field in [('customs', 'seccion_aduanera'), ('documents', 'clave_documento'), ('operations', 'tipo_operacion')]},
    }
