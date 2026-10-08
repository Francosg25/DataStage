"""Amendment frequency, not a determination of operational fault."""
from .trade_values import identity, normalized


def rectifications_by_customs(tables, periods):
    complete = bool(periods) and all({'501', '701'}.issubset(p['tables']) for p in periods)
    headers = {identity(r) for r in tables['501']} - {None}
    amendments = {identity(r) for r in tables['701']} - {None}
    invalid_headers = sum(identity(r) is None for r in tables['501'])
    invalid_amendments = sum(identity(r) is None for r in tables['701'])
    unmatched = amendments - headers
    offices = sorted({normalized(r.get('seccion_aduanera')) or 'unknown'
                      for code in ('501', '701') for r in tables[code]})
    denominator = len(headers) if complete and not invalid_headers else None

    def percentage(numerator, base):
        return round(numerator / base * 100, 2) if numerator is not None and base else None

    rows = []
    for office in offices:
        count = sum(k[-1] == office for k in amendments) if complete and not invalid_amendments else None
        declarations = sum(k[-1] == office for k in headers) if denominator is not None else None
        verified = not any(k[-1] == office for k in unmatched)
        rows.append({'customs': office, 'r1': count, 'declarations': declarations,
                     'officeRate': percentage(count, declarations) if verified else None,
                     'globalRate': percentage(count, denominator) if verified else None})
    count = len(amendments) if complete and not invalid_amendments else None
    rate = percentage(count, denominator) if not unmatched else None
    return {'rows': rows, 'totals': {'r1': count, 'declarations': denominator,
                                   'officeRate': rate, 'globalRate': rate},
            'globalDeclarations': denominator, 'available': complete,
            'unmatchedAmendments': len(unmatched),
            'invalidKeys': invalid_headers + invalid_amendments}
