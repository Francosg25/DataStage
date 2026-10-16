"""Monthly worker publication creates paired reports and waits for identity decisions."""
import io
from uuid import uuid4

import openpyxl
from sqlalchemy import func, select
import test_api_worker

from app.modules.identity.auth import Principal, current_principal
from app.persistence.suppliers import SupplierReportRequest


system = test_api_worker.system
NATIONAL_HEADERS = ["RFC", "Operaciones virtuales", "Estatus"]
FOREIGN_HEADERS = ["Nombre o Razón social", "Apellido Paterno", "Apellido Materno", "País ",
                   "Domicilio", "Cliente/Proveedor", "Estatus"]
PERIODS = {1: "Enero_2026", 2: "Febrero_2026", 3: "Marzo_2026"}


def entries(month, names):
    headers = "Patente|Pedimento|SeccionAduanera|TipoOperacion|ClaveDocumento|Rfc|FechaPagoReal\n"
    invoices = ("Patente|Pedimento|SeccionAduanera|NumeroFactura|PaisFacturacion|IndentFiscalProveedor|"
                "ProveedorMercancia|CalleProveedor|NumExteriorProveedor|CpProveedor|MunicipioProveedor|FechaPagoReal\n")
    for index, name in enumerate(names, 1):
        number = str(6000000 + month * 100 + index)
        paid = f"2026-{month:02d}-15 12:00:00"
        headers += f"0036|{number}|240|1|A1|XYZ010101XY1|{paid}\n"
        invoices += f"0036|{number}|240|INV-{month}-{index}|USA||{name}|MAIN STREET|10|10001|NEW YORK|{paid}\n"
    return {"source_501.asc": headers, "source_505.asc": invoices}


def publish(system, month, names, *, key=None):
    app, client, settings = system
    response = test_api_worker.upload(client, entries(month, names), PERIODS[month], key=key)
    assert response.status_code == 202, response.text
    test_api_worker.drain(app, settings)
    run_id = response.json()["id"]
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["publicationStatus"] == "published", run
    assert run["status"] == "completed", run
    return run_id


def state(client, run_id):
    response = client.get(f"/api/v1/suppliers/runs/{run_id}/report")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["runId"] == run_id
    return result


def workbook(client, report_id, kind):
    response = client.get(f"/api/v1/suppliers/reports/{report_id}/{kind}.xlsx")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    book = openpyxl.load_workbook(io.BytesIO(response.content))
    sheet = book.active
    assert [cell.value for cell in sheet[1]] == (NATIONAL_HEADERS if kind == "national" else FOREIGN_HEADERS)
    return response.content, sheet


def assert_highlight(row, expected):
    assert all((cell.fill.patternType == "solid" and cell.fill.fgColor.rgb[-6:] == "FFFF00") is expected
               for cell in row)


def resolve_same(client, review, supplier_id):
    response = client.post(f"/api/v1/suppliers/reviews/{review['id']}/resolve", json={
        "decision": "same", "supplierId": supplier_id, "expectedVersion": review["version"],
        "reason": "Confirmada la variante Electric/Eletric del mismo proveedor",
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_three_months_generate_paired_reports_and_recognize_supported_typo_automatically(system):
    app, client, settings = system
    key = str(uuid4())
    january = publish(system, 1, ["Johnson Electric LLC"], key=key)
    first = state(client, january)
    assert first["status"] == "ready" and first["pending"] == 0
    assert first["report"] is not None
    first_id = first["report"]["id"]
    national_bytes, national = workbook(client, first_id, "national")
    foreign_bytes, foreign = workbook(client, first_id, "foreign")
    assert national.max_row == 1
    assert foreign.max_row == 2
    assert foreign["A2"].value == "Johnson Electric LLC"
    assert foreign["G2"].value == "Alta"
    assert_highlight(foreign[2], True)
    assert client.get("/api/v1/suppliers").json()["total"] == 1

    repeated = test_api_worker.upload(client, entries(1, ["Johnson Electric LLC"]), PERIODS[1], key=key)
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["id"] == january
    test_api_worker.drain(app, settings)
    assert state(client, january)["report"]["id"] == first_id
    assert client.get("/api/v1/suppliers/reports").json()["total"] == 1
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SupplierReportRequest)) == 1

    february = publish(system, 2, ["Johnson Eletric LLC"])
    waiting = state(client, february)
    assert waiting["status"] == "ready" and waiting["pending"] == 0
    reviews = client.get("/api/v1/suppliers/reviews").json()
    assert reviews["total"] == 0
    assert client.get("/api/v1/suppliers/reports").json()["total"] == 2
    assert client.get("/api/v1/suppliers").json()["total"] == 1
    with app.state.session_factory() as session:
        pending_request = session.scalar(select(SupplierReportRequest).where(
            SupplierReportRequest.source_run_id == february))
        assert pending_request is not None and pending_request.report_id is not None
        for kind in ("national", "foreign"):
            assert client.get(f"/api/v1/suppliers/reports/{pending_request.id}/{kind}.xlsx").status_code == 404

    second = state(client, february)
    assert second["status"] == "ready" and second["pending"] == 0
    assert second["report"]["id"] != first_id
    _, national_second = workbook(client, second["report"]["id"], "national")
    _, foreign_second = workbook(client, second["report"]["id"], "foreign")
    assert national_second.max_row == 1 and foreign_second.max_row == 2
    assert foreign_second["A2"].value == "Johnson Electric LLC"
    assert foreign_second["G2"].value == "Sin modificación"
    assert_highlight(foreign_second[2], False)
    assert client.get("/api/v1/suppliers/equivalences").json()["total"] == 0

    march = publish(system, 3, ["Johnson Eletric LLC"])
    third = state(client, march)
    assert third["status"] == "ready" and third["pending"] == 0
    assert client.get("/api/v1/suppliers/reviews").json()["total"] == 0
    assert client.get("/api/v1/suppliers").json()["total"] == 1
    _, third_foreign = workbook(client, third["report"]["id"], "foreign")
    workbook(client, third["report"]["id"], "national")
    assert third_foreign.max_row == 2 and third_foreign["G2"].value == "Sin modificación"
    assert_highlight(third_foreign[2], False)
    assert client.get("/api/v1/suppliers/reports").json()["total"] == 3
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SupplierReportRequest)) == 3
    assert workbook(client, first_id, "national")[0] == national_bytes
    assert workbook(client, first_id, "foreign")[0] == foreign_bytes


def test_monthly_report_state_and_requests_respect_scope_and_reader_access(system):
    app, client, _ = system
    january = publish(system, 1, ["Johnson Electric LLC"])
    report_id = state(client, january)["report"]["id"]
    app.dependency_overrides[current_principal] = lambda: Principal(
        "reader", "Reader", frozenset({"Reader"}), "local")
    assert state(client, january)["status"] == "ready"
    response = client.get("/api/v1/suppliers/report-requests")
    assert response.status_code == 200 and response.json()["total"] == 1
    app.dependency_overrides[current_principal] = lambda: Principal(
        "other-reader", "Other reader", frozenset({"Reader"}), "other-scope")
    try:
        assert client.get(f"/api/v1/suppliers/runs/{january}/report").status_code == 404
        response = client.get("/api/v1/suppliers/report-requests")
        assert response.status_code == 200 and response.json()["total"] == 0
        for kind in ("national", "foreign"):
            assert client.get(f"/api/v1/suppliers/reports/{report_id}/{kind}.xlsx").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_each_month_keeps_its_own_pair_and_later_suppliers_do_not_leak_back(system):
    _, client, _ = system
    january = publish(system, 1, ["Johnson Electric LLC"])
    first_id = state(client, january)["report"]["id"]
    first_bytes, _ = workbook(client, first_id, "foreign")
    february = publish(system, 2, ["Johnson Electronic LLC"])
    second = state(client, february)
    assert second["status"] == "ready" and second["pending"] == 0
    march = publish(system, 3, ["Zebra Industrial Components Ltd"])
    third = state(client, march)
    _, feb = workbook(client, second["report"]["id"], "foreign")
    _, mar = workbook(client, third["report"]["id"], "foreign")
    assert {row[0].value for row in list(feb.rows)[1:]} == {"Johnson Electric LLC", "Johnson Electronic LLC"}
    assert {row[0].value for row in list(mar.rows)[1:]} == {"Johnson Electric LLC", "Johnson Electronic LLC", "Zebra Industrial Components Ltd"}
    for row in list(mar.rows)[1:]:
        assert_highlight(row, row[0].value.startswith("Zebra"))
    assert workbook(client, first_id, "foreign")[0] == first_bytes
    assert client.get("/api/v1/suppliers/reviews").json()["total"] == 0


def test_distinct_new_name_is_added_and_highlighted_without_a_review_step(system):
    _, client, _ = system
    publish(system, 1, ["Johnson Electric LLC"])
    february = publish(system, 2, ["Johnson Electronic LLC"])
    completed = state(client, february)
    assert completed["status"] == "ready" and completed["pending"] == 0
    workbook(client, completed["report"]["id"], "national")
    _, foreign = workbook(client, completed["report"]["id"], "foreign")
    rows = {row[0].value: row for row in list(foreign.rows)[1:]}
    assert set(rows) == {"Johnson Electric LLC", "Johnson Electronic LLC"}
    assert rows["Johnson Electronic LLC"][-1].value == "Alta"
    assert_highlight(rows["Johnson Electronic LLC"], True)
    assert_highlight(rows["Johnson Electric LLC"], False)
    assert client.get("/api/v1/suppliers/reviews").json()["total"] == 0
