"""Private workbook initialization and supersession of historical evidence."""
import json

import pytest
from sqlalchemy import func, select

from app.modules.identity.auth import Principal
from app.modules.suppliers import service
from app.persistence import Base, make_engine, session_factory
from app.persistence.models import Period, Run
from app.persistence.suppliers import Supplier, SupplierObservation


@pytest.fixture
def database():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with session_factory(engine)() as session:
        yield session
    engine.dispose()


def principal(scope="supplier-test"):
    return Principal("tester", "Tester", frozenset({"Admin", "Operator", "Reader"}), scope)


def seed():
    return {
        "schemas": service.DEFAULT_SCHEMAS,
        "national": [{"RFC": "ABC010101AB1", "Operaciones virtuales": "No", "Estatus": "Sin modificación",
                      "source": {"file": "national.xls", "sheet": "Sheet1", "row": 2, "sha256": "a" * 64}}],
        "foreign": [{"Nombre o Razón social": "Ácme, S.A.", "Apellido Paterno": "", "Apellido Materno": "",
                     "País ": "Estados Unidos de América", "Domicilio": "", "Cliente/Proveedor": "Proveedor",
                     "Estatus": "Alta", "source": {"file": "foreign.xls", "sheet": "Sheet1", "row": 2,
                                                     "sha256": "b" * 64}}],
    }


def baseline():
    operation = {"Periodo": "Enero_2026", "Patente": "0036", "Pedimento": "0000009", "SeccionAduanera": "240",
                 "PedimentoCompleto": "26 24 0036 0000009", "ArchivoOrigen": "request.asc", "FolioOrigen": "request"}
    foreign_operation = {**operation, "Pedimento": "0000010", "PedimentoCompleto": "26 24 0036 0000010"}
    source = {"file": "annual.xlsx", "sha256": "c" * 64}
    return {"baseline": {"source": source, "tables": {
        "501": [{**operation, "Rfc": "XYZ010101XY1", "ClaveDocumento": "V1", "TipoOperacion": "1",
                 "source": {**source, "sheet": "501 Datos generales", "row": 2}},
                {**foreign_operation, "Rfc": "XYZ010101XY1", "ClaveDocumento": "A1", "TipoOperacion": "1",
                 "source": {**source, "sheet": "501 Datos generales", "row": 3}}],
        "505": [{**foreign_operation, "PaisFacturacion": "USA", "IndentFiscalProveedor": "",
                 "ProveedorMercancia": "ACME S A", "source": {**source, "sheet": "505 Facturas", "row": 2}}],
        "507": [{**operation, "ClaveCaso": "V1", "IdentificadorCaso": "ABC010101AB1", "ComplementoCaso": "CN",
                 "source": {**source, "sheet": "507 Casos pedimento", "row": 2}}],
    }}}


def test_baseline_is_idempotent_and_matches_template_country_and_punctuation(database):
    session, user = database, principal()
    service.initialize_seed(session, user, seed())
    first = service.ingest_baseline(session, user, baseline())
    count = session.scalar(select(func.count()).select_from(SupplierObservation))
    second = service.ingest_baseline(session, user, baseline())
    assert first["catalog"] == second["catalog"] == 2
    assert first["pending"] == second["pending"] == 0
    assert session.scalar(select(func.count()).select_from(SupplierObservation)) == count == 2
    suppliers = {row.kind: row for row in session.scalars(select(Supplier))}
    original = json.loads(suppliers["foreign"].data_json)
    assert original["originalRow"] == {header: seed()["foreign"][0][header]
                                       for header in service.DEFAULT_SCHEMAS["foreign"]}
    assert original["originalRow"]["País "] == "Estados Unidos de América"
    assert suppliers["foreign"].country == "USA"
    assert suppliers["foreign"].original_status == "Alta"
    assert service.supplier_response(session, suppliers["national"])["virtualOperations"] is True
    evidence = service.supplier_response(session, suppliers["national"], evidence=True)["evidence"]
    assert any(record["table"] == "507" and record["source"]["sheet"] == "507 Casos pedimento"
               for entry in evidence if "records" in entry for record in entry["records"])


def test_published_month_supersedes_only_matching_baseline_period_and_keeps_catalog(database):
    session, user = database, principal()
    service.initialize_seed(session, user, seed())
    payload = baseline()
    february = {**payload["baseline"]["tables"]["505"][0], "Periodo": "Febrero_2026"}
    payload["baseline"]["tables"]["505"].append(february)
    service.ingest_baseline(session, user, payload)
    national = session.scalar(select(Supplier).where(Supplier.kind == "national"))
    assert service.supplier_response(session, national)["virtualOperations"] is True
    period = Period(scope_id=user.scope_id, year=2026, month=1, name="Enero_2026")
    session.add(period)
    session.flush()
    run = Run(scope_id=user.scope_id, kind="monthly", year=2026, period_id=period.id,
              input_fingerprint="e" * 64, publication_status="published", status="completed")
    session.add(run)
    session.flush()
    period.active_run_id = run.id
    session.flush()
    service.sync_active_history(session, user.scope_id, user.id)
    rows = list(session.scalars(select(SupplierObservation)))
    assert all(not row.active for row in rows if row.period_name == "Enero_2026")
    assert all(row.active for row in rows if row.period_name == "Febrero_2026")
    assert service.supplier_response(session, national)["virtualOperations"] is False
    assert session.scalar(select(func.count()).select_from(Supplier)) == 2
    before = len(rows)
    service.sync_active_history(session, user.scope_id, user.id)
    assert session.scalar(select(func.count()).select_from(SupplierObservation)) == before
    period.active_run_id = None
    session.flush()
    service.sync_active_history(session, user.scope_id, user.id)
    assert all(not row.active for row in session.scalars(select(SupplierObservation))
               if row.period_name == "Enero_2026")
    assert service.supplier_response(session, national)["virtualOperations"] is False


@pytest.mark.parametrize("contradiction", ["contributor_rfc", "immex", "other_operation", "other_period"])
def test_virtual_evidence_requires_counterparty_semantics_and_complete_operation(database, contradiction):
    session, user = database, principal()
    service.initialize_seed(session, user, seed())
    payload = baseline()
    tables = payload["baseline"]["tables"]
    if contradiction == "contributor_rfc":
        tables["501"][0]["Rfc"] = "ABC010101AB1"
    elif contradiction == "immex":
        tables["507"][0]["ComplementoCaso"] = "IM"
    elif contradiction == "other_operation":
        tables["507"][0]["PedimentoCompleto"] = "26 24 0036 0000999"
    else:
        tables["507"][0]["Periodo"] = "Febrero_2026"
    service.ingest_baseline(session, user, payload)
    national = session.scalar(select(Supplier).where(Supplier.kind == "national"))
    assert service.supplier_response(session, national)["virtualOperations"] is False
    assert session.scalar(select(func.count()).select_from(Supplier)) == 2


def test_national_country_does_not_make_foreign_tax_number_a_valid_supplier_rfc(database):
    session, user = database, principal()
    service.initialize_seed(session, user, seed())
    payload = baseline()
    payload["baseline"]["tables"]["505"][0].update(
        PaisFacturacion="MEX", IndentFiscalProveedor="06-0000010", ProveedorMercancia="Another foreign supplier")
    service.ingest_baseline(session, user, payload)
    reviews = service.list_reviews(session, user.scope_id)
    assert len(reviews) == 1
    assert reviews[0]["reason"] == "missing_identity"
    assert session.scalar(select(func.count()).select_from(Supplier)) == 2
    foreign = session.scalar(select(Supplier).where(Supplier.kind == "foreign"))
    service.resolve_review(session, user, reviews[0]["id"], "same", foreign.id,
                           expected_version=reviews[0]["version"], reason="Country field contradicts established supplier")
    assert service.list_reviews(session, user.scope_id) == []
    payload["baseline"]["source"]["sha256"] = "d" * 64
    service.ingest_baseline(session, user, payload)
    assert service.list_reviews(session, user.scope_id) == []
    assert session.scalar(select(func.count()).select_from(Supplier)) == 2
