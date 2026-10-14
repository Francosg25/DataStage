"""Regression tests for the population, currency and missing-data meaning of charts."""
import json

from app.modules.reporting.analytics import declaration_ranking, ranking, total
from app.modules.reporting.part_taxes import exchange_rates, payment_method_totals
from test_analytics import install_reference
from test_analytics_reporting import item
import test_api_worker

system = test_api_worker.system


def report_for(client, settings, data):
    settings.analytics_reference_file.write_text(json.dumps(data), encoding='utf-8')
    response = client.get('/api/v1/reports/analytics', params={'source': 'reference', 'year': 2026})
    assert response.status_code == 200
    return response.json()


def test_declaration_rankings_share_the_kpi_population(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    data['tables']['501'].append(dict(data['tables']['501'][0]))
    result = report_for(client, settings, data)
    for dimension in ('customs', 'documents', 'operations'):
        assert sum(row['value'] for row in result['breakdowns'][dimension]) == result['totals']['declarations'] == 2
    assert result['coverage']['duplicateDeclarationRows'] == 1
    # Conflicting categories still represent one declaration, not two.
    rows = declaration_ranking([item(), item(clave_documento='RT')], 'clave_documento')
    assert rows == [{'key': 'unknown', 'value': 1, 'rows': 1}]


def test_incomplete_keys_do_not_disappear_from_declaration_counts(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    data['tables']['501'][0]['patente'] = ''
    result = report_for(client, settings, data)
    assert result['totals']['declarations'] is None
    assert result['breakdowns']['customs'] == []
    assert result['coverage']['invalidDeclarationKeys'] == 1
    assert result['coverage']['duplicateDeclarationRows'] == 0


def test_missing_table_blocks_partial_totals_but_keeps_valid_months(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    del data['periods'][1]['tables']['551']
    data['tables']['551'] = [r for r in data['tables']['551'] if r['month'] == 1]
    result = report_for(client, settings, data)
    assert result['totals']['tradeUsd'] is None
    assert result['totals']['items'] is None
    assert result['monthly'][0]['metrics']['tradeUsd'] == 0.3
    assert result['monthly'][1]['metrics']['tradeUsd'] is None
    assert result['coverage']['incompleteTables'] == ['551']
    assert all(row['value'] is None for row in result['breakdowns']['tariffs'])


def test_origins_and_destinations_do_not_mix_the_same_country(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    for row in data['tables']['551']:
        row['pais_origen_destino'] = 'USA'
    data['tables']['551'][-1]['valor_dolares'] = '20'
    result = report_for(client, settings, data)
    assert result['breakdowns']['originCountries'] == [{'key': 'USA', 'value': 0.3, 'rows': 2}]
    assert result['breakdowns']['destinationCountries'] == [{'key': 'USA', 'value': 20, 'rows': 1}]


def test_invalid_numeric_values_are_never_summed_as_zero_including_other_bucket():
    assert total([{'value': '100'}, {'value': ''}], 'value') is None
    assert total([], 'value') == 0
    result = ranking([{'key': str(i), 'value': str(i)} for i in range(1, 10)] +
                     [{'key': 'invalid', 'value': 'bad'}], 'key', 'value', limit=8)
    assert result[-1]['key'] == 'other'
    assert result[-1]['value'] is None


def test_other_payment_methods_exclude_exports_and_preserve_official_distinctions():
    imported, exported = item(), item(pedimento='10', tipo_operacion='2')
    payments = [imported | dict(clave_contribucion='3', forma_pago=fp, importe_pago=amount)
                for fp, amount in [('0', '100'), ('13', '200'), ('21', '300'), ('22', '400')]]
    payments.append(exported | dict(clave_contribucion='3', forma_pago='13', importe_pago='9999'))
    tables = {'551': [imported, exported], '557': payments}
    result = payment_method_totals(tables, {'551', '557'}, 'USD', exchange_rates([imported, exported]))
    assert result['cash']['iva'] == 5
    assert result['certiva']['iva'] == 15
    assert [(r['code'], r['iva'], r['rows']) for r in result['other']] == [('13', 10, 1), ('22', 20, 1)]
    assert result['otherPaymentRows'] == 2


def test_unverified_other_payments_do_not_contaminate_cash_or_hide_unknown_operations():
    base = item()
    invalid = item(pedimento='20', tipo_operacion='9')
    result = payment_method_totals({'551': [base, invalid], '557': [
        base | dict(clave_contribucion='6', forma_pago='0', importe_pago='100'),
        invalid | dict(clave_contribucion='6', forma_pago='13', importe_pago='200'),
    ]}, {'551', '557'}, 'MXN', {})
    assert result['cash']['igi'] == 100
    assert result['other'][0]['igi'] is None
    assert result['otherUnmatchedRows'] == 1
    assert result['otherPaymentRows'] == 0


def test_selection_rate_is_available_only_for_fully_classified_events(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    data['tables']['sel'] = data['tables']['sel'][:2]
    result = report_for(client, settings, data)
    assert result['totals']['redRate'] == 50
    assert result['totals']['unclassifiedSelections'] == 0


def test_rectification_monthly_series_also_counts_distinct_declarations(system, tmp_path):
    _, client, settings = system
    data = install_reference(settings, tmp_path)
    data['tables']['701'] = [dict(data['tables']['501'][0])] * 3
    result = report_for(client, settings, data)
    assert result['totals']['rectifications'] == 1
    assert result['rectifications'][0]['values'][0] == 1
