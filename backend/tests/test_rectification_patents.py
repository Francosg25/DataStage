"""Broker and customs groups must partition distinct declarations, not multiply them."""
from copy import deepcopy

from app.modules.reporting.rectifications import rectifications_by_customs


def declaration(**changes):
    return dict(year=2026, month=1, patente='0036', pedimento='0000009', seccion_aduanera='240') | changes


def test_customs_patent_and_patent_groups_partition_unique_declarations_across_months():
    a = declaration()
    alias = declaration(patente='36', pedimento='9')
    b = declaration(pedimento='10')
    c = declaration(pedimento='11', seccion_aduanera='160')
    d = declaration(patente='0077')
    e = declaration(month=2)
    tables = {'501': [a, alias, b, c, d, e], '701': [a, alias, c, d, e, e]}
    original = deepcopy(tables)
    result = rectifications_by_customs(tables, [{'tables': {'501': 6, '701': 6}}])
    assert tables == original
    assert result['totals'] == {'r1': 4, 'declarations': 5, 'officeRate': 80, 'globalRate': 80}
    assert result['customsPatentRows'] == [
        {'customs': '160', 'patent': '36', 'r1': 1, 'declarations': 1, 'groupRate': 100, 'globalRate': 20},
        {'customs': '240', 'patent': '36', 'r1': 2, 'declarations': 3, 'groupRate': 66.67, 'globalRate': 40},
        {'customs': '240', 'patent': '77', 'r1': 1, 'declarations': 1, 'groupRate': 100, 'globalRate': 20},
    ]
    assert result['patentRows'] == [
        {'patent': '36', 'r1': 3, 'declarations': 4, 'groupRate': 75, 'globalRate': 60},
        {'patent': '77', 'r1': 1, 'declarations': 1, 'groupRate': 100, 'globalRate': 20},
    ]
    for group in ('rows', 'customsPatentRows', 'patentRows'):
        assert sum(row['r1'] for row in result[group]) == 4
        assert sum(row['declarations'] for row in result[group]) == 5


def test_orphan_amendment_invalidates_only_its_group_and_global_total_rate():
    a, b = declaration(), declaration(patente='77')
    orphan = declaration(patente='77', pedimento='99')
    result = rectifications_by_customs({'501': [a, b], '701': [a, orphan]}, [{'tables': {'501': 2, '701': 2}}])
    assert result['unmatchedAmendments'] == 1
    assert result['totals']['globalRate'] is None
    assert result['customsPatentRows'][0]['groupRate'] == 100
    assert result['patentRows'][0]['groupRate'] == 100
    assert result['patentRows'][0]['globalRate'] == 50
    assert result['customsPatentRows'][1]['groupRate'] is None
    assert result['patentRows'][1]['groupRate'] is None
    assert result['patentRows'][1]['globalRate'] is None


def test_missing_coverage_invalid_keys_and_zero_base_remain_unavailable():
    row = declaration()
    incomplete = rectifications_by_customs({'501': [row], '701': [row]}, [{'tables': {'501': 1}}])
    for group in ('customsPatentRows', 'patentRows'):
        assert incomplete[group][0]['r1'] is None
        assert incomplete[group][0]['declarations'] is None
        assert incomplete[group][0]['groupRate'] is None
    invalid = declaration(patente='')
    result = rectifications_by_customs({'501': [invalid], '701': [invalid]}, [{'tables': {'501': 1, '701': 1}}])
    assert result['invalidKeys'] == 2
    assert result['patentRows'][0]['patent'] == 'unknown'
    assert result['patentRows'][0]['r1'] is None
    assert result['patentRows'][0]['groupRate'] is None
    empty = rectifications_by_customs({'501': [], '701': []}, [{'tables': {'501': 0, '701': 0}}])
    assert empty['patentRows'] == empty['customsPatentRows'] == []
    assert empty['totals']['r1'] == 0
    assert empty['totals']['officeRate'] is None
