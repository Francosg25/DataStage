"""Excel output adapter; Excel never participates in the transformation."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import xlsxwriter

from .catalog import normalize_header

MONTHLY_CONTROL_HEADERS = ("Archivo", "Tabla", "Hoja", "Estatus", "Filas", "Columnas", "ColumnasFecha", "Mensaje")
ANNUAL_CONTROL_HEADERS = ("Periodo",) + MONTHLY_CONTROL_HEADERS
EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_COLUMNS = 16_384
EXCEL_MAX_TEXT = 32_767


def _validate_sheet(headers: list[str], rows: list[list]) -> None:
    if len(headers) > EXCEL_MAX_COLUMNS or len(rows) + 1 > EXCEL_MAX_ROWS:
        raise ValueError("El resultado excede los límites de filas o columnas de Excel; no se ha truncado.")
    if not headers:
        raise ValueError("No se puede exportar una hoja sin encabezados.")
    for values in [headers]:
        if any(len(str(value)) > EXCEL_MAX_TEXT for value in values):
            raise ValueError("Un encabezado excede los 32767 caracteres de Excel.")
    for row in rows:
        if len(row) != len(headers):
            raise ValueError("Una fila no coincide con el esquema final.")
        if any(len(str(value)) > EXCEL_MAX_TEXT for value in row):
            raise ValueError("Un valor excede los 32767 caracteres de Excel; no se ha truncado.")


def _datetime_cell(value: object) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if 1900 <= parsed.year <= 2100 else None
    except ValueError:
        return None


def export_xlsx(result: dict, path: Path) -> None:
    """Validate first; write an atomic .xlsx with filtered ranges, not tables."""
    path = Path(path)
    control_headers = list(ANNUAL_CONTROL_HEADERS if result["kind"] == "annual" else MONTHLY_CONTROL_HEADERS)
    sheets = [{"sheetName": "Control_Proceso", "headers": control_headers, "dateColumns": [],
               "rows": [[row.get(header, "") for header in control_headers] for row in result["controlRows"]]}] + result["tables"]
    for sheet in sheets:
        _validate_sheet(sheet["headers"], sheet["rows"])
    path.parent.mkdir(parents=True, exist_ok=True)
    import uuid
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with xlsxwriter.Workbook(str(temp_path), {"strings_to_formulas": False, "strings_to_urls": False}) as workbook:
            header_format = workbook.add_format({
                "bold": True, "font_color": "#FFFFFF", "bg_color": "#145C56",
                "font_size": 11, "align": "left", "valign": "vcenter", "text_wrap": True,
            })
            text_format = workbook.add_format({"num_format": "@"})
            date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
            for sheet in sheets:
                worksheet = workbook.add_worksheet(sheet["sheetName"])
                headers, rows = sheet["headers"], sheet["rows"]
                date_keys = set(sheet["dateColumns"])
                widths = [max(len(line) for line in header.split("\n")) for header in headers]
                worksheet.freeze_panes(1, 0)
                for column, header in enumerate(headers):
                    worksheet.write_string(0, column, header, header_format)
                for row_index, row in enumerate(rows, 1):
                    for column, value in enumerate(row):
                        parsed = _datetime_cell(value) if normalize_header(headers[column]) in date_keys else None
                        if parsed:
                            worksheet.write_datetime(row_index, column, parsed, date_format)
                            visible = parsed.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            visible = str(value) if value is not None else ""
                            worksheet.write_string(row_index, column, visible, text_format)
                        widths[column] = max(widths[column], *(len(line) for line in visible.split("\n")))
                for column, width in enumerate(widths):
                    worksheet.set_column(column, column, min(255, max(12, width + 4)), text_format)
                worksheet.autofilter(0, 0, len(rows), len(headers) - 1)
                header_lines = max(len(header.split("\n")) for header in headers)
                worksheet.set_row(0, max(32, header_lines * 16 + 12))
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
