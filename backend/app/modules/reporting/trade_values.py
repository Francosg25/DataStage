"""Shared identifiers and decimal arithmetic for customs analytics."""
from decimal import Decimal, InvalidOperation

KEY_FIELDS = ('patente', 'pedimento', 'seccion_aduanera')


def text_value(value):
    return '' if value is None else str(value).strip()


def number(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        parsed = Decimal(str(value).strip())
        return parsed if parsed.is_finite() else None
    except InvalidOperation:
        return None


def normalized(value):
    text = text_value(value)
    parsed = number(value)
    return str(int(parsed)) if parsed is not None and parsed == int(parsed) else text


def identity(row):
    values = [normalized(row.get(f)) for f in KEY_FIELDS]
    return (row['year'], row['month'], *values) if all(values) else None


def item_identity(row):
    header = identity(row)
    values = [normalized(row.get(f)) for f in ('fraccion', 'secuencia_fraccion')]
    return (*header, *values) if header and all(values) else None


def strict_sum(values):
    values = list(values)
    return None if any(v is None for v in values) else float(sum(values, Decimal(0)))
