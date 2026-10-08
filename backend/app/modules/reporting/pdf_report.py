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
    trade_key = 'trade' + currency.title()
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
        [t('Valor de mercancias (551)', 'Trade value (551)'), fmt(totals[trade_key], 2) + ' ' + currency],
        ['IGI - FP 0', fmt(totals['igiPaid'], 2) + ' ' + currency],
        ['IVA - FP 0', fmt(totals['ivaPaid'], 2) + ' ' + currency],
        [t('Rectificaciones (701)', 'Amendments (701)'), fmt(totals['rectifications'])],
        [t('Seleccion en rojo (SEL)', 'Red selection (SEL)'), pct(totals['redRate'])],
    ], [320, 195])
    story.append(p(t('Evolucion mensual', 'Monthly performance'), subheading))
    table([t('Mes', 'Month'), t('Pedimentos', 'Declarations'), t('Mercancias', 'Trade value'),
           'IGI FP 0', 'IVA FP 0'], [
        [month_name(m['month']), fmt(m['metrics']['declarations']), fmt(m['metrics'][trade_key], 2),
         fmt(m['metrics']['igiPaid'], 2), fmt(m['metrics']['ivaPaid'], 2)] for m in months
    ], [85, 70, 126, 117, 117])

    story.append(PageBreak())
    title(t('Contribuciones por forma de pago', 'Taxes by payment method'))
    story.append(p(t('Importaciones verificadas en 551. Importes de 557 separados por FormaPago: '
                     'FP 0 = efectivo; FP 21 = CERTIVA. CERTIVA no se suma al efectivo.',
                     'Imports verified in 551. Amounts from 557 split by payment method: '
                     'FP 0 = cash; FP 21 = CERTIVA. CERTIVA is not added to cash.')))
    def payment_row(label, values):
        return [label] + [fmt(values[method][tax], 2) for method in ('cash', 'certiva') for tax in ('igi', 'iva')]
    table([t('Mes', 'Month'), 'IGI FP 0', 'IVA FP 0', 'IGI FP 21', 'IVA FP 21'],
          [payment_row(month_name(m['month']), m['paymentMethods']) for m in months] +
          [payment_row('Total', report['paymentMethods'])], [85, 107.5, 107.5, 107.5, 107.5], total=True)
    story.append(p(t('Principales numeros de parte por IGI en efectivo', 'Top part numbers by cash import duty'), subheading))
    top = sorted([r for r in report['partTaxes']['rows'] if r['partNumber'] and r['igi'] is not None and r['igi'] > 0],
                 key=lambda r: (-r['igi'], r['partNumber'], r['tariff']))[:10]
    table([t('Numero de parte', 'Part number'), t('Fraccion', 'Tariff'), 'IGI FP 0', 'IVA FP 0'],
          [[r['partNumber'], r['tariff'], fmt(r['igi'], 2), fmt(r['iva'], 2)] for r in top] or
          [[t('Sin datos identificables', 'No identifiable data'), '', '', '']], [185, 100, 115, 115])

    story.append(PageBreak())
    title(t('Rectificaciones por aduana', 'Amendments by customs office'))
    rect = report['rectificationsByCustoms']
    story.append(p(t('R1: pedimentos distintos registrados en 701. El documento puede conservar '
                     'claves AF, IN, RT u otras; no se filtra exclusivamente por ClaveDocumento = R1.',
                     'R1: distinct declarations recorded in 701. Document codes may remain AF, IN, RT '
                     'or others; records are not restricted to DocumentCode = R1.')))
    story.append(p(t('Base global con los filtros aplicados: ', 'Global base under the applied filters: ') +
                   fmt(rect['globalDeclarations']) + t(' pedimentos de 501.', ' declarations from 501.')))
    def rect_row(label, row):
        return [label, fmt(row['r1']), fmt(row['declarations']), pct(row['officeRate']), pct(row['globalRate'])]
    table([t('Codigo y aduana', 'Code and customs office'), 'R1', t('Pedimentos', 'Declarations'),
           t('% aduana', '% office'), t('% global', '% global')],
          [rect_row(r['customs'] + ' - ' + CUSTOMS.get(r['customs'], t('Sin descripcion validada', 'Description not verified')), r)
           for r in rect['rows']] + [rect_row('Total', rect['totals'])], [207, 48, 90, 85, 85], total=True)
    story.append(p(t('% aduana = R1 de la aduana / pedimentos de esa aduana x 100. '
                     '% global = R1 de la aduana / total de pedimentos filtrados x 100. '
                     'El total porcentual se recalcula; no se promedian porcentajes.',
                     '% office = office R1 / office declarations x 100. '
                     '% global = office R1 / total filtered declarations x 100. '
                     'Total percentages are recalculated, not averaged.')))
    story.append(p(t('Es una frecuencia de rectificacion, no una prueba de error o responsabilidad. '
                     'No se infieren costos ni responsables logisticos.',
                     'This is amendment frequency, not proof of error or responsibility. '
                     'Costs and logistics owners are not inferred.')))

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
         'carece de 551/557 o 501/701, su respectivo total de contribuciones o rectificaciones queda N/D.',
         'N/A is not zero. Totals cover available months. If an available month lacks 551/557 or '
         '501/701, the respective tax or amendment total is N/A.'),
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
