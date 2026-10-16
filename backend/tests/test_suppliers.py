"""Supplier identity, live evidence and transactional publication regression tests."""
from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook
import pytest
from sqlalchemy import select

from app.modules.identity.auth import Principal
from app.modules.suppliers import service as suppliers
from app.persistence import Base, make_engine, session_factory
from app.persistence.business import BUSINESS_TABLES
from app.persistence.models import AuditEvent, Period, ProcessingFile, Run


@pytest.fixture
def domain():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    with factory.begin() as session:
        yield session, Principal("operator", "Operator", frozenset({"Admin"}), "tenant")
    engine.dispose()


def publish(session, principal, month, invoices=(), identifiers=(), *, contributor="CON010101AA1"):
    period = session.scalar(select(Period).where(Period.scope_id == principal.scope_id, Period.month == month))
    if period is None:
        period = Period(scope_id=principal.scope_id, year=2026, month=month,
                        name=["Enero_2026", "Febrero_2026", "Marzo_2026"][month - 1])
        session.add(period)
        session.flush()
    run = Run(scope_id=principal.scope_id, period_id=period.id, year=2026,
              input_fingerprint=uuid4().hex * 2, status="completed", publication_status="published")
    session.add(run)
    session.flush()
    for ordinal, (code, rows) in enumerate((("501", [{"rfc": contributor, "clave_documento": "V1"}]),
                                           ("505", invoices), ("507", identifiers))):
        source = ProcessingFile(run_id=run.id, period_id=period.id, file_name=f"source_{code}.asc",
                                table_code=code, sha256=uuid4().hex * 2, ordinal=ordinal)
        session.add(source)
        session.flush()
        for row_number, row in enumerate(rows, 2):
            data = {"period_id": period.id, "processing_run_id": run.id, "processing_file_id": source.id,
                    "archivo_origen": source.file_name, "folio_origen": "source", "table_code": code,
                    "source_row_number": row_number, "pedimento_completo": "26 24 0036 6000001"}
            session.execute(BUSINESS_TABLES[code].insert().values(**{**data, **row}))
    period.active_run_id, period.version = run.id, period.version + 1
    session.flush()
    suppliers.sync_active_history(session, principal.scope_id, principal.id)
    return run


def invoice(name="Álamo Tecnología, S.A.", tax="TAX-100", country="USA", **kwargs):
    return {"proveedor_mercancia": name, "indent_fiscal_proveedor": tax, "pais_facturacion": country,
            "calle_proveedor": "100 Main St.", **kwargs}


def test_monthly_history_normalizes_punctuation_and_minor_name_changes_without_review(domain):
    session, principal = domain
    publish(session, principal, 1, [invoice()])
    publish(session, principal, 2, [invoice(name="alamo tecnologia SA", tax="TAX100", country="United States")])
    publish(session, principal, 3, [invoice(name="ALAMO TECNOLOGIAS SA", tax="")])
    assert len(suppliers.list_suppliers(session, principal.scope_id)) == 1
    assert suppliers.list_reviews(session, principal.scope_id) == []


def test_virtual_or_history_no_reset_and_replaced_evidence_invalidated(domain):
    session, principal = domain
    national = invoice("Proveedor Nacional SA", "ABC010101AA1", "MEX")
    first = publish(session, principal, 1, [national], [
        {"clave_caso": "V1", "identificador_caso": "ABC010101AA1", "complemento_caso": "CN"}])
    supplier = suppliers.list_suppliers(session, principal.scope_id)[0]
    assert supplier["virtualOperations"] is True
    publish(session, principal, 2, [national])
    assert suppliers.get_supplier(session, principal.scope_id, supplier["id"])["virtualOperations"] is True
    # Replacing the month removes its virtual support, without deleting the supplier.
    publish(session, principal, 1, [national])
    detail = suppliers.get_supplier(session, principal.scope_id, supplier["id"])
    assert detail["virtualOperations"] is False
    assert not next(e for e in detail["evidence"] if e["runId"] == first.id)["active"]
    updated = suppliers.update_supplier(session, principal, supplier["id"],
                                         {"virtualConfirmation": True, "reason": "Confirmación de historial"}, detail["version"])
    suppliers.retire_runs(session, principal.scope_id, [e["runId"] for e in updated["evidence"]])
    assert suppliers.get_supplier(session, principal.scope_id, supplier["id"])["virtualOperations"] is True


def test_immex_and_contributor_rfc_never_become_supplier_rfc(domain):
    session, principal = domain
    publish(session, principal, 1, [invoice("Nacional sin virtuales", "ABC010101AA1", "MEX")], [
        {"clave_caso": "V1", "identificador_caso": "42832006", "complemento_caso": "IM"}])
    national = suppliers.list_suppliers(session, principal.scope_id)[0]
    assert national["taxId"] == "ABC010101AA1" and national["virtualOperations"] is False
    assert suppliers.list_reviews(session, principal.scope_id) == []
    publish(session, principal, 2, [invoice("Contribuyente como proveedor", "CON010101AA1", "MEX")])
    assert all(s["taxId"] != "CON010101AA1" for s in suppliers.list_suppliers(session, principal.scope_id))


def test_new_505_supplier_uses_older_independent_virtual_evidence_and_tracks_its_retirement(domain):
    session, principal = domain
    first = publish(session, principal, 1, [], [
        {"clave_caso": "V1", "identificador_caso": "ABC010101AA1", "complemento_caso": "CN"}])
    assert suppliers.list_suppliers(session, principal.scope_id) == []  # 507 never creates a supplier.
    assert suppliers.list_reviews(session, principal.scope_id) == []
    publish(session, principal, 2, [invoice("Identificado por 505", "ABC010101AA1", "MEX")])
    supplier = suppliers.list_suppliers(session, principal.scope_id)[0]
    assert supplier["virtualOperations"] is True
    assert suppliers.list_reviews(session, principal.scope_id) == []
    detail = suppliers.get_supplier(session, principal.scope_id, supplier["id"])
    assert any(e["runId"] == first.id and e["virtualConfirmed"] for e in detail["evidence"])
    publish(session, principal, 1, [], [])
    assert suppliers.get_supplier(session, principal.scope_id, supplier["id"])["virtualOperations"] is False


def test_national_is_available_before_virtual_evidence_and_updates_from_history(domain):
    session, principal = domain
    publish(session, principal, 1, [invoice("Nacional identificado", "ABC010101AA1", "")])
    supplier = suppliers.list_suppliers(session, principal.scope_id)[0]
    assert supplier["type"] == "national" and supplier["virtualOperations"] is False
    publish(session, principal, 2, [], [
        {"clave_caso": "V1", "identificador_caso": "ABC010101AA1", "complemento_caso": "CN"}])
    assert suppliers.list_reviews(session, principal.scope_id) == []
    assert suppliers.get_supplier(session, principal.scope_id, supplier["id"])["virtualOperations"] is True


def test_optional_fiscal_id_and_address_changes_do_not_duplicate_the_same_foreign_name(domain):
    session, principal = domain
    publish(session, principal, 1, [invoice()])
    existing = suppliers.list_suppliers(session, principal.scope_id)[0]
    publish(session, principal, 2, [invoice(tax="TAX200", calle_proveedor="500 Another St")])
    assert suppliers.list_reviews(session, principal.scope_id) == []
    assert [s["id"] for s in suppliers.list_suppliers(session, principal.scope_id)] == [existing["id"]]
    assert suppliers.get_supplier(session, principal.scope_id, existing["id"])["evidenceCount"] == 2


@pytest.mark.parametrize("code,mode", [("V1", "CN"), ("V1", "RFE"), ("V1", "V2"), ("V2", ""), ("V8", ""), ("V5", ""), ("V6", "")])
def test_supported_507_rfc_modes_confirm_virtual(code, mode, domain):
    session, principal = domain
    publish(session, principal, 1, [invoice("Nacional", "ABC010101AA1", "MEX")], [
        {"clave_caso": code, "identificador_caso": "ABC010101AA1", "complemento_caso": mode}])
    assert suppliers.list_suppliers(session, principal.scope_id)[0]["virtualOperations"] is True


def test_report_immutable_pair_yellow_cycle_and_retry(domain):
    session, principal = domain
    publish(session, principal, 1, [invoice()])
    report = suppliers.create_report(session, principal, "report-month-001", "Primer reporte")
    before = suppliers.report_xlsx(session, principal.scope_id, report["id"], "foreign")
    book = load_workbook(BytesIO(before))
    assert book.active.max_column == 7
    assert [cell.value for cell in book.active[1]] == suppliers.DEFAULT_SCHEMAS["foreign"]
    assert book.active.cell(2, 7).value == "Alta"
    assert all(c.fill.fgColor.rgb == "FFFFFF00" for c in book.active[2])
    assert suppliers.create_report(session, principal, "report-month-001", "Primer reporte")["id"] == report["id"]
    assert len(suppliers.list_reports(session, principal.scope_id)) == 1
    second = suppliers.create_report(session, principal, "report-month-002", "Segundo reporte")
    later = load_workbook(BytesIO(suppliers.report_xlsx(session, principal.scope_id, second["id"], "foreign")))
    assert later.active.cell(2, 7).value == "Sin modificación"
    assert all(c.fill.fgColor.rgb != "FFFFFF00" for c in later.active[2])
    assert suppliers.report_xlsx(session, principal.scope_id, report["id"], "foreign") == before
    assert load_workbook(BytesIO(suppliers.report_xlsx(session, principal.scope_id, report["id"], "national"))).active.max_column == 3
    assert any(e.action == "suppliers.report_created" for e in session.scalars(select(AuditEvent)))


def test_completed_monthly_reports_remain_frozen_when_an_earlier_month_is_replaced(domain):
    session, principal = domain
    january = publish(session, principal, 1, [invoice()])
    suppliers.request_monthly_report(session, january, principal.id)
    first = suppliers.monthly_report_state(session, principal.scope_id, january.id)
    before = suppliers.report_xlsx(session, principal.scope_id, first["report"]["id"], "foreign")
    february = publish(session, principal, 2, [invoice(name="ALAMO TECNOLOGIAS SA", tax="")])
    suppliers.request_monthly_report(session, february, principal.id)
    second = suppliers.monthly_report_state(session, principal.scope_id, february.id)
    assert second["status"] == "ready"
    second_before = suppliers.report_xlsx(session, principal.scope_id, second["report"]["id"], "foreign")
    publish(session, principal, 1, [])
    assert suppliers.report_xlsx(session, principal.scope_id, first["report"]["id"], "foreign") == before
    assert suppliers.report_xlsx(session, principal.scope_id, second["report"]["id"], "foreign") == second_before


def test_national_505_identity_automatically_delivers_both_files_without_confirmation(domain):
    session, principal = domain
    run = publish(session, principal, 1, [invoice("Proveedor nacional", "ABC010101AA1", "MEX")])
    suppliers.request_monthly_report(session, run, principal.id)
    state = suppliers.monthly_report_state(session, principal.scope_id, run.id)
    assert state["status"] == "ready" and suppliers.list_reviews(session, principal.scope_id) == []
    national = load_workbook(BytesIO(suppliers.report_xlsx(session, principal.scope_id, state["report"]["id"], "national")))
    assert [cell.value for cell in national.active[2]] == ["ABC010101AA1", "No", "Alta"]
    assert all(cell.fill.fgColor.rgb == "FFFFFF00" for cell in national.active[2])
    assert load_workbook(BytesIO(suppliers.report_xlsx(session, principal.scope_id, state["report"]["id"], "foreign"))).active.max_row == 1
