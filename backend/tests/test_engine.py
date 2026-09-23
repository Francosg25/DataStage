from datetime import datetime
import json

import pytest

from app.modules.engine import (
    EngineOptions, InputFile, TABLE_ORDER, detect_table_code, normalize_header,
    parse_period, process_annual, process_monthly,
)
from app.modules.engine.catalog import folio_from_name, make_sheet_names
from app.modules.engine.dates import is_date_header, parse_date


def source(content, name="1896462_501.asc", period="Abril_2026", code=None, file_id="source-1"):
    return InputFile(name, content, period, code, file_id)


@pytest.mark.parametrize("name,explicit,expected", [
    ("x_501.asc", None, "501"), ("501_123_551.asc", None, "551"),
    ("501-551.asc", None, "551"), ("123456_501.asc", None, "501"),
    ("xyz501.asc", None, "xyz501"), ("x_501_resumen.asc", None, "resumen"),
    ("x_501_inci.asc", None, "inci"), ("x_Seleccion.asc", None, "sel"),
    ("x_Selección.asc", None, "sel"), ("x_sel_thing.asc", None, "sel"),
    ("x_select.asc", None, "select"), ("x_resumen.asc", "  XYZ  ", "xyz"),
    ("C:\\some_folder\\ABC-987.asc", None, "987"),
])
def test_code_detection_precedence_and_numeric_boundaries(name, explicit, expected):
    assert detect_table_code(name, explicit) == expected


@pytest.mark.parametrize("text,expected", [("Abril_2026", (2026, 4, "Abril_2026")), ("JAN_2026", (2026, 1, "Enero_2026")), ("Agosto 2026", (2026, 8, "Agosto_2026")), ("December-2026", (2026, 12, "Diciembre_2026"))])
def test_period_aliases(text, expected):
    assert parse_period(text) == expected


@pytest.mark.parametrize("text", ["Foo_2026", "Mes_2026", "Abril_26", "13_2026", "April_1899", "abril_2101", ""])
def test_invalid_period(text):
    with pytest.raises(ValueError):
        parse_period(text)


@pytest.mark.parametrize("value,expected", [
    ("2026-04-23", "2026-04-23T00:00:00"), ("2026/4/23 13:42", "2026-04-23T13:42:00"),
    ("20260423", "2026-04-23T00:00:00"), ("20260423134256", "2026-04-23T13:42:56"),
    ("20260423 13:42:56", "2026-04-23T13:42:56"), ("2026-04-23T13:42:56", "2026-04-23T13:42:56"),
    ("23/04/2026", "2026-04-23T00:00:00"), ("04/23/2026", "2026-04-23T00:00:00"),
    ("04/23/2026 12:00 AM", "2026-04-23T00:00:00"), ("23/04/2026 12:00 PM", "2026-04-23T12:00:00"),
    ("04/23/2026 1:02:03 pm", "2026-04-23T13:02:03"), ("20000229", "2000-02-29T00:00:00"),
    ("2100-12-31", "2100-12-31T00:00:00"), ("1900-01-01", "1900-01-01T00:00:00"),
])
def test_strict_dates_and_compact_formats(value, expected):
    parsed, _ = parse_date(value)
    assert parsed == datetime.fromisoformat(expected)


@pytest.mark.parametrize("value", ["19000229", "20260229", "2101-01-01", "1899-12-31", "20261301", "20260431", "20260423240000", "20260423126000", "20260423125960", "202604231234", "2026-04/23", "23/04/2026 13:00 PM", "23/04/2026 0:00 AM", "23/04/2026 23:01:60", "2026-04-23Z", "2026-04-23 junk", "1/2/26", "", "2026-00-01"])
def test_invalid_dates_are_not_silently_coerced(value):
    assert parse_date(value)[0] is None


def test_ambiguity_is_explicit_and_configurable():
    assert parse_date("04/05/2026", "DMY") == (datetime(2026, 5, 4), True)
    assert parse_date("04/05/2026", "MDY") == (datetime(2026, 4, 5), True)
    assert parse_date("05/05/2026")[1] is False


@pytest.mark.parametrize("name", ["TipoFecha", "ClaveTipoFecha", "Clave de tipo de fecha", "Tipo de fecha", "NumeroFecha", "SecuenciaFecha", "FechaTipoFecha", "FechaClaveTipoFechaAnterior"])
def test_date_exclusions_override_prefix(name):
    assert not is_date_header(name)


def test_normalization_and_parse_fills_truncates_preserves_text():
    assert normalize_header(" \ufeffClavé_de Sección! ") == "clavedeseccion"
    result = process_monthly("Abril_2026", [source("\ufeff Clave | Valor | Extra ||\r\n\r\n 001 | 0002 |x|ignored|\r 003 | 04 |\n")])
    table = result["tables"][0]
    assert table["headers"] == ["Periodo", "ArchivoOrigen", "FolioOrigen", "Clave", "Valor", "Extra"]
    assert table["rows"] == [["Abril_2026", "1896462_501.asc", "1896462", "001", "0002", "x"], ["Abril_2026", "1896462_501.asc", "1896462", "003", "04", ""]]
    assert [s["rowNumber"] for s in table["rowSources"]] == [3, 4]
    assert result["controlRows"][0]["Columnas"] == 3
    assert result["controlRows"][-1]["Columnas"] == 6
    assert json.loads(json.dumps(result)) == result


def test_unification_aligns_previous_rows_against_new_columns():
    files = [source("RFC|FechaPagoReal\nA|2026-04-23", "a_501.asc", file_id="1"), source("fecha pago réal|NUEVA|Rfc\n2026/04/24|007|B", "b_501.asc", file_id="2")]
    table = process_monthly("Abril_2026", files)["tables"][0]
    assert table["headers"] == ["Periodo", "ArchivoOrigen", "FolioOrigen", "RFC", "FechaPagoReal", "NUEVA"]
    assert table["rows"][0][3:] == ["A", "2026-04-23T00:00:00", ""]
    assert table["rows"][1][3:] == ["B", "2026-04-24T00:00:00", "007"]
    assert table["rowSources"][0]["originalDates"] == {"fechapagoreal": "2026-04-23"}


def test_pedimento_aliases_preferred_year_and_fallback():
    content = "Patente Aduanal|Número de Pedimento|Clave de sección aduanera de despacho|FechaOperacion|FechaPagoReal|TipoFecha\n3636|6000009|24-0|2024-01-01|2025-05-01|001\n0001|0000002|7|invalid||002"
    result = process_monthly("Abril_2026", [source(content)])
    table = result["tables"][0]
    assert table["headers"][3] == "PedimentoCompleto"
    assert table["rows"][0][3] == "25 24 3636 6000009"
    assert table["rows"][1][3] == "26 07 0001 0000002"
    assert table["rows"][0][-1] == "001"
    assert result["functionalResult"] == "OK"
    assert result["warnings"][0]["code"] == "INVALID_DATE"


def test_existing_complete_pedimento_is_not_duplicated():
    result = process_monthly("Abril_2026", [source("Patente|Pedimento|SeccionAduanera|Pedimento_Unificado\n1|2|3|original")])
    assert "PedimentoCompleto" not in result["tables"][0]["headers"]
    assert result["tables"][0]["rows"][0][-1] == "original"


def test_empty_header_only_and_invalid_headers_are_distinct():
    files = [source("", "empty_501.asc"), source("|||", "noheaders_501.asc"), source("A|B", "headersonly_501.asc"), source("A|á\n1|2", "collision_501.asc")]
    result = process_monthly("Abril_2026", files)
    assert [f["message"] for f in result["files"][:3]] == ["Archivo vacio.", "No se detectaron encabezados.", "Archivo solo con encabezado."]
    assert result["functionalResult"] == "WARNING"
    assert (result["receivedFiles"], result["processedFiles"], result["skippedFiles"], result["failedFiles"]) == (4, 1, 2, 1)
    assert result["tables"][0]["rows"] == []
    assert result["controlRows"][-1]["Mensaje"] == "1 archivos unificados."


def test_invalid_dates_warn_without_changing_functional_result():
    result = process_monthly("Abril_2026", [source("FechaX|FechaY\n2026-02-30|04/05/2026")])
    assert result["tables"][0]["rows"][0][-2:] == ["2026-02-30", "2026-05-04T00:00:00"]
    assert [w["code"] for w in result["warnings"]] == ["INVALID_DATE", "AMBIGUOUS_DATE"]
    assert result["functionalResult"] == "OK"


def test_monthly_period_comes_from_request_not_zip_or_file_period():
    result = process_monthly("Abril_2026", [source("X\n1", period="January_2025")])
    assert result["tables"][0]["rows"][0][0] == "Abril_2026"


def test_official_and_unknown_table_order_and_sheet_collisions():
    codes = ["z_unknown", "resumen", "501", "sel", "551", "a_unknown"]
    result = process_monthly("Abril_2026", [source("A\n1", code=code) for code in codes])
    assert [t["tableCode"] for t in result["tables"]] == ["501", "551", "sel", "resumen", "a_unknown", "z_unknown"]
    assert result["sheets"][0] == "Control_Proceso"
    names = make_sheet_names(["a/b", "ab", "[]:*?", "Control_Proceso", "x" * 50, "history"])
    assert len({n.lower() for n in names.values()} | {"control_proceso"}) == len(names) + 1
    assert all(len(name) <= 31 and not any(c in name for c in "[]:*?/\\") for name in names.values())
    assert len(TABLE_ORDER) == 26


def test_annual_filter_sort_and_variable_schema():
    files = [source("A|C\naug|3", "b_501.asc", "Aug_2026"), source("A\njanb", "b_501.asc", "Jan_2026"), source("B|A\n2|jana", "a_501.asc", "Ene_2026"), source("A\nwrong", period="Bad_2026"), source("A\nold", period="Enero_2025"), source("A\nlate", period="Dic_2026")]
    result = process_annual(2026, "Ene-Ago", files)
    assert (result["receivedFiles"], result["processedFiles"], result["skippedFiles"]) == (6, 3, 3)
    table = result["tables"][0]
    assert table["headers"] == ["Periodo", "ArchivoOrigen", "FolioOrigen", "B", "A", "C"]
    assert [r[3:] for r in table["rows"]] == [["2", "jana", ""], ["", "janb", ""], ["", "aug", "3"]]
    assert list(result["controlRows"][0]) == ["Periodo", "Archivo", "Tabla", "Hoja", "Estatus", "Filas", "Columnas", "ColumnasFecha", "Mensaje"]
    assert result["controlRows"][-1]["Mensaje"] == "3 archivos; 2 periodos unificados."
    assert len(result["excludedFiles"]) == 3


def test_unrecognized_annual_range_includes_whole_year():
    result = process_annual(2026, "rango desconocido", [source("A\n1", period="Dec_2026")])
    assert result["processedFiles"] == 1
    assert result["warnings"][0]["code"] == "UNRECOGNIZED_RANGE"
    assert result["functionalResult"] == "OK"


def test_limits_reject_whole_later_file_preserving_previous_version_of_group():
    result = process_monthly("Abril_2026", [source("A\n1"), source("A\n2")], EngineOptions(max_rows=1))
    assert result["functionalResult"] == "WARNING"
    assert result["tables"][0]["rows"][0][-1] == "1"
    assert len(result["tables"][0]["rows"]) == 1
    assert result["processedFiles"] == 1
    assert result["failedFiles"] == 1


def test_deterministic_result_for_repeated_processing():
    files = [source("Patente|Pedimento|SeccionAduanera|FechaPagoReal\n0001|0000002|7|20260423")]
    assert process_monthly("Abril_2026", files) == process_monthly("Abril_2026", files)


def test_folio_suffix_and_path():
    assert folio_from_name("folder/A-B_1896462_501.asc", "501") == "1896462"
    assert folio_from_name("1896462-sel.ASC", "sel") == "1896462"
