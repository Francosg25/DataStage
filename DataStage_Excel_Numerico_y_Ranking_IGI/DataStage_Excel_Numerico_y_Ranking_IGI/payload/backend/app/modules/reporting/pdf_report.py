"""Render the same authorized analytics snapshot used by the dashboard, in memory."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

# Names already validated for the interface against the supplied Anexo 22.
CUSTOMS = {
    '160': 'Manzanillo', '240': 'Nuevo Laredo', '270': 'Piedras Negras',
    '271': 'Aeropuerto Plan de Guadalupe', '430': 'Veracruz',
    '470': 'Aeropuerto Ciudad de Mexico', '480': 'Guadalajara', '520': 'Monterrey',
    '521': 'Aeropuerto Mariano Escobedo', '651': 'San Cayetano Morelos, Toluca',
    '730': 'Aguascalientes', '731': 'Interpuerto San Luis Potosi',
    '800': 'Colombia, Nuevo Leon', '810': 'Altamira', '840': 'Guanajuato',
    '850': 'Aeropuerto Felipe Angeles',
}
MONTHS = {
    'es': 'Enero Febrero Marzo Abril Mayo Junio Julio Agosto Septiembre Octubre Noviembre Diciembre'.split(),
    'en': 'January February March April May June July August September October November December'.split(),
}


def render_report(report, language='es'):
    def t(es, en):
        return es if language == 'es' else en

    def fmt(value, digits=0):
        return t('N/D', 'N/A') if value is None else f'{value:,.{digits}f}'

    def pct(value):
        return fmt(value, 2) + ('%' if value is not None else '')

    body = ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=13,
                          textColor=colors.HexColor('#25343d'), spaceAfter=7)
    heading = ParagraphStyle('heading', parent=body, fontName='Helvetica-Bold', fontSize=19,
                             leading=24, spaceAfter=15, keepWithNext=True)
    subheading = ParagraphStyle('subheading', parent=body, fontName='Helvetica-Bold', fontSize=11,
                                leading=15, spaceBefore=13, spaceAfter=9, keepWithNext=True)
    cell = ParagraphStyle('cell', parent=body, fontSize=8, leading=10, spaceAfter=0)
    numeric = ParagraphStyle('numeric', parent=cell, alignment=TA_RIGHT)
    header = ParagraphStyle('header', parent=cell, fontName='Helvetica-Bold', textColor=colors.white)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=11, wordWrap='CJK')

    def p(value, style=body):
        return Paragraph(escape(str(value)), style)

    story = []

    def title(text):
        story.extend([p(text, heading), p(period + ' | ' + report['currency'])])

    def table(headers, rows, widths, total=False):
        cells = [[p(v, header) for v in headers]]
        cells.extend([[p(v, cell if i == 0 else numeric) for i, v in enumerate(row)] for row in rows])
        result = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
        commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#145c56')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f6')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, colors.HexColor('#145c56')),
        ]
        if total:
            commands += [('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dceeea')),
                         ('LINEABOVE', (0, -1), (-1, -1), 0.7, colors.HexColor('#145c56'))]
        result.setStyle(TableStyle(commands))
        story.extend([result, Spacer(1, 9)])

    months = [m for m in report['monthly'] if report['startMonth'] <= m['month'] <= report['endMonth']]
    def month_name(month):
        return MONTHS[language][month - 1]
    period = f"{month_name(report['startMonth'])} - {month_name(report['endMonth'])} {report['year']}"
    currency = report['currency']
    import_key, export_key = 'import' + currency.title(), 'export' + currency.title()
    f = report['appliedFilters']
    totals = report['totals']
    title(t('Reporte general de operaciones', 'General operations report'))
    story.append(p(t('Fuente: ', 'Source: ') + (
        t('Excel de referencia', 'Reference workbook') if report['source'] == 'reference'
        else t('Versiones mensuales publicadas', 'Published monthly versions'))))
    story.append(p(t('Filtros aplicados', 'Applied filters') + ': ' + ' | '.join([
        t('Operacion ', 'Operation ') + (f['operation'] or t('Todas', 'All')),
        t('Aduana ', 'Customs ') + (f['customs'] or t('Todas', 'All')),
        t('Documento ', 'Document ') + (f['document'] or t('Todos', 'All')),
    ])))
    coverage = report['coverage']
    story.append(p(t('Cobertura: ', 'Coverage: ') +
                   f"{len(coverage['availableMonths'])}/{coverage['requestedMonths']} " +
                   t('meses disponibles. Los meses sin fuente no son cero.',
                     'months available. Months without a source are not zero.')))
    table([t('Indicador del periodo', 'Period metric'), t('Valor', 'Value')], [
        [t('Pedimentos (501)', 'Declarations (501)'), fmt(totals['declarations'])],
        [t('Valor de importaciones (551)', 'Import goods value (551)'), fmt(totals[import_key], 2) + ' ' + currency],
        [t('Valor de exportaciones (551)', 'Export goods value (551)'), fmt(totals[export_key], 2) + ' ' + currency],
        ['IGI - FP 0', fmt(totals['igiPaid'], 2) + ' ' + currency],
        ['IVA - FP 0', fmt(totals['ivaPaid'], 2) + ' ' + currency],
        ['IVA - FP 21', fmt(totals['ivaFp21'], 2) + ' ' + currency],
        [t('Rectificaciones (701)', 'Amendments (701)'), fmt(totals['rectifications'])],
        [t('Seleccion en rojo (SEL)', 'Red selection (SEL)'), pct(totals['redRate'])],
    ], [320, 195])
    story.append(p(t('Evolucion mensual', 'Monthly performance'), subheading))
    table([t('Mes', 'Month'), t('Pedimentos', 'Declarations'), t('Valor importacion', 'Import goods value'),
           t('Valor exportacion', 'Export goods value')], [
        [month_name(m['month']), fmt(m['metrics']['declarations']), fmt(m['metrics'][import_key], 2),
         fmt(m['metrics'][export_key], 2)] for m in months
    ], [85, 90, 170, 170])

    story.append(PageBreak())
    title(t('Contribuciones por forma de pago', 'Taxes by payment method'))
    story.append(p(t('Importaciones verificadas en 551. Importes de 557 separados por FormaPago: '
                     'FP 0 = efectivo; FP 21 = credito en IVA e IEPS (CERTIVA). El credito no se suma al efectivo.',
                     'Imports verified in 551. Amounts from 557 split by payment method: '
                     'FP 0 = cash; FP 21 = VAT/excise credit (CERTIVA). Credit is not added to cash.')))
    def payment_row(label, values):
        return [label, fmt(values['cash']['igi'], 2), fmt(values['cash']['iva'], 2), fmt(values['certiva']['iva'], 2)]
    table([t('Mes', 'Month'), 'IGI FP 0', 'IVA FP 0', 'IVA FP 21'],
          [payment_row(month_name(m['month']), m['paymentMethods']) for m in months] +
          [payment_row('Total', report['paymentMethods'])], [85, 140, 140, 150], total=True)
    other = report['paymentMethods'].get('other', [])
    if other:
        story.append(p(t('Otras formas de pago del rango', 'Other payment methods in the range'), subheading))
        names = {'13': t('Pago ya efectuado', 'Previously paid'),
                 '22': t('Garantia en IVA e IEPS', 'VAT/excise guarantee')}
        table([t('Forma de pago', 'Payment method'), t('Registros importacion', 'Import records'), 'IGI', 'IVA'],
              [[('FP ' + row['code'] + ' - ' + names.get(row['code'], t('Otra forma', 'Other method'))),
                fmt(row['rows']), fmt(row['igi'], 2), fmt(row['iva'], 2)] for row in other], [215, 100, 100, 100])
        story.append(p(t('No se suman al efectivo. FP 13 corresponde a pago ya efectuado; FP 22 es garantia, no credito FP 21.',
                         'Not added to cash. FP 13 is previously paid; FP 22 is a guarantee, not FP 21 credit.')))
        if any(row['unmatchedRows'] for row in other):
            story.append(p(t('Hay registros sin partida u operacion verificable; los importes de su forma de pago quedan sin dato.',
                             'Some records have no verified item or operation; amounts for their payment method are unavailable.')))
    story.append(p(t('Principales numeros de parte por IGI en efectivo', 'Top part numbers by cash import duty'), subheading))
    top = sorted([r for r in report['partTaxes']['rows'] if r['partNumber'] and r['igi'] is not None and r['igi'] > 0],
                 key=lambda r: (-r['igi'], r['partNumber'], r['tariff']))[:10]
    if not report['partTaxes']['available'] or not report['partTaxes']['observationSourceAvailable'] or any(
            r['partNumber'] and r['igi'] is None for r in report['partTaxes']['rows']):
        top = []
    table([t('Numero de parte', 'Part number'), t('Fraccion', 'Tariff'), 'IGI FP 0', 'IVA FP 0'],
          [[r['partNumber'], r['tariff'], fmt(r['igi'], 2), fmt(r['iva'], 2)] for r in top] or
          [[t('Sin datos identificables', 'No identifiable data'), '', '', '']], [185, 100, 115, 115])

    story.append(PageBreak())
    title(t('Rectificaciones por aduana y patente', 'Amendments by customs office and broker'))
    rect = report['rectificationsByCustoms']
    story.append(p(t('Pedimentos rectificados: pedimentos distintos registrados en 701. El documento puede conservar '
                     'claves AF, IN, RT u otras; no se filtra exclusivamente por ClaveDocumento = R1.',
                     'Amended declarations: distinct declarations recorded in 701. Document codes may remain AF, IN, RT '
                     'or others; records are not restricted to DocumentCode = R1.')))
    story.append(p(t('Base global con los filtros aplicados: ', 'Global base under the applied filters: ') +
                   fmt(rect['globalDeclarations']) + t(' pedimentos de 501.', ' declarations from 501.')))
    def group_row(label, row):
        return [label, fmt(row['r1']), fmt(row['declarations']), pct(row['groupRate']), pct(row['globalRate'])]
    table([t('Aduana', 'Customs office'), t('Patente', 'Broker license'), t('Rectificados', 'Amended'),
           t('Pedimentos', 'Declarations'), t('% aduana / patente', '% office / broker'), '% global'],
          [[row['customs'] + ' - ' + CUSTOMS.get(row['customs'], t('Sin descripcion validada', 'Description not verified')),
            *group_row(row['patent'], row)] for row in rect['customsPatentRows']] +
          [[t('Total', 'Total'), '', fmt(rect['totals']['r1']), fmt(rect['totals']['declarations']),
            pct(rect['totals']['officeRate']), pct(rect['totals']['globalRate'])]], [180, 55, 75, 85, 65, 55], total=True)
    story.append(p(t('% aduana / patente = rectificados de esa combinacion / sus pedimentos x 100. '
                     '% global = rectificados de esa combinacion / total de pedimentos filtrados x 100. '
                     'El total porcentual se recalcula; no se promedian porcentajes.',
                     '% office / broker = amended for the pair / declarations for the pair x 100. '
                     '% global = pair amended / total filtered declarations x 100. '
                     'Total percentages are recalculated, not averaged.')))

    story.append(PageBreak())
    title(t('Rectificaciones por patente', 'Amendments by broker license'))
    story.append(p(t('Agrupa todas las aduanas de la seleccion por patente. Base global: ',
                     'Combines all selected customs offices by broker license. Global base: ') +
                   fmt(rect['globalDeclarations']) + t(' pedimentos.', ' declarations.')))
    table([t('Patente', 'Broker license'), t('Rectificados', 'Amended'), t('Pedimentos', 'Declarations'),
           t('% patente', '% broker'), '% global'],
          [group_row(row['patent'], row) for row in rect['patentRows']] +
          [[t('Total', 'Total'), fmt(rect['totals']['r1']), fmt(rect['totals']['declarations']),
            pct(rect['totals']['officeRate']), pct(rect['totals']['globalRate'])]], [105, 100, 110, 100, 100], total=True)
    story.append(p(t('% patente = rectificados de la patente / pedimentos de la patente x 100. '
                     'Ambas tablas describen la misma base: no se suman sus totales. '
                     'Una rectificacion no demuestra por si sola un error o responsabilidad.',
                     '% broker = broker amended / broker declarations x 100. '
                     'Both tables describe the same base: do not add their totals. '
                     'An amendment alone does not establish an error or responsibility.')))

    story.append(PageBreak())
    title(t('Calidad, criterios y trazabilidad', 'Quality, methodology and provenance'))
    parts, payments = report['partTaxes'], report['paymentMethods']
    table([t('Control', 'Check'), t('Registros / partidas', 'Records / items')], [
        [t('Partidas sin NP', 'Items missing a part number'), fmt(parts['missingParts'])],
        [t('Partidas con NP ambiguo', 'Items with ambiguous part numbers'), fmt(parts['ambiguousParts'])],
        [t('Llaves de partida incompletas', 'Incomplete item keys'), fmt(parts['invalidItemKeys'])],
        [t('Pagos FP 0 / FP 21 sin cruce verificable', 'Unverified FP 0 / FP 21 payments'),
         f"{payments['cash']['unmatchedRows']} / {payments['certiva']['unmatchedRows']}"],
        [t('Otras formas de pago IGI/IVA excluidas (557)', 'Other excluded IGI/VAT payment methods (557)'), fmt(payments['otherPaymentRows'])],
        [t('501 sin tipo de cambio unico valido', '501 without a unique valid exchange rate'), fmt(coverage['missingExchangeRates'])],
        [t('701 sin correspondencia en 501', '701 not matched to 501'), fmt(rect['unmatchedAmendments'])],
        [t('Llaves invalidas 501 / 701', 'Invalid 501 / 701 keys'), fmt(rect['invalidKeys'])],
    ], [405, 110])
    for es, en in [
        ('La llave de pedimento incluye ano, mes de carga, patente, pedimento y aduana. '
         'Se eliminan repeticiones de esa llave; apariciones en meses diferentes permanecen separadas.',
         'Declaration keys include upload year, month, broker, declaration and customs office. '
         'Duplicate keys are removed; appearances in different months remain separate.'),
        ('IGI = ClaveContribucion 6; IVA = 3. El cruce 551/557 incluye fraccion y secuencia. '
         'Solo TipoOperacion 1. No se suman tablas 510, 557 y 702 entre si.',
         'IGI = tax code 6; VAT = 3. The 551/557 match includes tariff and sequence. '
         'Only operation type 1. Tables 510, 557 and 702 are not added together.'),
        ('USD = ImportePago MXN / TipoCambio de cada pedimento en 501. No se usa una cotizacion actual. '
         'Valores invalidos, tipos de cambio faltantes o cruces ambiguos dejan el agregado sin dato.',
         'USD = MXN payment amount / declaration exchange rate in 501. No current spot rate is used. '
         'Invalid values, missing rates or ambiguous matches leave the aggregate unavailable.'),
        ('N/D no equivale a cero. Los totales corresponden a meses disponibles. Si un mes disponible '
         'carece de una tabla requerida, el agregado afectado queda N/D.',
         'N/A is not zero. Totals cover available months. If an available month lacks a required table, '
         'the affected aggregate is N/A.'),
        ('Valor declarado suma registros 551. No reconstruye el estado final de las operaciones ni '
         'netea rectificaciones contra originales. Las diferencias 702 permanecen separadas.',
         'Declared value sums 551 records. It does not reconstruct final operation states or net '
         'amendments against originals. Differences in 702 remain separate.'),
        ('NP identifica el principal y OTRO NP un alternativo del mismo articulo; el importe se asigna '
         'una sola vez. Las alertas permanecen hasta corregir la fuente.',
         'NP identifies the principal and OTRO NP an alternate for the same item; amounts are assigned '
         'once. Alerts remain until the source is corrected.'),
    ]:
        story.append(p(t(es, en), small))
    story.append(p(t('Fuentes del corte', 'Snapshot sources'), subheading))
    for source in report['sources']:
        story.append(p(source['file'] + ' | SHA-256: ' + source['sha256'], small))
    for month in months:
        if month['runId']:
            story.append(p(f"{month_name(month['month'])}: {month['runId']} | v{month['version']}", small))
    reconciliation = report.get('reconciliation')
    if reconciliation and not reconciliation['matched']:
        story.append(p(t('Advertencia: diferencias entre referencias: ', 'Warning: reference differences: ') +
                       '; '.join(f"{r['period']} / {r['table']}" for r in reconciliation['differences']), small))
    story.append(p(t('Generado (UTC): ', 'Generated (UTC): ') + report['generatedAt'], small))
    story.append(p('Snapshot SHA-256: ' + report['snapshotId'], small))

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=40, rightMargin=40,
                            topMargin=70, bottomMargin=45, title=t('DataStage - Reporte general', 'DataStage - General report'),
                            author='DataStage', pageCompression=1)

    def page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#145c56'))
        canvas.rect(0, A4[1] - 42, A4[0], 42, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 12)
        canvas.drawString(40, A4[1] - 27, 'DataStage')
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(A4[0] - 40, A4[1] - 26, t('OPERACIONES ADUANERAS', 'CUSTOMS OPERATIONS'))
        canvas.setFillColor(colors.HexColor('#536773'))
        canvas.drawString(40, 24, period + ' | ' + currency)
        canvas.drawRightString(A4[0] - 40, 24, t('Pagina ', 'Page ') + str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()

