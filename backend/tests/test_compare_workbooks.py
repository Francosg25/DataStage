from datetime import datetime
import hashlib
import json
import shutil

import xlsxwriter

from app.cli.compare_workbooks import compare_workbooks, main


def write_workbook(path, sheets, *, date_1904=False):
    with xlsxwriter.Workbook(path, {"date_1904": date_1904, "strings_to_formulas": False}) as workbook:
        date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
        for name, rows in sheets:
            worksheet = workbook.add_worksheet(name)
            for row_number, row in enumerate(rows):
                for column, value in enumerate(row):
                    if isinstance(value, datetime):
                        worksheet.write_datetime(row_number, column, value, date_format)
                    elif isinstance(value, str):
                        worksheet.write_string(row_number, column, value)
                    elif value is not None:
                        worksheet.write(row_number, column, value)


def sample():
    return [("Control_Proceso", [["Archivo", "Filas", "Columnas"], ["source_501.asc", 1, 3]]),
            ("501 Datos generales", [["Patente", "PedimentoCompleto", "FechaPagoReal"],
                                      ["0036", "26 24 0036 0000009", datetime(2026, 4, 20, 13, 14, 15)]])]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_identical_workbooks_match_without_modifying_inputs(tmp_path):
    generated, reference = tmp_path / "generated.xlsx", tmp_path / "reference.xlsx"
    write_workbook(reference, sample())
    shutil.copyfile(reference, generated)
    before = (digest(generated), digest(reference))
    report = compare_workbooks(generated, reference)
    assert report["match"]
    assert report["differenceCount"] == 0
    assert report["sheetSummaries"][1]["generated"]["dataRows"] == 1
    assert report["sheetSummaries"][1]["generated"]["headerColumns"] == 3
    assert (digest(generated), digest(reference)) == before
    assert main([str(generated), str(reference)]) == 0


def test_differences_cover_types_leading_zeros_pedimento_dates_and_control(tmp_path):
    generated, reference = tmp_path / "generated.xlsx", tmp_path / "reference.xlsx"
    write_workbook(reference, sample())
    changed = sample()
    changed[0][1][1][1] = 2
    changed[1][1][1] = [36, "SECRET_DIFFERENT_PEDIMENTO", datetime(2026, 4, 21, 13, 14, 15)]
    write_workbook(generated, changed)
    report = compare_workbooks(generated, reference)
    assert not report["match"]
    assert report["differenceCount"] == 4
    assert report["differencesByKind"] == {"cell_type": 1, "control_cell": 1, "date_value": 1, "pedimento_cell": 1}
    typed = next(item for item in report["differences"] if item["kind"] == "cell_type")
    assert typed["cell"] == "A2"
    assert typed["expectedType"] == "text"
    assert typed["actualType"] == "number"
    assert "SECRET_DIFFERENT_PEDIMENTO" not in json.dumps(report)
    assert all("actual" not in item and "expected" not in item for item in report["differences"])


def test_cli_reports_bounded_samples_but_counts_all_changes(tmp_path, capsys):
    generated, reference, target = tmp_path / "generated.xlsx", tmp_path / "reference.xlsx", tmp_path / "report.json"
    write_workbook(reference, [("Data", [["A", "B", "C", "D"], ["one", "two", "three", "four"]])])
    write_workbook(generated, [("Data", [["A", "B", "C", "D"], ["SECRET_VALUE_LONG", "newtwo", "newthree", "newfour"]])])
    assert main([str(generated), str(reference), "--report", str(target), "--include-values",
                 "--max-differences", "2", "--max-value-characters", "5"]) == 1
    console = capsys.readouterr().out
    assert "SECRET" not in console
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["differenceCount"] == 4
    assert len(report["differences"]) == 2
    assert report["samplesTruncated"]
    assert report["differences"][0]["actual"] == {"preview": "SECRE", "length": 17, "truncated": True}


def test_sheet_and_header_order_and_row_counts_are_compared(tmp_path):
    generated, reference = tmp_path / "generated.xlsx", tmp_path / "reference.xlsx"
    write_workbook(reference, [("A", [["First", "Second"], ["1", "2"]]), ("B", [["X"]])])
    write_workbook(generated, [("Extra", [["X"]]), ("A", [["Second", "First"], ["1", "2"], ["3", "4"]])])
    report = compare_workbooks(generated, reference)
    categories = report["differencesByKind"]
    assert categories["sheet_order"] == 1
    assert categories["missing_sheet"] == categories["extra_sheet"] == 1
    assert categories["header"] == 2
    assert categories["sheet_dataRows"] == 1


def test_native_dates_match_across_excel_epochs_but_text_date_does_not(tmp_path):
    generated, reference = tmp_path / "generated.xlsx", tmp_path / "reference.xlsx"
    rows = [("Dates", [["Fecha"], [datetime(2026, 4, 20)]])]
    write_workbook(reference, rows)
    write_workbook(generated, rows, date_1904=True)
    assert compare_workbooks(generated, reference)["match"]
    write_workbook(generated, [("Dates", [["Fecha"], ["2026-04-20T00:00:00"]])])
    assert compare_workbooks(generated, reference)["differencesByKind"] == {"cell_type": 1}


def test_report_cannot_replace_compared_workbook(tmp_path, capsys):
    generated, reference = tmp_path / "generated.xlsx", tmp_path / "reference.xlsx"
    write_workbook(reference, sample())
    shutil.copyfile(reference, generated)
    before = digest(reference)
    assert main([str(generated), str(reference), "--report", str(reference)]) == 2
    assert digest(reference) == before
    assert "error" in capsys.readouterr().err


def test_missing_input_returns_two_and_no_report(tmp_path, capsys):
    target = tmp_path / "report.json"
    assert main([str(tmp_path / "missing.xlsx"), str(tmp_path / "reference.xlsx"), "--report", str(target)]) == 2
    assert not target.exists()
    assert "error" in capsys.readouterr().err
