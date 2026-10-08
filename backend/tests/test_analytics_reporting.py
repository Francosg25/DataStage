import json

import pytest

from app.modules.identity.auth import Principal, current_principal
from app.modules.reporting.part_taxes import exchange_rates, payment_method_totals
from app.modules.reporting.rectifications import rectifications_by_customs
from app.modules.reporting.pdf_report import render_report
from test_analytics import install_reference
import test_api_worker

system = test_api_worker.system


def item(**changes):
    return dict(year=2026, month=1, patente='0036', pedimento='0000009', seccion_aduanera='240',
                fraccion='12345678', secuencia_fraccion='1', tipo_operacion='1',
                clave_documento='AF', tipo_cambio='20') | changes


def test_payment_methods_remain_separate_and_ignore_exports_and_other_taxes():
    imported, exported = item(), item(pedimento='10', tipo_operacion='2')
    tables = {'551': [imported, imported, exported], '557': [
        imported | dict(clave_contribucion='6', forma_pago='0', importe_pago='100'),
        imported | dict(clave_contribucion='3', forma_pago='0', importe_pago='80'),
        imported | dict(clave_contribucion='3', forma_pago='21', importe_pago='320'),
        imported | dict(clave_contribucion='6', forma_pago='21.0', importe_pago='40'),
        imported | dict(clave_contribucion='6', forma_pago='9', importe_pago='999'),
        imported | dict(clave_contribucion='1', forma_pago='0', importe_pago='999'),
        exported | dict(clave_contribucion='3', forma_pago='0', importe_pago='999'),
    ]}
    usd = payment_method_totals(tables, {'551', '557'}, 'USD', exchange_rates([imported, exported]))
    assert usd == {'cash': {'igi': 5, 'iva': 4, 'unmatchedRows': 0},
                   'certiva': {'igi': 2, 'iva': 16, 'unmatchedRows': 0}, 'otherPaymentRows': 1}
    mxn = payment_method_totals(tables, {'551', '557'}, 'MXN', {})
    assert mxn['cash']['igi'] == 100
    assert mxn['certiva']['iva'] == 320


@pytest.mark.parametrize('coverage', [set(), {'551'}, {'557'}])
def test_missing_payment_tables_are_not_zero(coverage):
    result = payment_method_totals({'551': [], '557': []}, coverage, 'MXN', {})
    assert result['cash']['igi'] is None
    assert result['certiva']['iva'] is None


def test_unmatched_certiva_does_not_invalidate_verified_cash():
    base = item()
    tables = {'551': [base], '557': [
        base | dict(clave_contribucion='6', forma_pago='0', importe_pago='100'),
        item(secuencia_fraccion='2', clave_contribucion='3', forma_pago='21', importe_pago='200'),
    ]}
    result = payment_method_totals(tables, {'551', '557'}, 'MXN', {})
    assert result['cash']['igi'] == 100
    assert result['certiva']['iva'] is None
    assert result['certiva']['unmatchedRows'] == 1


@pytest.mark.parametrize('amount,rate', [('invalid', '20'), ('100', None), ('100', '0')])
def test_invalid_amounts_or_rates_are_unavailable(amount, rate):
    base = item(tipo_cambio=rate)
    result = payment_method_totals({'551': [base], '557': [
        base | dict(clave_contribucion='3', forma_pago='21', importe_pago=amount)]},
        {'551', '557'}, 'USD', exchange_rates([base]))
    assert result['certiva']['iva'] is None
    assert result['cash']['igi'] == 0


def test_rectifications_count_distinct_keys_and_recompute_rates():
    a, b, c = item(), item(pedimento='10'), item(pedimento='11', seccion_aduanera='160')
    result = rectifications_by_customs({'501': [a, a, b, c], '701': [a, a, c]}, [{'tables': {'501': 4, '701': 3}}])
    assert result['globalDeclarations'] == 3
    assert result['totals'] == {'r1': 2, 'declarations': 3, 'officeRate': 66.67, 'globalRate': 66.67}
    assert result['rows'] == [
        {'customs': '160', 'r1': 1, 'declarations': 1, 'officeRate': 100, 'globalRate': 33.33},
        {'customs': '240', 'r1': 1, 'declarations': 2, 'officeRate': 50, 'globalRate': 33.33}]


def test_missing_rectification_coverage_and_orphans_do_not_create_valid_rates():
    base = item()
    tables = {'501': [base], '701': [item(pedimento='10')]}
    result = rectifications_by_customs(tables, [{'tables': {'501': 1, '701': 1}}])
    assert result['unmatchedAmendments'] == 1
    assert result['rows'][0]['officeRate'] is None
    assert result['totals']['globalRate'] is None
    result = rectifications_by_customs(tables, [{'tables': {'501': 1}}])
    assert not result['available']
    assert result['totals']['r1'] is None
    assert result['globalDeclarations'] is None


def test_invalid_keys_and_empty_denominators_are_explicit():
    result = rectifications_by_customs({'501': [], '701': []}, [{'tables': {'501': 0, '701': 0}}])
    assert result['totals']['r1'] == 0
    assert result['totals']['globalRate'] is None
    result = rectifications_by_customs({'501': [item(patente='')], '701': [item(patente='')]},
                                      [{'tables': {'501': 1, '701': 1}}])
    assert result['invalidKeys'] == 2
    assert result['globalDeclarations'] is None
    assert result['totals']['r1'] is None


def test_report_filters_apply_to_new_tables_and_snapshot(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    data['tables']['701'] = [dict(data['tables']['501'][0])]
    settings.analytics_reference_file.write_text(json.dumps(data), encoding='utf-8')
    params = dict(source='reference', year=2026, startMonth=1, endMonth=1, customs='240', currency='MXN')
    report = client.get('/api/v1/reports/analytics', params=params).json()
    assert report['rectificationsByCustoms']['totals']['r1'] == 1
    assert report['rectificationsByCustoms']['globalDeclarations'] == 1
    assert report['appliedFilters']['customs'] == '240'
    assert report['appliedFilters']['startMonth'] == 1
    assert client.get('/api/v1/reports/analytics', params=params).json()['snapshotId'] == report['snapshotId']
    filtered = client.get('/api/v1/reports/analytics', params=params | {'operation': '2'}).json()
    assert filtered['rectificationsByCustoms']['totals']['r1'] == 0
    assert filtered['rectificationsByCustoms']['totals']['globalRate'] is None
    assert filtered['snapshotId'] != report['snapshotId']


@pytest.mark.parametrize('language', ['es', 'en'])
def test_pdf_is_a_real_protected_download_and_stale_snapshots_fail(system, tmp_path, language):
    app, client, settings = system
    install_reference(settings, tmp_path)
    params = dict(source='reference', year=2026, startMonth=2, endMonth=2, currency='MXN')
    report = client.get('/api/v1/reports/analytics', params=params).json()
    response = client.get('/api/v1/reports/analytics/pdf', params=params | {'language': language, 'snapshot': report['snapshotId']})
    assert response.status_code == 200, response.text
    assert response.content.startswith(b'%PDF-')
    assert response.content.rstrip().endswith(b'%%EOF')
    assert response.headers['content-type'] == 'application/pdf'
    assert f'2026-02-02-MXN-{language}.pdf' in response.headers['content-disposition']
    assert 'no-store' in response.headers['cache-control']
    assert client.get('/api/v1/reports/analytics/pdf', params=params | {'snapshot': '0' * 64}).status_code == 409
    assert client.get('/api/v1/reports/analytics/pdf', params=params | {'language': 'invalid'}).status_code == 422
    app.dependency_overrides[current_principal] = lambda: Principal('user', 'User', frozenset(), 'local')
    assert client.get('/api/v1/reports/analytics/pdf', params=params).status_code == 403
    app.dependency_overrides[current_principal] = lambda: Principal('other', 'Other', frozenset({'Reader'}), 'other')
    assert client.get('/api/v1/reports/analytics/pdf', params=params).status_code == 404
    app.dependency_overrides.clear()
    app.state.settings = settings.model_copy(update={'auth_mode': 'entra'})
    assert client.get('/api/v1/reports/analytics/pdf', params=params).status_code == 401


def test_pdf_handles_empty_data_and_escapes_source_markup(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    data['sources'] = [{'file': '<img src="https://invalid/"> & source', 'sha256': 'f' * 64}]
    settings.analytics_reference_file.write_text(json.dumps(data), encoding='utf-8')
    report = client.get('/api/v1/reports/analytics', params={'source': 'reference', 'startMonth': 3, 'endMonth': 12}).json()
    assert report['rectificationsByCustoms']['totals']['r1'] is None
    assert report['paymentMethods']['cash']['igi'] is None
    assert render_report(report).startswith(b'%PDF-')
