"""Read-only trade analytics. Aggregate each grain separately; never fan out joins."""
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import json
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.core.errors import ApplicationError
from app.persistence.business import BUSINESS_TABLES
from app.persistence.models import Period, ProcessingTable, Run
from .trade_values import KEY_FIELDS, identity, normalized, number, text_value, strict_sum
from .part_taxes import (convert, exchange_rates, import_payment_groups, paid_taxes,
                         payment_method_totals)
from .rectifications import rectifications_by_customs

FIELDS = {
    '501': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'tipo_pedimento',
            'peso_bruto_mercancia', 'total_fletes', 'total_seguros', 'total_embalajes',
            'total_incrementables', 'total_deducibles', 'medio_transporte_entrada_salida', 'tipo_cambio'),
    '551': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'fraccion', 'secuencia_fraccion',
            'valor_dolares', 'valor_aduana', 'valor_comercial', 'pais_origen_destino'),
    '505': (*KEY_FIELDS, 'proveedor_mercancia', 'pais_facturacion', 'termino_facturacion', 'valor_dolares'),
    '510': (*KEY_FIELDS, 'clave_contribucion', 'forma_pago', 'importe_pago'),
    '557': (*KEY_FIELDS, 'fraccion', 'secuencia_fraccion', 'clave_contribucion', 'forma_pago', 'importe_pago'),
    '558': (*KEY_FIELDS, 'fraccion', 'secuencia_fraccion', 'secuencia_observacion', 'observaciones'),
    '702': (*KEY_FIELDS, 'clave_contribucion', 'forma_pago', 'importe_pago'),
    '701': KEY_FIELDS,
    'sel': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'semaforo_fiscal'),
    'inci': (*KEY_FIELDS, 'tipo_operacion', 'clave_documento', 'grado_incidencia'),
}


def total(rows, field):
    return strict_sum(number(row.get(field)) for row in rows)


def change(current, previous):
    return None if current is None or previous in (None, 0) else round((current - previous) / abs(previous) * 100, 2)


@lru_cache(maxsize=2)
def _reference(path, modified, size, changed=0, inode=0):
    with Path(path).open(encoding='utf-8') as stream:
        return json.load(stream)


def reference_dataset(settings, scope):
    path = settings.analytics_reference_file
    if path is None or not path.is_file():
        return None
    stat = path.stat()
    data = _reference(str(path.resolve()), stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns, stat.st_ino)
    return data if data.get('scopeId') == scope and data.get('schemaVersion') == 1 else None


def published_dataset(session, scope, year, codes=FIELDS):
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
    for code in codes:
        fields = FIELDS[code]
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


def _dataset_revision(session, settings, scope, source, year):
    if source == 'reference':
        path = settings.analytics_reference_file
        if path is None or not path.is_file():
            return None
        stat = path.stat()
        return (str(path.resolve()), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    # Published rows are immutable within a run. Replacing or deleting a month
    # changes its active run/version, including publications made by the worker.
    rows = session.execute(select(Period.month, Period.active_run_id, Period.version, Run.counts_json)
        .join(Run, Period.active_run_id == Run.id).where(
            Period.scope_id == scope, Run.scope_id == scope, Run.kind == 'monthly',
            Run.publication_status == 'published', Period.year == year).order_by(Period.month))
    return (id(session.get_bind()), tuple(tuple(row) for row in rows))


def _source_option(source, periods):
    latest = max(periods, default=None)
    return {'id': source, 'years': sorted({year for year, _ in periods}, reverse=True),
            'latestPeriod': {'year': latest[0], 'month': latest[1]} if latest else None}


def options(session, settings, scope):
    periods = list(session.execute(select(Period.year, Period.month)
        .join(Run, Period.active_run_id == Run.id).where(
            Period.scope_id == scope, Run.scope_id == scope, Run.kind == 'monthly',
            Run.publication_status == 'published')))
    reference = reference_dataset(settings, scope)
    sources = [_source_option('published', periods)]
    if reference:
        sources.append(_source_option('reference', [(p['year'], p['month']) for p in reference['periods']]))
    return {'sources': sources, 'defaultSource': 'published' if periods else 'reference' if reference else 'published'}


def ranking(rows, key, field=None, limit=8):
    groups = defaultdict(list)
    for row in rows:
        groups[text_value(row.get(key)) or 'unknown'].append(row)
    result = [{'key': k, 'value': total(v, field) if field else len(v), 'rows': len(v)} for k, v in groups.items()]
    result.sort(key=lambda x: (-(x['value'] or 0), x['key']))
    if len(result) > limit:
        tail = result[limit:]
        result = result[:limit] + [{'key': 'other', 'value': strict_sum(number(x['value']) for x in tail), 'rows': sum(x['rows'] for x in tail)}]
    return result


def declaration_ranking(rows, field):
    """Use the same distinct declaration population as the KPI, not 501 row count."""
    groups = defaultdict(set)
    for row in rows:
        key = identity(row)
        if key is None:
            return []
        groups[key].add(normalized(row.get(field)) or 'unknown')
    # Conflicting descriptions for the same declaration remain one declaration.
    return ranking([{field: next(iter(values)) if len(values) == 1 else 'unknown'}
                    for values in groups.values()], field)


def summarize(session, settings, scope, *, source='published', year=2026, start_month=1,
              end_month=12, operation='', customs='', document='', currency='USD', cache=None):
    if currency not in {'USD', 'MXN'}:
        raise ApplicationError(400, 'INVALID_CURRENCY', 'Moneda no admitida')
    if start_month > end_month:
        raise ApplicationError(400, 'INVALID_RANGE', 'El mes inicial debe ser anterior o igual al final.')
    if source not in {'reference', 'published'}:
        raise ApplicationError(400, 'INVALID_SOURCE', 'La fuente de análisis no es válida.')
    if cache is not None:
        key = ('full', scope, source, year, start_month, end_month, operation, customs, document,
               currency, _dataset_revision(session, settings, scope, source, year))
        return cache.get_or_compute(key, lambda: summarize(
            session, settings, scope, source=source, year=year, start_month=start_month,
            end_month=end_month, operation=operation, customs=customs, document=document, currency=currency))
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
    rates = exchange_rates(headers)
    def matches(r):
        return ((not operation or normalized(r.get('tipo_operacion')) == normalized(operation))
                and (not customs or normalized(r.get('seccion_aduanera')) == normalized(customs))
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

    def metrics(tables, coverage, payments):
        general, items = tables['501'], tables['551']
        unique = {identity(r) for r in general if identity(r) is not None}
        red = sum(normalized(r.get('semaforo_fiscal')) == '0' for r in tables['sel'])
        green = sum(normalized(r.get('semaforo_fiscal')) == '1' for r in tables['sel'])
        unknown_selections = len(tables['sel']) - red - green
        valid_headers = all(identity(r) is not None for r in general)
        result = {
            'declarations': len(unique) if '501' in coverage and valid_headers else None,
            'imports': len({identity(r) for r in general if identity(r) is not None and normalized(r.get('tipo_operacion')) == '1'}) if '501' in coverage else None,
            'exports': len({identity(r) for r in general if identity(r) is not None and normalized(r.get('tipo_operacion')) == '2'}) if '501' in coverage else None,
            'items': len(items) if '551' in coverage else None,
            'tradeUsd': total(items, 'valor_dolares') if '551' in coverage else None,
            'customsMxn': total(items, 'valor_aduana') if '551' in coverage else None,
            'commercialMxn': total(items, 'valor_comercial') if '551' in coverage else None,
            'importUsd': total([r for r in items if normalized(r.get('tipo_operacion')) == '1'], 'valor_dolares') if '551' in coverage else None,
            'exportUsd': total([r for r in items if normalized(r.get('tipo_operacion')) == '2'], 'valor_dolares') if '551' in coverage else None,
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
            'rectifications': len({identity(r) for r in tables['701']} - {None})
            if '701' in coverage and all(identity(r) is not None for r in tables['701']) else None,
            'red': red if 'sel' in coverage else None, 'green': green if 'sel' in coverage else None,
            'unclassifiedSelections': unknown_selections if 'sel' in coverage else None,
            'redRate': round(red / (red + green) * 100, 2)
            if 'sel' in coverage and red + green and not unknown_selections else None,
            'simpleIncidents': sum(text_value(r.get('grado_incidencia')) == 'S' for r in tables['inci']) if 'inci' in coverage else None,
            'seriousIncidents': sum(text_value(r.get('grado_incidencia')) == 'G' for r in tables['inci']) if 'inci' in coverage else None,
            'correctInspections': sum(text_value(r.get('grado_incidencia')) == 'C' for r in tables['inci']) if 'inci' in coverage else None,
        }
        monetary = {'trade': ('551', 'valor_dolares', 'USD'), 'customs': ('551', 'valor_aduana', 'MXN'),
                    'commercial': ('551', 'valor_comercial', 'MXN'), 'invoice': ('505', 'valor_dolares', 'USD'),
                    'headerPayments': ('510', 'importe_pago', 'MXN'), 'freight': ('501', 'total_fletes', 'MXN'),
                    'insurance': ('501', 'total_seguros', 'MXN'), 'packing': ('501', 'total_embalajes', 'MXN'),
                    'increments': ('501', 'total_incrementables', 'MXN'), 'deductions': ('501', 'total_deducibles', 'MXN')}
        for name, (code, field, original) in monetary.items():
            result[name + currency.title()] = strict_sum(convert(r, field, original, currency, rates) for r in tables[code]) if code in coverage else None
        for name, operation_code in [('import', '1'), ('export', '2')]:
            result[name + currency.title()] = strict_sum(convert(r, 'valor_dolares', 'USD', currency, rates) for r in items if normalized(r.get('tipo_operacion')) == operation_code) if '551' in coverage else None
        result['unclassifiedTrade' + currency.title()] = strict_sum(
            convert(r, 'valor_dolares', 'USD', currency, rates) for r in items
            if normalized(r.get('tipo_operacion')) not in {'1', '2'}) if '551' in coverage else None
        result['unclassifiedItems'] = sum(normalized(r.get('tipo_operacion')) not in {'1', '2'}
                                          for r in items) if '551' in coverage else None
        result.update(igiPaid=payments['cash']['igi'], ivaPaid=payments['cash']['iva'],
                      igiFp21=payments['certiva']['igi'], ivaFp21=payments['certiva']['iva'])
        return result

    by_month = {month: {code: [] for code in FIELDS} for month in range(1, 13)}
    for code, rows in filtered.items():
        for row in rows:
            by_month[row['month']][code].append(row)
    monthly = []
    for month in range(1, 13):
        p = periods.get(month)
        tables = by_month[month]
        payments = payment_method_totals(tables, p['tables'] if p else {}, currency, rates)
        m = metrics(tables, p['tables'] if p else {}, payments)
        monthly.append({'month': month, 'available': p is not None, 'metrics': m,
                        'paymentMethods': payments,
                        'rows': p['rows'] if p else None, 'warnings': p.get('warnings') if p else None,
                        'errors': p.get('errors') if p else None, 'files': p.get('files') if p else None,
                        'tables': p['tables'] if p else {}, 'runId': p.get('runId') if p else None,
                        'version': p.get('version') if p else None})
    selected = {code: [r for r in rows if start_month <= r['month'] <= end_month] for code, rows in filtered.items()}
    selected_periods = [p for n, p in periods.items() if start_month <= n <= end_month]
    # An absent table in an available month is not an empty table. Do not
    # present a partial sum as the total for that metric's available months.
    coverage = set.intersection(*(set(p['tables']) for p in selected_periods)) if selected_periods else set()
    rectification_summary = rectifications_by_customs(selected, selected_periods)
    payment_coverage = {'551', '557'} if selected_periods and all(
        {'551', '557'}.issubset(p['tables']) for p in selected_periods) else set()
    selected_payments = import_payment_groups(selected)
    payment_summary = payment_method_totals(selected, payment_coverage, currency, rates, groups=selected_payments)
    summary = metrics(selected, coverage, payment_summary)
    summary['rectifications'] = rectification_summary['totals']['r1']
    parts = paid_taxes(selected, coverage, currency, rates, payment_groups=selected_payments)
    parts['available'] = bool(selected_periods) and all({'551', '557'}.issubset(p['tables']) for p in selected_periods)
    parts['observationSourceAvailable'] = bool(selected_periods) and all('558' in p['tables'] for p in selected_periods)
    if not parts['available']:
        parts['totals'] = {'igi': None, 'iva': None}
        summary.update(igiPaid=None, ivaPaid=None, igiFp21=None, ivaFp21=None)
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
        'customs': declaration_ranking(selected['501'], 'seccion_aduanera') if '501' in coverage else [],
        'documents': declaration_ranking(selected['501'], 'clave_documento') if '501' in coverage else [],
        'operations': declaration_ranking(selected['501'], 'tipo_operacion') if '501' in coverage else [],
        'transport': ranking(selected['501'], 'medio_transporte_entrada_salida'),
        'inspection': ranking(selected['inci'], 'grado_incidencia'),
    }
    for name, (code, key, field, original) in {
        'countries': ('551', 'pais_origen_destino', 'valor_dolares', 'USD'),
        'originCountries': ('551', 'pais_origen_destino', 'valor_dolares', 'USD'),
        'destinationCountries': ('551', 'pais_origen_destino', 'valor_dolares', 'USD'),
        'tariffs': ('551', 'fraccion', 'valor_dolares', 'USD'),
        'suppliers': ('505', 'proveedor_mercancia', 'valor_dolares', 'USD'),
        'incoterms': ('505', 'termino_facturacion', 'valor_dolares', 'USD'),
        'headerTaxes': ('510', 'clave_contribucion', 'importe_pago', 'MXN'),
        'itemTaxes': ('557', 'clave_contribucion', 'importe_pago', 'MXN'),
        'paymentMethods': ('510', 'forma_pago', 'importe_pago', 'MXN'),
    }.items():
        groups = defaultdict(list)
        for row in selected[code]:
            op = {'originCountries': '1', 'destinationCountries': '2'}.get(name)
            if op and normalized(row.get('tipo_operacion')) != op:
                continue
            groups[text_value(row.get(key)) or 'unknown'].append(convert(row, field, original, currency, rates))
        values = sorted([{'key': k, 'value': strict_sum(v), 'rows': len(v)} for k, v in groups.items()], key=lambda r: (-(r['value'] or 0), r['key']))
        breakdowns[name] = values[:8] + ([{'key': 'other', 'value': strict_sum(number(v['value']) for v in values[8:]), 'rows': sum(v['rows'] for v in values[8:])}] if len(values) > 8 else [])
        if code not in coverage:
            for row in breakdowns[name]:
                row['value'] = None
    rectifications = []
    for patent in sorted({text_value(r.get('patente')) for r in selected['701']}):
        rectifications.append({'patent': patent, 'values': [len({identity(r) for r in selected['701']
            if text_value(r.get('patente')) == patent and r['month'] == m} - {None})
            if m in periods and '701' in periods[m]['tables'] and all(identity(r) is not None
                for r in selected['701'] if r['month'] == m) else None for m in range(1, 13)]})
    result = {
        'appliedFilters': {'source': source, 'year': year, 'startMonth': start_month, 'endMonth': end_month,
                           'operation': operation, 'customs': customs, 'document': document, 'currency': currency},
        'paymentMethods': payment_summary, 'rectificationsByCustoms': rectification_summary,
        'currency': currency, 'partTaxes': parts, 'rectifications': rectifications,
        'source': source, 'year': year, 'startMonth': start_month, 'endMonth': end_month,
        'generatedAt': datetime.now(timezone.utc).isoformat(), 'sources': data.get('sources', []),
        'reconciliation': data.get('reconciliation'), 'monthly': monthly, 'totals': summary,
        'latestMonth': latest, 'previousMonth': latest - 1 if latest and latest > 1 else None,
        'latest': last, 'previous': previous, 'deltas': deltas, 'breakdowns': breakdowns,
        'coverage': {'availableMonths': available_months, 'requestedMonths': end_month - start_month + 1,
                     'missingExchangeRates': sum(rates.get(identity(r)) is None for r in selected['501']),
                     'tables': completeness, 'invalidNumericValues': invalid, 'orphanItems': orphan_items,
                     'incompleteTables': sorted({c for p in selected_periods for c in p['tables']} - coverage),
                     'invalidDeclarationKeys': sum(identity(r) is None for r in selected['501']),
                     'duplicateDeclarationRows': sum(identity(r) is not None for r in selected['501']) - len({identity(r) for r in selected['501']} - {None}),
                     'processingFiltersApplied': False},
        'filters': {name: sorted({text_value(r.get(field)) for r in headers if text_value(r.get(field))})
                    for name, field in [('customs', 'seccion_aduanera'), ('documents', 'clave_documento'), ('operations', 'tipo_operacion')]},
    }
    result['snapshotId'] = hashlib.sha256(json.dumps(
        {k: v for k, v in result.items() if k != 'generatedAt'}, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    return result


def monthly_summary(session, settings, scope, *, source='published', year=2026, currency='USD', cache=None):
    """Comparison metrics only: no PN matching, observations or rankings."""
    if currency not in {'USD', 'MXN'}:
        raise ApplicationError(400, 'INVALID_CURRENCY', 'Moneda no admitida')
    if source not in {'reference', 'published'}:
        raise ApplicationError(400, 'INVALID_SOURCE', 'La fuente de análisis no es válida.')
    if cache is not None:
        key = ('months', scope, source, year, currency, _dataset_revision(session, settings, scope, source, year))
        return cache.get_or_compute(key, lambda: monthly_summary(
            session, settings, scope, source=source, year=year, currency=currency))
    codes = ('501', '551', '557', '701')
    if source == 'reference':
        data = reference_dataset(settings, scope)
        if data is None:
            raise ApplicationError(404, 'REFERENCE_UNAVAILABLE', 'No hay una referencia Excel disponible en este ámbito.')
    else:
        data = published_dataset(session, scope, year, codes)
    periods = {p['month']: p for p in data['periods'] if p['year'] == year}
    tables_by_month = {month: {code: [] for code in codes} for month in range(1, 13)}
    headers = []
    for code in codes:
        for row in data['tables'].get(code, []):
            if row['year'] == year:
                tables_by_month[row['month']][code].append(row)
                if code == '501':
                    headers.append(row)
    rates = exchange_rates(headers)
    monthly = []
    for month, tables in tables_by_month.items():
        period = periods.get(month)
        coverage = period['tables'] if period else {}
        keys = {identity(row) for row in tables['501']}
        payments = payment_method_totals(tables, coverage, currency, rates)
        metrics = {
            'declarations': len(keys) if '501' in coverage and None not in keys else None,
            'items': len(tables['551']) if '551' in coverage else None,
            'trade' + currency.title(): strict_sum(
                convert(row, 'valor_dolares', 'USD', currency, rates) for row in tables['551'])
            if '551' in coverage else None,
            'igiPaid': payments['cash']['igi'], 'ivaPaid': payments['cash']['iva'],
            'igiFp21': payments['certiva']['igi'], 'ivaFp21': payments['certiva']['iva'],
            'rectifications': rectifications_by_customs(tables, [period] if period else [])['totals']['r1'],
        }
        for name, operation_code in [('import', '1'), ('export', '2')]:
            metrics[name + currency.title()] = strict_sum(
                convert(row, 'valor_dolares', 'USD', currency, rates) for row in tables['551']
                if normalized(row.get('tipo_operacion')) == operation_code) if '551' in coverage else None
        monthly.append({'month': month, 'available': period is not None, 'metrics': metrics})
    return {'source': source, 'year': year, 'currency': currency, 'monthly': monthly,
            'generatedAt': datetime.now(timezone.utc).isoformat()}

