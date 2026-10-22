"""Editable OOXML reports from a bundled blank theme. No Node on the server.

The blank package was authored with Artifact Tool; runtime fills native text,
tables and charts. No uploaded presentation is executed or used as a template.
"""
from io import BytesIO
import json
from copy import deepcopy
from pathlib import Path
import textwrap
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile

import xlsxwriter

from .data_queries import fail
from .file_visuals import COLORS, chart_data, display

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
EMU = 9525  # CSS px; template is 1280 x 720.

for prefix, namespace in (("p", P), ("a", A), ("r", R), ("c", C)):
    ET.register_namespace(prefix, namespace)


def package_xml(root, namespace):
    # OPC requires unprefixed Types/Relationships with a default namespace.
    # Avoid changing ElementTree's global default binding across requests.
    root = deepcopy(root)
    for node in root.iter():
        if node.tag.startswith("{" + namespace + "}"):
            node.tag = node.tag.split("}", 1)[1]
    root.set("xmlns", namespace)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def paragraph(text, size=24, color="28414C", bold=False):
    return (f'<a:p><a:r><a:rPr lang="en-US" sz="{int(size * 75)}" b="{int(bold)}">'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Arial"/></a:rPr>'
            f'<a:t xml:space="preserve">{escape(str(text))}</a:t></a:r><a:endParaRPr lang="en-US"/></a:p>')


def textbox(identifier, text, x, y, width, height, size=24, color="28414C", bold=False):
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{identifier}" name="Text {identifier}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{int(x * EMU)}" y="{int(y * EMU)}"/><a:ext cx="{int(width * EMU)}" cy="{int(height * EMU)}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>'
            + "".join(paragraph(line, size, color, bold) for line in str(text).split("\n")) + '</p:txBody></p:sp>')


def slide_xml(content):
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}">'
            '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            + content + '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>').encode()


def table(headers, rows):
    widths = [1136 / len(headers)] * len(headers)
    heights = [max(54, 25 * max(len(textwrap.wrap(str(value), max(8, int(widths[i] / 11)))) for i, value in enumerate(headers)) + 18)]
    for row in rows:
        heights.append(max(44, 24 * max(len(textwrap.wrap(display(value), max(8, int(widths[i] / 10)))) or 1 for i, value in enumerate(row)) + 14))
    cells = []
    for index, row in enumerate([headers, *rows]):
        contents = []
        for value in row:
            fill = '145C56' if index == 0 else 'FFFFFF' if index % 2 == 1 else 'F0F5F6'
            color = 'FFFFFF' if index == 0 else '28414C'
            contents.append('<a:tc><a:txBody><a:bodyPr wrap="square"/><a:lstStyle/>' +
                paragraph(display(value), 21, color, index == 0) + f'</a:txBody><a:tcPr marL="90000" marR="90000" marT="40000" marB="40000" anchor="ctr"><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill></a:tcPr></a:tc>')
        cells.append(f'<a:tr h="{int(heights[index] * EMU)}">' + ''.join(contents) + '</a:tr>')
    height = sum(heights)
    return ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="4" name="Data table"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
            f'<p:xfrm><a:off x="{72 * EMU}" y="{172 * EMU}"/><a:ext cx="{1136 * EMU}" cy="{int(height * EMU)}"/></p:xfrm>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table"><a:tbl><a:tblPr firstRow="1" bandRow="1"/>'
            '<a:tblGrid>' + ''.join(f'<a:gridCol w="{int(width * EMU)}"/>' for width in widths) + '</a:tblGrid>' + ''.join(cells) + '</a:tbl></a:graphicData></a:graphic></p:graphicFrame>'), height


def native_chart(result, kind):
    values = chart_data(result)
    if len(values) > 12:
        fail("agent_presentation_chart", "La gráfica de PowerPoint admite hasta 12 categorías legibles; reduce la selección o crea una imagen independiente.")
    series = []
    for index, header in enumerate(result.headers[1:]):
        category = ''.join(f'<c:pt idx="{i}"><c:v>{escape(row[0])}</c:v></c:pt>' for i, row in enumerate(values))
        numbers = ''.join(f'<c:pt idx="{i}"><c:v>{row[index + 1]}</c:v></c:pt>' for i, row in enumerate(values))
        color = COLORS[index].lstrip("#")
        series.append(f'<c:ser><c:idx val="{index}"/><c:order val="{index}"/><c:tx><c:v>{escape(header)}</c:v></c:tx>'
            f'<c:spPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:ln w="28575"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln></c:spPr>'
            f'<c:cat><c:strRef><c:f>Data!$A$2:$A${len(values) + 1}</c:f><c:strCache><c:ptCount val="{len(values)}"/>{category}</c:strCache></c:strRef></c:cat>'
            f'<c:val><c:numRef><c:f>Data!${chr(66 + index)}$2:${chr(66 + index)}${len(values) + 1}</c:f><c:numCache><c:formatCode>#,##0.00</c:formatCode><c:ptCount val="{len(values)}"/>{numbers}</c:numCache></c:numRef></c:val></c:ser>')
    tag = "lineChart" if kind == "line" else "barChart"
    settings = '<c:grouping val="standard"/>' if kind == "line" else '<c:barDir val="col"/><c:grouping val="clustered"/>'
    numeric_values = [abs(value) for row in values for value in row[1:] if value]
    number_format = "0.000E+00" if numeric_values and (min(numeric_values) < .01 or max(numeric_values) >= 1e9) else "#,##0.00"
    unit = result.units[1] if result.units else ""
    axis_text = '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="1600"><a:latin typeface="Arial"/></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>'
    axis_title = (f'<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/>{paragraph(unit, 22)}</c:rich></c:tx><c:overlay val="0"/></c:title>'
                  if unit in {"USD", "MXN", "%", "MXN/USD"} else "")
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><c:chartSpace xmlns:c="{C}" xmlns:a="{A}" xmlns:r="{R}">'
           '<c:lang val="en-US"/><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/>'
           f'<c:{tag}>{settings}{"".join(series)}<c:axId val="1"/><c:axId val="2"/></c:{tag}>'
           f'<c:catAx><c:axId val="1"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/><c:tickLblPos val="nextTo"/>{axis_text}<c:crossAx val="2"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/></c:catAx>'
           f'<c:valAx><c:axId val="2"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="l"/><c:majorGridlines/>{axis_title}<c:numFmt formatCode="{number_format}" sourceLinked="0"/><c:tickLblPos val="nextTo"/>{axis_text}<c:crossAx val="1"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>'
           f'</c:plotArea><c:legend><c:legendPos val="b"/><c:layout/>{axis_text}</c:legend><c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>'
           '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="1600"><a:latin typeface="Arial"/></a:defRPr></a:pPr><a:endParaRPr lang="en-US"/></a:p></c:txPr>'
           '<c:externalData r:id="rIdWorkbook"><c:autoUpdate val="0"/></c:externalData></c:chartSpace>')
    buffer = BytesIO()
    with xlsxwriter.Workbook(buffer, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}) as book:
        page = book.add_worksheet("Data")
        for row_index, row in enumerate([result.headers, *values]):
            for col, value in enumerate(row):
                page.write_number(row_index, col, value) if isinstance(value, (int, float)) else page.write_string(row_index, col, value)
    return xml.encode(), buffer.getvalue()


def render_presentation(title, sections, manifest, language):
    source_title = "Sources" if language == "en" else "Fuentes"
    template = Path(__file__).resolve().parents[2] / "resources/reports/blank.pptx"
    with zipfile.ZipFile(template) as archive:
        parts = {name: archive.read(name) for name in archive.namelist() if not name.startswith(("ppt/slides/", "ppt/notesSlides/"))}
        layout = ET.fromstring(archive.read("ppt/slides/_rels/slide1.xml.rels"))
        layout_target = next(node.attrib["Target"] for node in layout if node.attrib["Type"].endswith("/slideLayout"))
    slides, chart_count = [], 0
    cover = textbox(2, "DataStage", 72, 80, 1136, 40, 24, "147D84", True)
    cover += textbox(3, title, 72, 205, 1136, 240, 56, "143E44", True)
    slides.append((cover, [], []))
    for section, result, caption in sections:
        heading = textbox(2, section["title"], 72, 40, 1136, 108, 40, "143E44", True)
        footer = textbox(3, caption, 72, 650, 1136, 45, 14)
        if section["commentary"]:
            commentary = textwrap.fill(section["commentary"], 80)
            slides.append((heading + textbox(4, commentary, 72, 180, 1136, 440, 26) + footer, [], result.sources))
        if section["chart"] != "none":
            chart_count += 1
            chart, workbook = native_chart(result, section["chart"])
            parts[f"ppt/charts/chart{chart_count}.xml"] = chart
            parts[f"ppt/embeddings/data{chart_count}.xlsx"] = workbook
            parts[f"ppt/charts/_rels/chart{chart_count}.xml.rels"] = (
                f'<Relationships xmlns="{REL}"><Relationship Id="rIdWorkbook" Type="{R}/package" Target="../embeddings/data{chart_count}.xlsx"/></Relationships>').encode()
            frame = ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="4" name="Editable data chart"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
                     f'<p:xfrm><a:off x="{72 * EMU}" y="{165 * EMU}"/><a:ext cx="{1136 * EMU}" cy="{460 * EMU}"/></p:xfrm>'
                     f'<a:graphic><a:graphicData uri="{C}"><c:chart xmlns:c="{C}" r:id="rIdChart"/></a:graphicData></a:graphic></p:graphicFrame>')
            slides.append((heading + frame + footer, [("rIdChart", R + "/chart", f"../charts/chart{chart_count}.xml")], result.sources))
        pending = []
        for row in result.rows:
            _, height = table(result.headers, [*pending, row])
            if height > 450:
                if not pending:
                    fail("agent_presentation_cell", "Una fila no cabe en PowerPoint. Reduce columnas o longitud del texto.")
                markup, _ = table(result.headers, pending)
                slides.append((heading + markup + footer, [], result.sources))
                pending = []
            pending.append(row)
        if pending or not result.rows:
            markup, height = table(result.headers, pending)
            if height > 450:
                fail("agent_presentation_cell", "Una fila no cabe en PowerPoint.")
            slides.append((heading + markup + footer, [], result.sources))
    source_lines = []
    for source in manifest["sources"]:
        if "attachmentId" in source:
            source_lines.append(f'{source["name"]}\n{source["sheet"]}\nSHA-256: {source["sha256"]}')
        else:
            source_lines.append(f'{source["period"]}. {"Version" if language == "en" else "Versión"} {source["version"]}\n'
                                f'{"Tables" if language == "en" else "Tablas"}: {", ".join(source.get("tables", []))}\nID: {source["runId"]}')
    for start in range(0, len(source_lines), 2):
        source_body = textbox(2, source_title, 72, 40, 1136, 100, 40, "143E44", True)
        source_body += textbox(3, "\n\n".join("\n".join(textwrap.fill(part, 90) for part in line.split("\n")) for line in source_lines[start:start + 2]), 72, 175, 1136, 450, 24)
        slides.append((source_body, [], manifest["sources"]))
    if len(slides) > 40:
        fail("agent_presentation_large", "La presentación supera 40 diapositivas. Resume o agrupa los datos; el detalle completo puede ir en Excel.")
    presentation = ET.fromstring(parts["ppt/presentation.xml"])
    old_ids = presentation.find("{" + P + "}sldIdLst")
    position = list(presentation).index(old_ids) if old_ids is not None else 0
    if old_ids is not None:
        presentation.remove(old_ids)
    identifiers = ET.Element("{" + P + "}sldIdLst")
    presentation.insert(position, identifiers)
    relationships = ET.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    for node in list(relationships):
        if node.attrib["Type"].endswith("/slide"):
            relationships.remove(node)
    types = ET.fromstring(parts["[Content_Types].xml"])
    for node in list(types):
        if node.attrib.get("PartName", "").startswith(("/ppt/slides/", "/ppt/notesSlides/")):
            types.remove(node)
    for number, (body, extra, sources) in enumerate(slides, 1):
        rid = f"rIdDataStageSlide{number}"
        ET.SubElement(identifiers, "{" + P + "}sldId", {"id": str(255 + number), "{" + R + "}id": rid})
        ET.SubElement(relationships, "{" + REL + "}Relationship", {"Id": rid, "Type": R + "/slide", "Target": f"slides/slide{number}.xml"})
        parts[f"ppt/slides/slide{number}.xml"] = slide_xml(body)
        rels = ET.Element("{" + REL + "}Relationships")
        for rel_id, rel_type, target in [("rIdLayout", R + "/slideLayout", layout_target), *extra]:
            ET.SubElement(rels, "{" + REL + "}Relationship", {"Id": rel_id, "Type": rel_type, "Target": target})
        parts[f"ppt/slides/_rels/slide{number}.xml.rels"] = package_xml(rels, REL)
        ET.SubElement(types, "{" + CT + "}Override", {"PartName": f"/ppt/slides/slide{number}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"})
    for number in range(1, chart_count + 1):
        ET.SubElement(types, "{" + CT + "}Override", {"PartName": f"/ppt/charts/chart{number}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"})
    if chart_count and not any(node.attrib.get("Extension") == "xlsx" for node in types):
        ET.SubElement(types, "{" + CT + "}Default", {"Extension": "xlsx", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    # A standard custom XML part preserves complete queries/versions without
    # crowding readable slides with internal identifiers.
    parts["customXml/item1.xml"] = ('<sources xmlns="urn:datastage:sources">' + escape(json.dumps(manifest, ensure_ascii=False)) + '</sources>').encode()
    ET.SubElement(types, "{" + CT + "}Override", {"PartName": "/customXml/item1.xml", "ContentType": "application/xml"})
    root_rels = ET.fromstring(parts["_rels/.rels"])
    ET.SubElement(root_rels, "{" + REL + "}Relationship", {"Id": "rIdSources", "Type": R + "/customXml", "Target": "customXml/item1.xml"})
    parts["_rels/.rels"] = package_xml(root_rels, REL)
    parts["[Content_Types].xml"] = package_xml(types, CT)
    parts["ppt/presentation.xml"] = ET.tostring(presentation, encoding="utf-8", xml_declaration=True)
    parts["ppt/_rels/presentation.xml.rels"] = package_xml(relationships, REL)
    if "docProps/core.xml" in parts:
        core = ET.fromstring(parts["docProps/core.xml"])
        for name, value in (("{http://purl.org/dc/elements/1.1/}title", title),
                            ("{http://purl.org/dc/elements/1.1/}creator", "DataStage"),
                            ("{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastModifiedBy", "DataStage")):
            node = core.find(name)
            if node is None:
                node = ET.SubElement(core, name)
            node.text = value
        parts["docProps/core.xml"] = ET.tostring(core, encoding="utf-8", xml_declaration=True)
    if "docProps/app.xml" in parts:
        properties = ET.fromstring(parts["docProps/app.xml"])
        for node in properties:
            if node.tag.endswith("}Slides"):
                node.text = str(len(slides))
        parts["docProps/app.xml"] = ET.tostring(properties, encoding="utf-8", xml_declaration=True)
    result = BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return result.getvalue()
