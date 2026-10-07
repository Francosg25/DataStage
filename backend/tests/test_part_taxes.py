from decimal import Decimal

from app.modules.reporting.part_taxes import convert, exchange_rates, extract_parts, paid_taxes


def row(**changes):
    return dict(year=2026, month=1, patente='0036', pedimento='00009', seccion_aduanera='240',
                fraccion='85369099', secuencia_fraccion='1', tipo_operacion='1', **changes)


def dataset(observations=None):
    return {'501': [row(tipo_cambio='20')], '551': [row()],
            '558': observations if observations is not None else [row(observaciones='FACTURA X NP: 0001-ABC', secuencia_observacion='1')],
            '557': [row(clave_contribucion='6', forma_pago='0', importe_pago='100'),
                    row(clave_contribucion='3', forma_pago='0', importe_pago='160'),
                    row(clave_contribucion='1', forma_pago='0', importe_pago='99'),
                    row(clave_contribucion='6', forma_pago='9', importe_pago='1000')]}


def report(data, currency='USD'):
    return paid_taxes(data, data.keys(), currency, exchange_rates(data['501']))


def test_paid_import_taxes_are_not_dta_or_exempt_and_use_declaration_fx():
    result = report(dataset())
    assert result['totals'] == {'igi': 5.0, 'iva': 8.0}
    assert result['rows'][0]['partNumber'] == '0001-ABC'
    assert report(dataset(), 'MXN')['totals'] == {'igi': 100.0, 'iva': 160.0}


def test_multiple_observations_or_duplicate_header_do_not_multiply_payments():
    data = dataset()
    data['501'] *= 2
    data['558'] *= 3
    assert report(data)['totals']['igi'] == 5
    assert report(data)['rows'][0]['items'] == 1


def test_ambiguous_parts_are_never_assigned_full_tax_to_each_part():
    data = dataset([row(observaciones='NP: AA-1 NP: BB-2', secuencia_observacion='1')])
    result = report(data)
    assert result['ambiguousParts'] == 1
    assert result['rows'][0]['partNumber'] is None
    assert result['totals']['igi'] == 5
    assert len(result['rows']) == 1


def test_no_series_lots_or_unlabelled_numbers_inferred_as_part_number():
    assert extract_parts([row(observaciones='No. Series, Partes o Lotes: 12345')]) == []
    assert extract_parts([row(observaciones='12345')]) == []
    assert extract_parts([row(observaciones='ORDEN DE NUMERO DE PARTE 1')]) == []
    assert extract_parts([row(observaciones='NP: N/A')]) == []


def test_split_label_requires_adjacent_observation_sequence():
    observations = [row(observaciones='No.Parte', secuencia_observacion='2'),
                    row(observaciones='001-AB', secuencia_observacion='3')]
    assert extract_parts(observations) == ['001-AB']
    observations[1]['secuencia_observacion'] = '4'
    assert extract_parts(observations) == []


def test_user_np_and_otro_np_example_preserves_both_identifiers():
    assert extract_parts([row(observaciones='NP: 1200-1030847AN OTRO NP: 1200-1030847AND')]) == ['1200-1030847AN', '1200-1030847AND']
    result = report(dataset([row(observaciones='NP: 1200-1030847AN OTRO NP: 1200-1030847AND')]))
    assert result['alerts'] == []
    assert result['totals']['igi'] == 5.0
    assert len(result['rows']) == 1
    assert result['rows'][0]['partNumber'] == '1200-1030847AN'
    assert result['rows'][0]['alternatePartNumbers'] == ['1200-1030847AND']


def test_alias_without_a_principal_requires_review():
    result = report(dataset([row(observaciones='OTRO NP: 1200-1030847AND')]))
    assert result['rows'][0]['partNumber'] is None
    assert result['missingParts'] == 1


def test_historical_rates_are_applied_per_declaration_not_an_average():
    data = dataset()
    second = row(tipo_cambio='25') | {'pedimento': '10'}
    data['501'].append(second)
    data['551'].append(second)
    data['557'].append(second | {'clave_contribucion': '6', 'forma_pago': '0', 'importe_pago': '100'})
    assert report(data)['totals']['igi'] == 9.0  # 100/20 + 100/25
    assert report(data, 'MXN')['totals']['igi'] == 200.0


def test_alert_disappears_only_when_source_is_corrected():
    data = dataset([])
    assert report(data)['missingParts'] == 1
    assert report(data)['missingParts'] == 1
    data['558'] = [row(observaciones='NP: FIXED')]
    assert report(data)['alerts'] == []


def test_missing_or_conflicting_fx_does_not_produce_partial_dollar_total():
    data = dataset()
    data['501'] += [row(tipo_cambio='21')]
    assert report(data)['totals']['igi'] is None
    assert report(data, 'MXN')['totals']['igi'] == 100
    assert convert(row(importe_pago='0'), 'importe_pago', 'MXN', 'USD', {}) == Decimal(0)


def test_exports_are_not_igi_and_orphan_payments_are_flagged():
    data = dataset()
    data['551'][0]['tipo_operacion'] = '2'
    assert report(data)['totals']['igi'] == 0
    data['551'] = []
    assert report(data)['unmatchedTaxRows'] == 2
    assert report(data)['totals']['igi'] is None


def test_missing_source_is_not_zero():
    data = dataset()
    result = paid_taxes(data, {'501', '551'}, 'USD', exchange_rates(data['501']))
    assert result['totals']['igi'] is None
    assert not result['available']
