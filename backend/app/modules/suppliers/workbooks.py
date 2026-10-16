"""Retain the selected Excel layout; only append supplier rows and their yellow fill."""
from base64 import b64decode, b64encode
from copy import copy
from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from xml.etree import ElementTree


def _color(book, index):
    rgb = book.colour_map.get(index)
    return "FF" + "".join(f"{value:02X}" for value in rgb) if rgb else None


def from_xls(book):
    """Convert the legacy templates to XLSX, including their existing cell styles."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
    from openpyxl.utils import get_column_letter

    output = Workbook()
    output.remove(output.active)
    styles = {}
    borders = [None, "thin", "medium", "dashed", "dotted", "thick", "double", "hair",
               "mediumDashed", "dashDot", "mediumDashDot", "dashDotDot", "mediumDashDotDot", "slantDashDot"]
    patterns = [None, "solid", "mediumGray", "darkGray", "lightGray", "darkHorizontal", "darkVertical",
                "darkDown", "darkUp", "darkGrid", "darkTrellis", "lightHorizontal", "lightVertical",
                "lightDown", "lightUp", "lightGrid", "lightTrellis", "gray125", "gray0625"]
    for source in book.sheets():
        sheet = output.create_sheet(source.name)
        sheet.sheet_state = ["visible", "hidden", "veryHidden"][source.visibility]
        sheet.sheet_format.defaultRowHeight = source.default_row_height / 20
        sheet.sheet_view.showGridLines = bool(source.show_grid_lines)
        for column, info in source.colinfo_map.items():
            if column >= max(source.ncols, 1):
                continue
            dimension = sheet.column_dimensions[get_column_letter(column + 1)]
            dimension.width, dimension.hidden = info.width / 256, bool(info.hidden)
        for row, info in source.rowinfo_map.items():
            sheet.row_dimensions[row + 1].height = info.height / 20
            sheet.row_dimensions[row + 1].hidden = bool(info.hidden)
        for row in range(source.nrows):
            for column in range(source.ncols):
                original = source.cell(row, column)
                cell = sheet.cell(row + 1, column + 1)
                cell.value = original.value if original.ctype not in (0, 6) else None
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                index = source.cell_xf_index(row, column)
                if index not in styles:
                    xf = book.xf_list[index]
                    font, align, fill = book.font_list[xf.font_index], xf.alignment, xf.background
                    sides = {}
                    for edge in ("left", "right", "top", "bottom"):
                        style = borders[getattr(xf.border, edge + "_line_style")]
                        sides[edge] = Side(style=style, color=_color(book, getattr(xf.border, edge + "_colour_index")))
                    foreground = _color(book, fill.pattern_colour_index)
                    cell.font = Font(name=font.name, size=font.height / 20, bold=bool(font.bold),
                        italic=bool(font.italic), strike=bool(font.struck_out), color=_color(book, font.colour_index),
                        underline={1: "single", 2: "double", 0x21: "singleAccounting", 0x22: "doubleAccounting"}.get(font.underline_type))
                    cell.fill = PatternFill(patternType=patterns[fill.fill_pattern],
                        fgColor=foreground or "00000000", bgColor=_color(book, fill.background_colour_index) or "00000000")
                    cell.border = Border(**sides)
                    cell.alignment = Alignment(horizontal={1: "left", 2: "center", 3: "right", 4: "fill", 5: "justify", 6: "centerContinuous", 7: "distributed"}.get(align.hor_align),
                        vertical={0: "top", 1: "center", 2: "bottom", 3: "justify", 4: "distributed"}.get(align.vert_align),
                        wrap_text=bool(align.text_wrapped), shrink_to_fit=bool(align.shrink_to_fit),
                        indent=align.indent_level, text_rotation=align.rotation if align.rotation <= 180 else 0)
                    cell.number_format = book.format_map[xf.format_key].format_str
                    cell.protection = Protection(locked=bool(xf.protection.cell_locked), hidden=bool(xf.protection.formula_hidden))
                    styles[index] = copy(cell._style)
                else:
                    cell._style = copy(styles[index])
        for first_row, last_row, first_col, last_col in source.merged_cells:
            sheet.merge_cells(start_row=first_row + 1, end_row=last_row, start_column=first_col + 1, end_column=last_col)
    for name in book.name_map.get("_filterdatabase", []):
        if name.scope >= 0:
            sheet = output.worksheets[name.scope]
            sheet.auto_filter.ref = sheet.dimensions
    return output


def encode_template(book):
    output = BytesIO()
    book.save(output)
    return b64encode(output.getvalue()).decode("ascii")


def render(snapshot, kind, title):
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    template = snapshot["schemas"].get("_templates", {}).get(kind)
    book = load_workbook(BytesIO(b64decode(template)), keep_links=False) if template else Workbook()
    sheet = book.worksheets[0]
    headers = snapshot["schemas"][kind]
    if not template:
        sheet.title = "Sheet1"
        for column, header in enumerate(headers, 1):
            sheet.cell(1, column, header).font = Font(name="Calibri", size=11, bold=True)
            sheet.column_dimensions[get_column_letter(column)].width = (22 if kind == "national" else 30)
    # Capture styles before moving original rows to their final cumulative order.
    original_rows = {
        row: ([copy(sheet.cell(row, column)._style) for column in range(1, len(headers) + 1)],
              sheet.row_dimensions[row].height)
        for row in range(2, sheet.max_row + 1)
    }
    default_styles, default_height = original_rows.get(2, ([None] * len(headers), None))
    neutral_fills = []
    for column in range(1, len(headers) + 1):
        neutral = PatternFill()
        for row in range(2, sheet.max_row + 1):
            fill = sheet.cell(row, column).fill
            if not (fill.patternType == "solid" and fill.fgColor.type == "rgb" and fill.fgColor.rgb.endswith("FFFF00")):
                neutral = copy(fill)
                break
        neutral_fills.append(neutral)
    for row in sheet.iter_rows(min_row=2, max_row=max(sheet.max_row, len(snapshot[kind]) + 1), max_col=len(headers)):
        for cell in row:
            cell.value, cell.hyperlink, cell.comment = None, None, None
    for row_number, record in enumerate(snapshot[kind], 2):
        styles, height = original_rows.get(record.get("templateRow"), (default_styles, default_height))
        sheet.row_dimensions[row_number].height = height
        for column, value in enumerate(record["values"], 1):
            cell = sheet.cell(row_number, column)
            cell._style = copy(styles[column - 1])
            cell.value = value if value != "" else None
            if isinstance(value, str):
                cell.data_type = "s"  # Supplier text must never become a formula.
            if record["highlight"]:
                cell.fill = PatternFill("solid", fgColor="FFFFFF00")
            elif cell.fill.patternType == "solid" and cell.fill.fgColor.type == "rgb" and cell.fill.fgColor.rgb.endswith("FFFF00"):
                cell.fill = copy(neutral_fills[column - 1])
    last_row = max(1, len(snapshot[kind]) + 1)
    if sheet.max_row > last_row:
        sheet.delete_rows(last_row + 1, sheet.max_row - last_row)
    extent = f"A1:{get_column_letter(len(headers))}{last_row}"
    if sheet.auto_filter.ref:
        sheet.auto_filter.ref = extent
    for table in sheet.tables.values():
        table.ref = extent
        if table.autoFilter:
            table.autoFilter.ref = extent
    book.properties.title = title
    book.properties.created = book.properties.modified = datetime(2026, 1, 1)
    output = BytesIO()
    book.save(output)
    # Frozen reports must also be byte-stable across downloads at different times.
    stable = BytesIO()
    with ZipFile(output) as source, ZipFile(stable, "w", ZIP_DEFLATED) as target:
        for entry in source.infolist():
            info = ZipInfo(entry.filename, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            content = source.read(entry)
            if entry.filename == "docProps/core.xml":
                properties = ElementTree.fromstring(content)
                for name in ("created", "modified"):
                    stamp = properties.find("{http://purl.org/dc/terms/}" + name)
                    if stamp is not None:
                        stamp.text = "2026-01-01T00:00:00Z"
                content = ElementTree.tostring(properties, encoding="utf-8", xml_declaration=True)
            target.writestr(info, content)
    return stable.getvalue()
