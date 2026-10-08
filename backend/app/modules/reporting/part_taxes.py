"""Paid import taxes at item grain, with conservative part-number attribution."""
from collections import defaultdict
from decimal import Decimal
import re

from .trade_values import identity, item_identity, normalized, number, strict_sum, text_value

# Only explicit labels are evidence. Serial/lot numbers and arbitrary text are not parts.
PART_LABEL = r'(?:N\s*[/\.]?\s*P\.?|P\s*/\s*N|PART\s*(?:NUMBER|NO\.?)|N[O\u00daU]MERO\s+DE\s+PARTE|NO\.?\s*PARTE)'
PART = re.compile(r'(?<![\w])(?:(?P<alternate>OTRO|OTHER|ALTERNATE)\s+)?' + PART_LABEL + r'\s*[:=#]\s*(?P<part>[A-Z0-9][A-Z0-9._/\-]{0,79})', re.I)
STANDALONE_LABEL = re.compile(r'^(?:(?P<alternate>OTRO|OTHER|ALTERNATE)\s+)?' + PART_LABEL + r'\s*[:=#]?$', re.I)
TOKEN = re.compile(r'^[A-Z0-9][A-Z0-9._/\-]{0,79}$', re.I)
INVALID_PARTS = {'NA', 'N/A', 'ND', 'N/D', 'NONE', 'NULL', 'S/N', 'SIN', 'NO'}


def part_numbers(observations):
    primary, aliases = set(), set()
    previous = None
    for row in sorted(observations, key=lambda r: number(r.get('secuencia_observacion')) or Decimal(0)):
        text = text_value(row.get('observaciones'))
        for match in PART.finditer(text):
            target = aliases if match.group('alternate') else primary
            target.add(match.group('part').upper())
        seq = number(row.get('secuencia_observacion'))
        if previous is not None and seq == previous[0] + 1 and TOKEN.fullmatch(text):
            (aliases if previous[1] else primary).add(text.upper())
        label = STANDALONE_LABEL.fullmatch(text)
        previous = (seq, bool(label.group('alternate'))) if label and seq is not None else None
    return sorted(primary - INVALID_PARTS), sorted(aliases - INVALID_PARTS - primary)


def extract_parts(observations):
    primary, aliases = part_numbers(observations)
    return sorted(set(primary + aliases))


def exchange_rates(headers):
    rates = defaultdict(set)
    for row in headers:
        key = identity(row)
        if key is not None:
            rate = number(row.get('tipo_cambio'))
            rates[key].add(rate if rate is not None and rate > 0 else None)
    return {key: next(iter(values)) if len(values) == 1 else None for key, values in rates.items()}


def convert(row, field, source_currency, currency, rates):
    value = number(row.get(field))
    if value is None or source_currency == currency or value == 0:
        return value
    rate = rates.get(identity(row))
    if rate is None:
        return None
    return value / rate if currency == 'USD' else value * rate


def import_payments(tables, payment_method='0'):
    operations = defaultdict(set)
    for row in tables['551']:
        if (key := item_identity(row)) is not None:
            operations[key].add(normalized(row.get('tipo_operacion')))
    rows, unmatched = [], 0
    for row in tables['557']:
        tax = {'6': 'igi', '3': 'iva'}.get(normalized(row.get('clave_contribucion')))
        if not tax or normalized(row.get('forma_pago')) != payment_method:
            continue
        operation = operations.get(item_identity(row), set())
        if len(operation) != 1 or '' in operation:
            unmatched += 1
        elif operation == {'1'}:
            rows.append((row, tax))
    return rows, unmatched


def paid_totals(tables, coverage, currency, rates):
    rows, unmatched = import_payments(tables)
    return {tax: strict_sum(convert(row, 'importe_pago', 'MXN', currency, rates) for row, kind in rows if kind == tax)
            if '551' in coverage and '557' in coverage and not unmatched else None for tax in ('igi', 'iva')}


def payment_method_totals(tables, coverage, currency, rates):
    result = {}
    for method, name in [('0', 'cash'), ('21', 'certiva')]:
        rows, unmatched = import_payments(tables, method)
        result[name] = {
            tax: strict_sum(convert(row, 'importe_pago', 'MXN', currency, rates)
                            for row, kind in rows if kind == tax)
            if {'551', '557'}.issubset(coverage) and not unmatched else None
            for tax in ('igi', 'iva')
        }
        result[name]['unmatchedRows'] = unmatched
    result['otherPaymentRows'] = sum(
        normalized(row.get('clave_contribucion')) in {'3', '6'}
        and normalized(row.get('forma_pago')) not in {'0', '21'} for row in tables['557'])
    return result


def paid_taxes(tables, coverage, currency, rates):
    items, observations = defaultdict(list), defaultdict(list)
    for row in tables['551']:
        if (key := item_identity(row)) is not None:
            items[key].append(row)
    for row in tables.get('558', []):
        if (key := item_identity(row)) is not None:
            observations[key].append(row)

    resolved, aliases_by_item, alerts, groups = {}, {}, [], {}
    missing, ambiguous = 0, 0
    for key, records in items.items():
        primary, aliases = part_numbers(observations[key])
        candidates = sorted(set(primary + aliases))
        part = primary[0] if len(primary) == 1 else None
        resolved[key] = part
        aliases_by_item[key] = aliases
        if part is None:
            status = 'ambiguous' if len(primary) > 1 else 'missing'
            ambiguous += len(primary) > 1
            missing += not primary
            row = records[0]
            alerts.append({'year': row['year'], 'month': row['month'],
                           'patent': text_value(row.get('patente')), 'declaration': text_value(row.get('pedimento')),
                           'customs': text_value(row.get('seccion_aduanera')), 'tariff': text_value(row.get('fraccion')),
                           'sequence': text_value(row.get('secuencia_fraccion')), 'status': status,
                           'candidates': candidates, 'observations': [text_value(r.get('observaciones')) for r in observations[key]]})

    payments, unmatched = import_payments(tables)
    for row, tax in payments:
        key = item_identity(row)
        part = resolved[key]
        tariff = normalized(row.get('fraccion'))
        group = groups.setdefault((part, tariff), {'partNumber': part, 'tariff': tariff, 'months': defaultdict(lambda: {'igi': [], 'iva': []}), 'items': set(), 'aliases': set()})
        if part is not None:
            group['aliases'].update(aliases_by_item[key])
        group['months'][row['month']][tax].append(convert(row, 'importe_pago', 'MXN', currency, rates))
        group['items'].add(key)

    output = []
    for group in groups.values():
        output.append({'partNumber': group['partNumber'], 'alternatePartNumbers': sorted(group['aliases']), 'tariff': group['tariff'], 'items': len(group['items']),
                       'months': {str(month): {tax: strict_sum(values) for tax, values in taxes.items()}
                                  for month, taxes in sorted(group['months'].items())},
                       **{tax: strict_sum(v for taxes in group['months'].values() for v in taxes[tax]) for tax in ('igi', 'iva')}})
    output.sort(key=lambda g: (-(g['igi'] or 0), g['partNumber'] or '', g['tariff']))
    return {'rows': output, 'alerts': alerts, 'missingParts': missing, 'ambiguousParts': ambiguous,
            'invalidItemKeys': sum(item_identity(r) is None for r in tables['551']),
            'unmatchedTaxRows': unmatched, 'currency': currency,
            'available': all(code in coverage for code in ('551', '557')),
            'observationSourceAvailable': '558' in coverage,
            'totals': paid_totals(tables, coverage, currency, rates)}
