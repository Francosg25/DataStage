"""The KPI cards must separate trade directions and payment methods."""
import json

import pytest

import test_api_worker

system = test_api_worker.system


def install_kpis(settings, tmp_path):
    tables = {code: [] for code in ('501', '551', '557', '558', '701')}
    periods = []
    for month, import_value, export_value, import_rate, export_rate in (
        (1, 100, 200, 10, 20), (2, 150, 500, 20, 25),
    ):
        base = dict(year=2026, month=month, patente='0036', seccion_aduanera='240',
                    fraccion='12345678', secuencia_fraccion='1', clave_documento='A1')
        imported = base | dict(pedimento='0000001', tipo_operacion='1', tipo_cambio=str(import_rate))
        exported = base | dict(pedimento='0000002', tipo_operacion='2', tipo_cambio=str(export_rate))
        unknown = base | dict(pedimento='0000003', tipo_operacion='9', tipo_cambio='10')
        tables['501'].extend([imported, exported, unknown])
        tables['551'].extend([
            imported | dict(valor_dolares=str(import_value)),
            exported | dict(valor_dolares=str(export_value)),
            unknown | dict(valor_dolares='35'),
        ])
        amounts = (100, 80, 40, 320) if month == 1 else (300, 120, 120, 480)
        for (contribution, method), amount in zip((('6', '0'), ('3', '0'), ('6', '21.0'), ('3', '21')), amounts):
            tables['557'].append(imported | dict(
                clave_contribucion=contribution, forma_pago=method, importe_pago=str(amount)))
        tables['557'].extend([
            imported | dict(clave_contribucion='6', forma_pago='13', importe_pago='900'),
            exported | dict(clave_contribucion='3', forma_pago='21', importe_pago='9999'),
        ])
        periods.append(dict(year=2026, month=month, name=f'Month_{month}', rows=20,
                            tables={code: sum(row['month'] == month for row in rows) for code, rows in tables.items()}))
    data = dict(schemaVersion=1, scopeId='local', sources=[], periods=periods, tables=tables)
    settings.analytics_reference_file = tmp_path / 'reference-kpis.json'
    save(settings, data)
    return data


def save(settings, data):
    settings.analytics_reference_file.write_text(json.dumps(data), encoding='utf-8')


@pytest.mark.parametrize('currency,expected', [
    ('USD', {'importUsd': 250, 'exportUsd': 700, 'igiPaid': 25, 'ivaPaid': 14, 'igiFp21': 10, 'ivaFp21': 56}),
    ('MXN', {'importMxn': 4000, 'exportMxn': 16500, 'igiPaid': 400, 'ivaPaid': 200, 'igiFp21': 160, 'ivaFp21': 800}),
])
def test_kpis_and_comparison_separate_directions_methods_and_conversion(system, tmp_path, currency, expected):
    _, client, settings = system
    install_kpis(settings, tmp_path)
    params = dict(source='reference', year=2026, currency=currency, startMonth=1, endMonth=2)
    report = client.get('/api/v1/reports/analytics', params=params).json()
    assert {key: report['totals'][key] for key in expected} == expected
    for key, method, tax in (('igiPaid', 'cash', 'igi'), ('ivaPaid', 'cash', 'iva'),
                             ('igiFp21', 'certiva', 'igi'), ('ivaFp21', 'certiva', 'iva')):
        assert report['totals'][key] == report['paymentMethods'][method][tax]
        assert report['latest'][key] == report['monthly'][1]['paymentMethods'][method][tax]
        assert report['previous'][key] == report['monthly'][0]['paymentMethods'][method][tax]
    if currency == 'USD':
        assert {key: report['deltas'][key] for key in ('igiPaid', 'ivaPaid', 'igiFp21', 'ivaFp21')} == {
            'igiPaid': 50, 'ivaPaid': -25, 'igiFp21': 50, 'ivaFp21': -25}
    # Unclassified trade and previously paid amounts cannot leak into these cards.
    assert report['totals']['trade' + currency.title()] > expected['import' + currency.title()] + expected['export' + currency.title()]
    filtered = client.get('/api/v1/reports/analytics', params=params | {'operation': '2'}).json()
    assert filtered['totals']['import' + currency.title()] == 0
    assert filtered['totals']['export' + currency.title()] == expected['export' + currency.title()]
    assert all(filtered['totals'][key] == 0 for key in ('igiPaid', 'ivaPaid', 'igiFp21', 'ivaFp21'))
    lean = client.get('/api/v1/reports/analytics/months', params=params).json()
    for month in (1, 2, 3):
        single = client.get('/api/v1/reports/analytics', params=params | {'startMonth': month, 'endMonth': month}).json()
        assert {key: lean['monthly'][month - 1]['metrics'][key] for key in expected} == {
            key: single['totals'][key] for key in expected}


@pytest.mark.parametrize('missing', ['551', '557'])
def test_kpi_missing_tables_never_turn_credit_into_zero_or_partial_totals(system, tmp_path, missing):
    _, client, settings = system
    data = install_kpis(settings, tmp_path)
    data['periods'][0]['tables'].pop(missing)
    save(settings, data)
    report = client.get('/api/v1/reports/analytics', params={'source': 'reference', 'year': 2026}).json()
    assert all(report['totals'][key] is None for key in ('igiPaid', 'ivaPaid', 'igiFp21', 'ivaFp21'))
    assert all(report['monthly'][0]['metrics'][key] is None for key in ('igiPaid', 'ivaPaid', 'igiFp21', 'ivaFp21'))
    assert report['monthly'][1]['metrics']['ivaFp21'] == 24


def test_unverified_credit_and_missing_exchange_rates_preserve_independent_cash(system, tmp_path):
    _, client, settings = system
    data = install_kpis(settings, tmp_path)
    data['tables']['557'][2]['secuencia_fraccion'] = '99'
    save(settings, data)
    params = dict(source='reference', year=2026, startMonth=1, endMonth=1)
    report = client.get('/api/v1/reports/analytics', params=params).json()
    assert report['totals']['igiPaid'] == 10
    assert report['totals']['ivaPaid'] == 8
    assert report['totals']['igiFp21'] is None
    assert report['totals']['ivaFp21'] is None
    data['tables']['557'][2]['secuencia_fraccion'] = '1'
    data['tables']['501'][0]['tipo_cambio'] = None
    save(settings, data)
    usd = client.get('/api/v1/reports/analytics', params=params).json()
    assert usd['totals']['igiFp21'] is None
    assert usd['totals']['exportUsd'] == 200
    mxn = client.get('/api/v1/reports/analytics', params=params | {'currency': 'MXN'}).json()
    assert mxn['totals']['igiFp21'] == 40
    assert mxn['totals']['ivaFp21'] == 320
    assert mxn['totals']['importMxn'] is None
    assert mxn['totals']['exportMxn'] == 4000
