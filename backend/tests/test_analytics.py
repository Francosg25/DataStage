import json
from decimal import Decimal

from app.modules.identity.auth import Principal, current_principal
from app.modules.reporting.analytics import change, number
import test_api_worker
from test_api_worker import upload, drain

system = test_api_worker.system


def install_reference(settings, tmp_path):
    base = {'year': 2026, 'patente': '0036', 'pedimento': '0000009', 'seccion_aduanera': '240'}
    january = base | {'month': 1, 'tipo_operacion': '1', 'clave_documento': 'A1'}
    february = base | {'month': 2, 'tipo_operacion': '2', 'clave_documento': 'V1'}
    data = {'schemaVersion': 1, 'scopeId': 'local', 'sources': [], 'periods': [
        {'year': 2026, 'month': m, 'name': name, 'rows': 20, 'tables': dict.fromkeys(['501','551','505','510','557','702','701','sel','inci'], 1)}
        for m, name in [(1,'Enero_2026'),(2,'Febrero_2026')]], 'tables': {
            '501': [january, february],
            '551': [january | {'valor_dolares': '0.1', 'valor_aduana':'100', 'valor_comercial':'90'},
                    january | {'valor_dolares':'0.2', 'valor_aduana':'200', 'valor_comercial':'180'},
                    february | {'valor_dolares':'0', 'valor_aduana':'0', 'valor_comercial':'0'}],
            '505': [january | {'valor_dolares':'999'}, january | {'valor_dolares':'999'}],
            '510': [january | {'importe_pago':'10', 'forma_pago':'0','clave_contribucion':'1'}],
            '557': [january | {'importe_pago':'50'}],
            '702': [january | {'importe_pago':'5'}],
            'sel': [january | {'semaforo_fiscal':c} for c in ['0','1','9']],
            'inci': [january | {'grado_incidencia':c} for c in ['C','G','S']],
        }}
    path = tmp_path / 'reference.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    settings.analytics_reference_file = path
    return data


def test_numeric_contract():
    assert number('0.00') == Decimal(0)
    assert number('NaN') is None
    assert number('Infinity') is None
    assert number('invalid') is None
    assert number('') is None
    assert change(10, 0) is None
    assert change(10, None) is None
    assert change(0, 10) == -100


def test_reference_grains_currency_and_null_months(system, tmp_path):
    _, client, settings = system
    install_reference(settings, tmp_path)
    response = client.get('/api/v1/reports/analytics', params={'source':'reference','year':2026})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['totals']['declarations'] == 2
    assert data['totals']['tradeUsd'] == 0.3
    assert data['totals']['headerPaymentsMxn'] == 10
    assert data['totals']['itemPaymentsMxn'] == 50
    assert data['totals']['paymentDifferencesMxn'] == 5
    assert data['totals']['redRate'] == 50
    assert data['totals']['correctInspections'] == 1
    assert data['totals']['seriousIncidents'] == 1
    assert data['monthly'][1]['metrics']['tradeUsd'] == 0
    assert data['monthly'][2]['metrics']['tradeUsd'] is None
    assert data['deltas']['tradeUsd'] == -100
    assert data['coverage']['availableMonths'] == [1, 2]


def test_filters_do_not_multiply_related_rows(system, tmp_path):
    _, client, settings = system
    install_reference(settings, tmp_path)
    data = client.get('/api/v1/reports/analytics', params={'source':'reference','year':2026,'operation':'1'}).json()
    assert data['totals']['declarations'] == 1
    assert data['totals']['tradeUsd'] == 0.3
    assert data['totals']['invoiceUsd'] == 1998
    assert data['totals']['headerPaymentsMxn'] == 10
    assert data['monthly'][1]['metrics']['declarations'] == 0
    assert data['monthly'][1]['rows'] == 20


def test_scope_protection_options_and_validation(system, tmp_path):
    app, client, settings = system
    install_reference(settings, tmp_path)
    assert client.get('/api/v1/reports/analytics/options').json()['defaultSource'] == 'reference'
    assert client.get('/api/v1/reports/analytics', params={'startMonth':10,'endMonth':2}).status_code == 400
    assert client.get('/api/v1/reports/analytics', params={'source':'untrusted'}).status_code == 422
    app.dependency_overrides[current_principal] = lambda: Principal('other','Other',frozenset({'Reader'}),'other')
    assert client.get('/api/v1/reports/analytics', params={'source':'reference'}).status_code == 404
    assert len(client.get('/api/v1/reports/analytics/options').json()['sources']) == 1
    assert client.get('/api/v1/reports/analytics').json()['totals']['declarations'] is None


def test_published_uses_only_active_monthly_version(system):
    app, client, settings = system
    upload(client, {'header_501.asc':'Patente|Pedimento|SeccionAduanera|TipoOperacion|ClaveDocumento|\n0036|0000009|240|1|A1|\n',
                    'items_551.asc':'Patente|Pedimento|SeccionAduanera|TipoOperacion|ClaveDocumento|ValorDolares|\n0036|0000009|240|1|A1|125.50|\n'})
    drain(app,settings)
    data = client.get('/api/v1/reports/analytics',params={'year':2026}).json()
    assert data['totals']['declarations'] == 1
    assert data['totals']['tradeUsd'] == 125.5
    assert data['monthly'][3]['available']
    assert data['monthly'][3]['runId']
    assert data['totals']['headerPaymentsMxn'] is None
