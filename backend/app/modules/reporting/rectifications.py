"""Amendment frequency, not a determination of operational fault."""
from collections import Counter

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

    def grouped_summary(key, header_counts, amendment_counts, unmatched_counts):
        group_count = amendment_counts[key] if complete and not invalid_amendments else None
        group_base = header_counts[key] if denominator is not None else None
        verified = not unmatched_counts[key]
        return {'r1': group_count, 'declarations': group_base,
                'groupRate': percentage(group_count, group_base) if verified else None,
                'globalRate': percentage(group_count, denominator) if verified else None}

    combinations = sorted({(normalized(row.get('seccion_aduanera')) or 'unknown',
                            normalized(row.get('patente')) or 'unknown')
                           for code in ('501', '701') for row in tables[code]})
    def office_patent(key):
        return key[-1], key[2]
    header_groups = Counter(office_patent(key) for key in headers)
    amendment_groups = Counter(office_patent(key) for key in amendments)
    unmatched_groups = Counter(office_patent(key) for key in unmatched)
    customs_patent_rows = [
        {'customs': office, 'patent': patent,
         **grouped_summary((office, patent), header_groups, amendment_groups, unmatched_groups)}
        for office, patent in combinations
    ]
    header_patents = Counter(key[2] for key in headers)
    amendment_patents = Counter(key[2] for key in amendments)
    unmatched_patents = Counter(key[2] for key in unmatched)
    patent_rows = [
        {'patent': patent, **grouped_summary(patent, header_patents, amendment_patents, unmatched_patents)}
        for patent in sorted({patent for _, patent in combinations})
    ]
    return {'rows': rows, 'totals': {'r1': count, 'declarations': denominator,
                                   'officeRate': rate, 'globalRate': rate},
            'customsPatentRows': customs_patent_rows, 'patentRows': patent_rows,
            'globalDeclarations': denominator, 'available': complete,
            'unmatchedAmendments': len(unmatched),
            'invalidKeys': invalid_headers + invalid_amendments}

