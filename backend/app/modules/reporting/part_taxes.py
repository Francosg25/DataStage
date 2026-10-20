"""Paid import taxes at item grain, with conservative part-number attribution."""
from collections import defaultdict
from decimal import Decimal
import json
import os
from pathlib import Path
import re

from .trade_values import identity, item_identity, normalized, number, strict_sum, text_value

KNOWN_PARTS = frozenset(text_value(part).upper() for part in json.loads(
    Path(os.environ.get("DATASTAGE_PART_CATALOG_FILE", Path(__file__).with_name("part_numbers.json"))).read_text(encoding="utf-8")
) if text_value(part))

# Etiquetas explícitas; los modelos, series y lotes no son NP por sí solos.
PART_LABEL = (
    r'(?:N\s*[/\.]?\s*P\.?|P\s*/\s*N|PART\s*(?:NUMBER|NO\.?)|'
    r'N[ÚU]MERO\s+DE\s+PARTE|NO\.?\s*(?:DE\s+)?PARTE|N\.\s*(?:DE\s+)?PARTE)'
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
CATALOG_TOKEN = re.compile(r'(?<![\w./+\-])[A-Z0-9][A-Z0-9._/+\-]*(?![\w./+\-])', re.I)
CONTEXT_LABEL = re.compile(
    r'(?<![\w])(?:'
    r'(?P<blocked>SERIES?|SERIAL(?:\s+NUMBER)?|MODELOS?|MODELS?|LOTES?|LOTS?|'
    r'FACTURAS?|INVOICES?|P\.?\s*O\.?)|'
    r'(?P<ordinary>DESCRIPCI[ÓO]N(?:\s+FACTURA)?|DESCRIPTION|OBSERVACI[ÓO]N(?:ES)?|'
    r'ART[IÍ]CULO|MERCANC[IÍ]A|PRODUCTO|ITEM|MARCA|BRAND))'
    r'(?:\s*[:=#]\s*|\s+)', re.I,
)
PACKAGING_SUFFIXES = ('EN', 'N')
ORDER_CONTEXT = re.compile(r'\bORDEN\s+DE\s*$', re.I)
PO = re.compile(r'^P\.?\s*O\.?(?:\s*[:=#]\s*|\s+)' + PART_CODE + r'$', re.I)
# Regla limitada al prefijo confirmado por el usuario y al contexto P.O | NP.
PO_PART = re.compile(r'^1905-[A-Z0-9]{4,30}$', re.I)
INVALID_PARTS = {
    'NA', 'N/A', 'ND', 'N/D', 'NONE', 'NULL', 'S/N', 'SIN', 'NO',
    'FACTURA', 'ORDEN', 'DESCRIPCION', 'DESCRIPCIÓN', 'MODELO', 'INTERNO',
}


def _clean_part(value):
    code = text_value(value).upper()
    # Preserve an exact catalog entry; otherwise a final dot is sentence punctuation.
    return code if code in KNOWN_PARTS else code.rstrip('.')


def _catalog_part(value):
    code = _clean_part(value)
    if code in KNOWN_PARTS:
        return code
    for suffix in PACKAGING_SUFFIXES:
        if code.endswith(suffix) and (base := code[:-len(suffix)]) in KNOWN_PARTS:
            return base
    return None


def _catalog_mentions(text, explicit_spans):
    """Find whole catalog tokens in prose while respecting other field labels."""
    contexts = list(CONTEXT_LABEL.finditer(text))
    context_index, blocked = 0, False
    for token in CATALOG_TOKEN.finditer(text):
        while context_index < len(contexts) and contexts[context_index].end() <= token.start():
            blocked = contexts[context_index].group('blocked') is not None
            context_index += 1
        if blocked or any(start <= token.start() < end for start, end in explicit_spans):
            continue
        code = _clean_part(token.group())
        if len(code) <= 80 and _catalog_part(code):
            yield code


def part_numbers(observations):
    primary, aliases = set(), set()

    def add_part(value, alternate=False):
        code = _clean_part(value)
        if not code or code in INVALID_PARTS or len(code) > 80:
            return
        canonical = _catalog_part(code) or code
        (aliases if alternate else primary).add(canonical)
        if canonical != code:
            aliases.add(code)

    pending, previous_seq = None, None
    for row in sorted(observations, key=lambda r: number(r.get('secuencia_observacion')) or Decimal(0)):
        seq = number(row.get('secuencia_observacion'))
        if seq is None or previous_seq is None or seq != previous_seq + 1:
            pending = None
        for text in re.split(r'[|\r\n]+', text_value(row.get('observaciones'))):
            text = text.strip()
            if not text:
                continue
            code = _clean_part(text)
            consumed = False
            if pending and TOKEN.fullmatch(code) and code not in INVALID_PARTS:
                if pending != 'po' or _catalog_part(code) or PO_PART.fullmatch(code):
                    add_part(code, pending == 'alias')
                    consumed = True
            pending = None
            spans = []
            for match in PART.finditer(text):
                spans.append(match.span())
                if ORDER_CONTEXT.search(text[:match.start()]):
                    continue
                add_part(match.group('part'), bool(match.group('alternate')))
            if not consumed:
                for code in _catalog_mentions(text, spans):
                    add_part(code)
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


def import_payment_groups(tables):
    """Resolve the item operation once for every payment method in this dataset."""
    operations = defaultdict(set)
    for row in tables['551']:
        if (key := item_identity(row)) is not None:
            operations[key].add(normalized(row.get('tipo_operacion')))
    rows, unmatched = defaultdict(list), defaultdict(int)
    for row in tables['557']:
        tax = {'6': 'igi', '3': 'iva'}.get(normalized(row.get('clave_contribucion')))
        if not tax:
            continue
        method = normalized(row.get('forma_pago'))
        operation = operations.get(item_identity(row), set())
        if operation not in ({'1'}, {'2'}):
            unmatched[method] += 1
        elif operation == {'1'}:
            rows[method].append((row, tax))
    return rows, unmatched


def import_payments(tables, payment_method='0', *, groups=None):
    rows, unmatched = groups if groups is not None else import_payment_groups(tables)
    return rows.get(payment_method, []), unmatched.get(payment_method, 0)


def paid_totals(tables, coverage, currency, rates, *, groups=None):
    rows, unmatched = import_payments(tables, groups=groups)
    return {tax: strict_sum(convert(row, 'importe_pago', 'MXN', currency, rates) for row, kind in rows if kind == tax)
            if '551' in coverage and '557' in coverage and not unmatched else None for tax in ('igi', 'iva')}


def payment_method_totals(tables, coverage, currency, rates, *, groups=None):
    result = {}
    groups = groups if groups is not None else import_payment_groups(tables)
    methods = sorted((set(groups[0]) | set(groups[1])) - {'0', '21'})
    other = []
    for method, name in [('0', 'cash'), ('21', 'certiva')] + [(m, None) for m in methods]:
        rows, unmatched = import_payments(tables, method, groups=groups)
        values = {
            tax: strict_sum(convert(row, 'importe_pago', 'MXN', currency, rates)
                            for row, kind in rows if kind == tax)
            if {'551', '557'}.issubset(coverage) and not unmatched else None
            for tax in ('igi', 'iva')
        }
        values['unmatchedRows'] = unmatched
        if name:
            result[name] = values
        elif rows or unmatched:
            other.append({'code': method or 'unknown', 'rows': len(rows), **values})
    # Keep each method separate. FP 13 is previously paid, not new cash;
    # FP 22 is a guarantee, not the FP 21 credit. Exports never enter these totals.
    result['other'] = other
    result['otherPaymentRows'] = sum(row['rows'] for row in other)
    result['otherUnmatchedRows'] = sum(row['unmatchedRows'] for row in other)
    return result


def paid_taxes(tables, coverage, currency, rates, *, payment_groups=None):
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

    payment_groups = payment_groups if payment_groups is not None else import_payment_groups(tables)
    payments, unmatched = import_payments(tables, groups=payment_groups)
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
            'totals': paid_totals(tables, coverage, currency, rates, groups=payment_groups)}
