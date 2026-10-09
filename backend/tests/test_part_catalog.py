"""Regression cases from EXCEL NP.xlsx and the supplied 558 observations."""
import unittest

from app.modules.reporting.part_taxes import KNOWN_PARTS, extract_parts, part_numbers
from test_part_taxes import dataset, report, row


class PartCatalogTests(unittest.TestCase):
    def test_catalog_covers_complete_codes_in_supported_contexts(self):
        self.assertEqual(len(KNOWN_PARTS), 381)
        self.assertIn('1905-5YY0781-0000RN', KNOWN_PARTS)
        self.assertIn('1438-8GA0001EN/MX', KNOWN_PARTS)
        for code in sorted(KNOWN_PARTS):
            for text in (
                code,
                f'NP: {code}',
                f'NUMERO DE PARTE {code} ORDEN DE NUMERO DE PARTE 1',
                f'P.O KF203-20260429-D000020 | {code}',
            ):
                with self.subTest(code=code, text=text):
                    self.assertEqual(extract_parts([row(observaciones=text)]), [code])

    def test_catalog_does_not_promote_other_labels_or_partial_codes(self):
        for code in sorted(KNOWN_PARTS):
            for text in (
                f'SERIE: {code}', f'MODELO: {code}', f'FACTURA {code}',
                f'P.O {code}', f'X{code}', f'{code}X',
            ):
                with self.subTest(text=text):
                    self.assertEqual(extract_parts([row(observaciones=text)]), [])

    def test_catalog_keeps_explicit_alternates_as_aliases(self):
        for code in sorted(KNOWN_PARTS):
            with self.subTest(code=code):
                self.assertEqual(
                    part_numbers([row(observaciones=f'NP: UNKNOWN-1 | OTRO NP: {code}')]),
                    (['UNKNOWN-1'], [code]),
                )
                self.assertEqual(
                    part_numbers([row(observaciones=f'NP: UNKNOWN-1 | OTRO NP | {code}')]),
                    (['UNKNOWN-1'], [code]),
                )

    def test_labels_still_allow_new_parts_not_in_the_catalog(self):
        for text, code in (
            ('NF: MX031638 | NP INTERNO: 1908-1129137', '1908-1129137'),
            ('NO. SERIES, PARTES O LOTES: DPZ01M-2GT019A-MLA3+1-00 | '
             'NO.PARTE | DPZ01M-2GT019A-MLA3+1-00 | PO:50800042734-11',
             'DPZ01M-2GT019A-MLA3+1-00'),
            ('NÚMERO DE PARTE: NEW-PART-01', 'NEW-PART-01'),
        ):
            with self.subTest(text=text):
                self.assertNotIn(code, KNOWN_PARTS)
                self.assertEqual(extract_parts([row(observaciones=text)]), [code])

    def test_observation_continuation_requires_adjacent_sequence(self):
        for label, code in (
            ('NP INTERNO:', '1908-1129137'),
            ('NO.PARTE', 'DPZ01M-2GT019A-MLA3+1-00'),
            ('P.O KF203-20260429-D000020', '1905-NEW0001'),
        ):
            observations = [row(observaciones=label, secuencia_observacion='1')]
            with self.subTest(label=label):
                self.assertEqual(extract_parts(observations + [
                    row(observaciones=code, secuencia_observacion='2')]), [code])
                self.assertEqual(extract_parts(observations + [
                    row(observaciones=code, secuencia_observacion='3')]), [])
                self.assertEqual(extract_parts(observations + [row(observaciones=code)]), [])

    def test_repeated_catalog_code_receives_original_tax_once(self):
        data = dataset([row(observaciones='FACTURA MX202300059868 NUMERO DE PARTE '
                                          '1999-5YY1385EN ORDEN DE NUMERO DE PARTE 1')] * 3)
        result = report(data)
        self.assertEqual(result['alerts'], [])
        self.assertEqual(result['rows'][0]['partNumber'], '1999-5YY1385EN')
        self.assertEqual(result['rows'][0]['igi'], 5.0)
        self.assertEqual(result['totals'], {'igi': 5.0, 'iva': 8.0})

    def test_two_real_parts_remain_ambiguous_without_duplicating_taxes(self):
        observations = 'FACTURA MX202300059814 NP: 1999-1WP0113EN DESCRIPCION FACTURA '
        observations += 'BOMBAS DE AGUA PARA USO AUTOMOTRIZFACTURA MX202300059813 | '
        observations += 'WP32G-1WP0113) | NP: 1999-1WP0111EN DESCRIPCION FACTURA BOMBAS '
        observations += 'DE AGUA PARA USO AUTOMOTRIZ(Modelo:WP31G-1WP0111)(Marca: JENA Modelo:'
        result = report(dataset([row(observaciones=observations)]))
        self.assertEqual(result['alerts'][0]['candidates'], ['1999-1WP0111EN', '1999-1WP0113EN'])
        self.assertEqual(result['ambiguousParts'], 1)
        self.assertEqual(len(result['rows']), 1)
        self.assertIsNone(result['rows'][0]['partNumber'])
        self.assertEqual(result['totals'], {'igi': 5.0, 'iva': 8.0})

    def test_order_counter_and_overlong_token_are_not_parts(self):
        for text in ('ORDEN DE NUMERO DE PARTE 1', 'NP: N/A', 'NP: ' + 'A' * 81):
            with self.subTest(text=text):
                self.assertEqual(extract_parts([row(observaciones=text)]), [])
