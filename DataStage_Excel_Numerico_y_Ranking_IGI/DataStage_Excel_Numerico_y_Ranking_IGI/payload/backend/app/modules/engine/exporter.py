"""Excel output adapter; Excel never participates in the transformation."""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import xlsxwriter

from .catalog import normalize_header
from .dates import is_date_header, parse_date

MONTHLY_CONTROL_HEADERS = ("Archivo", "Tabla", "Hoja", "Estatus", "Filas", "Columnas", "ColumnasFecha", "Mensaje")
ANNUAL_CONTROL_HEADERS = ("Periodo",) + MONTHLY_CONTROL_HEADERS
EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_COLUMNS = 16_384
EXCEL_MAX_TEXT = 32_767
MONEY_HEADERS = frozenset(normalize_header(header) for header in (
    "TotalFletes", "TotalSeguros", "TotalEmbalajes", "TotalIncrementables", "TotalDeducibles",
    "ValorDolares", "ValorMonedaExtranjera", "ValorUnitarioTitulo", "TotalGarantia",
    "PrecioUnitario", "ValorAduana", "ValorComercial", "ValorAgregado", "ValorComercialDolares",
    "ImportePago", "TotalContribuciones",
))
MEASURE_HEADERS = frozenset(normalize_header(header) for header in (
    "TipoCambio", "PesoBrutoMercancia", "CantidadUnidades", "TitulosAsignados", "TasaContribucion",
    "MercanciaDescargada", "CantidadUMComercial", "CantidadUMTarifa", "KilometrajeVehiculo",
    "CantidadMUMTarifa", "CantidadUnidadesMedida",
))
COUNT_HEADERS = frozenset(normalize_header(header) for header in ("TotalFracciones",))
CONTROL_COUNTS = frozenset(normalize_header(header) for header in ("Filas", "Columnas", "ColumnasFecha"))


def _empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _validate_sheet(headers: list[str], rows: list[list]) -> None:
    if len(headers) > EXCEL_MAX_COLUMNS or sum(any(not _empty(v) for v in row) for row in rows) + 1 > EXCEL_MAX_ROWS:
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
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        parsed, _ = parse_date(value)
    else:
        return None
    return parsed if parsed and parsed.tzinfo is None and 1900 <= parsed.year <= 2100 else None


def _number_cell(value: object) -> float | None:
    """Convert schema-defined measures only; never guess identifier types."""
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        return None
    try:
        parsed = Decimal(text)
        # Excel cannot faithfully store more than 15 significant decimal digits.
        significant = ''.join(str(digit) for digit in parsed.as_tuple().digits).rstrip('0')
        if len(significant) > 15:
            return None
        result = float(parsed)
        return result if math.isfinite(result) and (result != 0 or parsed == 0) else None
    except (InvalidOperation, OverflowError, ValueError):
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
            date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
            datetime_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
            money_format = workbook.add_format({"num_format": "#,##0.00"})
            measure_format = workbook.add_format({"num_format": "#,##0.##########"})
            count_format = workbook.add_format({"num_format": "#,##0"})
            for sheet in sheets:
                worksheet = workbook.add_worksheet(sheet["sheetName"])
                headers, rows = sheet["headers"], sheet["rows"]
                keys = [normalize_header(header) for header in headers]
                date_keys = {normalize_header(header) for header in sheet["dateColumns"]}
                date_keys.update(key for key in keys if is_date_header(key))
                count_keys = COUNT_HEADERS | (CONTROL_COUNTS if sheet["sheetName"] == "Control_Proceso" else set())
                numeric_keys = MONEY_HEADERS | MEASURE_HEADERS | count_keys
                column_formats = [date_format if key in date_keys else
                                  money_format if key in MONEY_HEADERS else
                                  count_format if key in count_keys else
                                  measure_format if key in MEASURE_HEADERS else text_format for key in keys]
                widths = [max(len(line) for line in header.split("\n")) for header in headers]
                worksheet.freeze_panes(1, 0)
                for column, header in enumerate(headers):
                    worksheet.write_string(0, column, header, header_format)
                row_index = 0
                for row in rows:
                    if all(_empty(value) for value in row):
                        continue
                    row_index += 1
                    for column, value in enumerate(row):
                        if _empty(value):
                            continue
                        key = keys[column]
                        parsed = _datetime_cell(value) if key in date_keys else None
                        numeric = _number_cell(value) if key in numeric_keys else None
                        if parsed:
                            has_time = parsed.time() != datetime.min.time()
                            worksheet.write_datetime(row_index, column, parsed, datetime_format if has_time else date_format)
                            visible = parsed.strftime("%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d")
                        elif numeric is not None:
                            worksheet.write_number(row_index, column, numeric, column_formats[column])
                            visible = str(value)
                        else:
                            visible = str(value) if value is not None else ""
                            worksheet.write_string(row_index, column, visible, text_format)
                        widths[column] = max(widths[column], *(len(line) for line in visible.split("\n")))
                for column, width in enumerate(widths):
                    worksheet.set_column(column, column, min(255, max(12, width + 4)), column_formats[column])
                worksheet.autofilter(0, 0, row_index, len(headers) - 1)
                header_lines = max(len(header.split("\n")) for header in headers)
                worksheet.set_row(0, max(32, header_lines * 16 + 12))
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

