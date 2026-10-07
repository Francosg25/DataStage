from datetime import datetime
from zipfile import ZipFile

import openpyxl
import pytest

from app.modules.engine import InputFile, export_xlsx, process_annual, process_monthly


def test_excel_preserves_text_dates_readable_headers_and_filtered_ranges(tmp_path):
    result = process_monthly("Abril_2026", [InputFile("x_501.asc", "Clave|FechaPagoReal|Nota\n00001|20260423121314|=SUM(A1:A2)\n00002|invalid|https://example.com", "Abril_2026")])
    path = tmp_path / "DataStage_Abril_2026.xlsx"
    export_xlsx(result, path)
    workbook = openpyxl.load_workbook(path)
    assert workbook.sheetnames == ["Control_Proceso", "501 Datos generales"]
    worksheet = workbook.worksheets[1]
    assert worksheet.freeze_panes == "A2"
    assert worksheet["D2"].value == "00001"
    assert worksheet["D2"].number_format == "@"
    assert worksheet["E2"].value == datetime(2026, 4, 23, 12, 13, 14)
    assert worksheet["E2"].number_format == "yyyy-mm-dd hh:mm:ss"
    assert worksheet["E3"].value == "invalid"
    assert worksheet["F2"].value == "=SUM(A1:A2)"
    assert worksheet["F2"].data_type == "s"
    assert worksheet["F3"].hyperlink is None
    assert worksheet["A1"].fill.fgColor.rgb == "FF145C56"
    assert worksheet["A1"].font.color.rgb == "FFFFFFFF"
    assert worksheet["A1"].font.bold
    assert worksheet["A1"].alignment.horizontal == "left"
    assert worksheet["A1"].alignment.wrap_text
    assert worksheet.row_dimensions[1].height == 32
    assert worksheet.auto_filter.ref == "A1:F3"
    assert all(not sheet.tables for sheet in workbook)
    with ZipFile(path) as archive:
        assert "<f>" not in archive.read("xl/worksheets/sheet2.xml").decode()
        assert not any(name.startswith("xl/tables/") for name in archive.namelist())


def test_header_only_sheet_has_autofilter(tmp_path):
    result = process_monthly("Abril_2026", [InputFile("x_501.asc", "Clave|Valor", "Abril_2026")])
    path = tmp_path / "empty.xlsx"
    export_xlsx(result, path)
    worksheet = openpyxl.load_workbook(path).worksheets[1]
    assert not worksheet.tables
    assert worksheet.auto_filter.ref == "A1:E1"
    assert worksheet.max_row == 1


def test_multiline_headers_have_readable_height_and_filter_space(tmp_path):
    result = {"kind": "monthly", "controlRows": [], "tables": [{
        "sheetName": "Encabezados", "headers": ["DescripcionMercancia", "Importe\noriginal"],
        "dateColumns": [], "rows": [["Articulo", "0001"]],
    }]}
    path = tmp_path / "headers.xlsx"
    export_xlsx(result, path)
    worksheet = openpyxl.load_workbook(path)["Encabezados"]
    assert worksheet.row_dimensions[1].height == 44
    assert worksheet.column_dimensions["A"].width >= len("DescripcionMercancia") + 4
    assert worksheet["B1"].value == "Importe\noriginal"
    assert worksheet["B1"].alignment.wrap_text
    assert worksheet["B2"].value == "0001"
    assert worksheet.auto_filter.ref == "A1:B2"
    assert not worksheet.tables


def test_annual_control_column_order_and_export(tmp_path):
    result = process_annual(2026, "Ene-Ago", [InputFile("x_501.asc", "A\n001", "Jan_2026")])
    path = tmp_path / "annual.xlsx"
    export_xlsx(result, path)
    workbook = openpyxl.load_workbook(path)
    worksheet = workbook.worksheets[0]
    assert [cell.value for cell in worksheet[1]] == ["Periodo", "Archivo", "Tabla", "Hoja", "Estatus", "Filas", "Columnas", "ColumnasFecha", "Mensaje"]
    for sheet in workbook:
        assert not sheet.tables
        assert sheet.auto_filter.ref == sheet.dimensions
        assert sheet.freeze_panes == "A2"
        assert all(cell.font.color.rgb == "FFFFFFFF" for cell in sheet[1])
        assert all(cell.fill.fgColor.rgb == "FF145C56" for cell in sheet[1])
    with ZipFile(path) as archive:
        assert not any(name.startswith("xl/tables/") for name in archive.namelist())


def test_export_limits_fail_before_replacing_existing_file(tmp_path):
    path = tmp_path / "output.xlsx"
    path.write_bytes(b"existing output")
    result = process_monthly("Abril_2026", [InputFile("x_501.asc", "A\n" + "x" * 32768, "Abril_2026")])
    with pytest.raises(ValueError, match="32767"):
        export_xlsx(result, path)
    assert path.read_bytes() == b"existing output"


def test_empty_result_still_exports_control(tmp_path):
    result = process_monthly("Abril_2026", [])
    path = tmp_path / "output.xlsx"
    export_xlsx(result, path)
    assert openpyxl.load_workbook(path).sheetnames == ["Control_Proceso"]


def test_out_of_range_iso_date_remains_original_text_in_excel(tmp_path):
    result = process_monthly("Abril_2026", [InputFile("x_501.asc", "FechaPagoReal\n2200-01-01T00:00:00", "Abril_2026")])
    path = tmp_path / "invalid-date.xlsx"
    export_xlsx(result, path)
    cell = openpyxl.load_workbook(path).worksheets[1]["D2"]
    assert cell.value == "2200-01-01T00:00:00"
    assert cell.data_type == "s"
