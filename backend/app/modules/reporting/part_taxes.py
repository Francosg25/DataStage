"""Paid import taxes at item grain, with conservative part-number attribution."""
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
import re

from .trade_values import identity, item_identity, normalized, number, strict_sum, text_value

KNOWN_PARTS = frozenset(json.loads(
    Path(__file__).with_name("part_numbers.json").read_text(encoding="utf-8")
))

# Etiquetas explícitas; los modelos, series y lotes no son NP por sí solos.
PART_LABEL = (
    r'(?:N\s*[/\.]?\s*P\.?|P\s*/\s*N|PART\s*(?:NUMBER|NO\.?)|'
    r'N[ÚU]MERO\s+DE\s+PARTE|NO\.?\s*(?:DE\s+)?PARTE)'
    r'(?:\s+INTERNO)?'
)
PART_CODE = r'[A-Z0-9][A-Z0-9._/+\-]{0,79}'
PREFIX = r'(?:(?P<alternate>OTRO|OTHER|ALTERNATE)\s+)?'
PART = re.compile(
    r'(?<![\w])' + PREFIX + PART_LABEL
    + r'(?:\s*[:=#]\s*|\s+)(?P<part>' + PART_CODE + r')'
    + r'(?=$|[\s,;:()\[\]{}])', re.I,
)
STANDALONE_LABEL = re.compile(
    r'^' + PREFIX + PART_LABEL + r'\s*[:=#]?$', re.I,
)
TOKEN = re.compile(r'^' + PART_CODE + r'$', re.I)
ORDER_CONTEXT = re.compile(r'\bORDEN\s+DE\s*$', re.I)
PO = re.compile(r'^P\.?\s*O\.?(?:\s*[:=#]\s*|\s+)' + PART_CODE + r'$', re.I)
# Regla limitada al prefijo confirmado por el usuario y al contexto P.O | NP.
PO_PART = re.compile(r'^1905-[A-Z0-9]{4,30}$', re.I)
INVALID_PARTS = {
    'NA', 'N/A', 'ND', 'N/D', 'NONE', 'NULL', 'S/N', 'SIN', 'NO',
    'FACTURA', 'ORDEN', 'DESCRIPCION', 'DESCRIPCIÓN', 'MODELO', 'INTERNO',
}


def part_numbers(observations):
    primary, aliases = set(), set()
    pending, previous_seq = None, None
    for row in sorted(observations, key=lambda r: number(r.get('secuencia_observacion')) or Decimal(0)):
        seq = number(row.get('secuencia_observacion'))
        if seq is None or previous_seq is None or seq != previous_seq + 1:
            pending = None
        for text in re.split(r'[|\r\n]+', text_value(row.get('observaciones'))):
            text = text.strip()
            if not text:
                continue
            code = text.upper()
            if pending and TOKEN.fullmatch(text) and code not in INVALID_PARTS:
                if pending != 'po' or code in KNOWN_PARTS or PO_PART.fullmatch(text):
                    (aliases if pending == 'alias' else primary).add(code)
            elif code in KNOWN_PARTS:
                primary.add(code)
            pending = None
            for match in PART.finditer(text):
                if ORDER_CONTEXT.search(text[:match.start()]):
                    continue
                code = match.group('part').upper()
                if code not in INVALID_PARTS:
                    (aliases if match.group('alternate') else primary).add(code)
            label = STANDALONE_LABEL.fullmatch(text)
            if label:
                pending = 'alias' if label.group('alternate') else 'primary'
            elif PO.fullmatch(text):
                pending = 'po'
        previous_seq = seq
    return sorted(primary), sorted(aliases - primary)

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
