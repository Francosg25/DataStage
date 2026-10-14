"""The supplied PN failures must resolve without inventing aliases or duplicating payments."""
import pytest

from app.modules.reporting import part_taxes
from test_part_taxes import dataset, report, row
import test_api_worker
from test_kpi_payment_methods import install_kpis, save

system = test_api_worker.system


@pytest.mark.parametrize('text,expected', [
    ('N. DE PARTE: 1616-5TP1037N. DE FACTURA: MXO-31627', '1616-5TP1037N'),
    ('DESCRIPCION DEL ARTICULO: 1651-EQM0165EN MOTOR ELECTRICO', '1651-EQM0165EN'),
    ('OBSERVACION: 1999-5YY1117EN.', '1999-5YY1117EN'),
    ('n. de parte: 1616-5tp1037n.', '1616-5TP1037N'),
    ('NP: 3.517.817.01.', '3.517.817.01'),
])
def test_user_labels_embedded_catalog_codes_and_terminal_punctuation(monkeypatch, text, expected):
    monkeypatch.setattr(part_taxes, 'KNOWN_PARTS', frozenset({'1651-EQM0165EN', '1999-5YY1117EN'}))
    assert part_taxes.part_numbers([row(observaciones=text)]) == ([expected], [])


def test_all_catalog_codes_are_found_as_whole_tokens_inside_descriptions():
    for code in part_taxes.KNOWN_PARTS:
        for text in (f'DESCRIPCION: ARTICULO {code} PARA USO AUTOMOTRIZ',
                     f'OBSERVACIONES: ({code}). MATERIAL',
                     f'PRODUCTO: {code.lower()}.'):
            assert part_taxes.part_numbers([row(observaciones=text)]) == ([code], [])


@pytest.mark.parametrize('suffix', ['N', 'EN'])
def test_packaging_suffix_matches_an_exact_registered_base_and_keeps_the_observed_alias(monkeypatch, suffix):
    base = '1616-5TP1037'
    observed = base + suffix
    monkeypatch.setattr(part_taxes, 'KNOWN_PARTS', frozenset({base}))
    observations = [row(observaciones=f'N. DE PARTE: {observed}. NP: {base}', secuencia_observacion='1')]
    assert part_taxes.part_numbers(observations) == ([base], [observed])
    result = report(dataset(observations * 3))
    assert not result['alerts']
    assert len(result['rows']) == 1
    assert result['rows'][0]['partNumber'] == base
    assert result['rows'][0]['alternatePartNumbers'] == [observed]
    assert result['totals'] == {'igi': 5.0, 'iva': 8.0}
    assert result['rows'][0]['igi'] == 5
    assert part_taxes.part_numbers([row(observaciones=f'DESCRIPCION: {observed}.')]) == ([base], [observed])


def test_exact_registered_suffix_is_not_stripped_and_unknown_suffixes_are_not_guessed(monkeypatch):
    base = '1616-5TP1037'
    full = base + 'N'
    monkeypatch.setattr(part_taxes, 'KNOWN_PARTS', frozenset({base, full}))
    assert part_taxes.part_numbers([row(observaciones=full)]) == ([full], [])
    for token in (base + 'X', 'X' + base, base[:-1] + '8EN', base + '-N'):
        assert part_taxes.part_numbers([row(observaciones=f'DESCRIPCION: {token}')]) == ([], [])


def test_explicit_alternates_and_split_alternates_are_not_promoted_by_catalog_scanning():
    known = '1651-EQM0165EN'
    for text in (f'NP: UNKNOWN-1 | OTRO NP: {known}.', f'NP: UNKNOWN-1 | OTRO NP | {known}.'):
        assert part_taxes.part_numbers([row(observaciones=text)]) == (['UNKNOWN-1'], [known])
    result = report(dataset([row(observaciones=f'OTRO NP: {known}.')]))
    assert result['rows'][0]['partNumber'] is None
    assert result['missingParts'] == 1


def test_catalog_mentions_in_series_models_invoices_or_orders_are_not_parts():
    known = '1651-EQM0165EN'
    for text in (f'SERIE: {known}.', f'MODELO: {known}.', f'FACTURA {known}.',
                 f'P.O {known}', f'LOT: {known}.', f'ORDEN DE NUMERO DE PARTE {known}'):
        assert part_taxes.part_numbers([row(observaciones=text)]) == ([], [])


def test_two_different_part_bodies_remain_ambiguous_even_with_packaging_suffixes(monkeypatch):
    bases = {'1616-5TP1037', '1616-5TP1038'}
    monkeypatch.setattr(part_taxes, 'KNOWN_PARTS', frozenset(bases))
    result = report(dataset([row(observaciones='NP: 1616-5TP1037N | NP: 1616-5TP1038EN')]))
    assert result['ambiguousParts'] == 1
    assert result['rows'][0]['partNumber'] is None
    assert result['alerts'][0]['candidates'] == sorted(bases | {'1616-5TP1037N', '1616-5TP1038EN'})
    assert len(result['rows']) == 1
    assert result['totals']['igi'] == 5


def test_principal_in_prose_and_an_explicit_alternate_keep_their_roles():
    text = 'DESCRIPCION: 1651-EQM0165EN | OTRO NP: 1999-5YY1117EN'
    result = report(dataset([row(observaciones=text)]))
    assert result['rows'][0]['partNumber'] == '1651-EQM0165EN'
    assert result['rows'][0]['alternatePartNumbers'] == ['1999-5YY1117EN']
    assert result['rows'][0]['igi'] == 5


@pytest.mark.parametrize('currency,expected', [('USD', [10, 15]), ('MXN', [100, 300])])
def test_report_api_resolves_packaging_and_embedded_parts_and_preserves_totals(system, tmp_path, monkeypatch, currency, expected):
    _, client, settings = system
    data = install_kpis(settings, tmp_path)
    base = '1616-5TP1037'
    monkeypatch.setattr(part_taxes, 'KNOWN_PARTS', frozenset({base, '1651-EQM0165EN'}))
    data['tables']['558'] = [
        item | {'secuencia_observacion': '1',
                'observaciones': 'N. DE PARTE: 1616-5TP1037N.' if item['month'] == 1 else 'DESCRIPCION: 1651-EQM0165EN MOTOR'}
        for item in data['tables']['551'] if item['tipo_operacion'] == '1'
    ]
    for period in data['periods']:
        period['tables']['558'] = 1
    save(settings, data)
    params = dict(source='reference', year=2026, startMonth=1, endMonth=2, currency=currency)
    response = client.get('/api/v1/reports/analytics', params=params)
    assert response.status_code == 200
    report = response.json()
    records = {row['partNumber']: row for row in report['partTaxes']['rows']}
    assert records[base]['alternatePartNumbers'] == [base + 'N']
    assert records[base]['igi'] == expected[0]
    assert records['1651-EQM0165EN']['igi'] == expected[1]
    assert report['totals']['igiPaid'] == sum(expected)
    assert client.get('/api/v1/reports/analytics', params=params).json()['snapshotId'] == report['snapshotId']
