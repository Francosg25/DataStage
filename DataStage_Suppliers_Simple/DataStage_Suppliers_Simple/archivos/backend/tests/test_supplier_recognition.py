"""Business regressions for low-intervention cumulative supplier lists."""
import json

from sqlalchemy import select

from app.modules.suppliers import service
from app.persistence.suppliers import Supplier, SupplierObservation
from test_suppliers import domain as domain, invoice, publish


def seed(session, user, name="Precision Components Limited", country="USA"):
    return service.initialize_seed(session, user, {"foreign": [{
        "Nombre o Razón social": name, "País ": country, "Domicilio": "100 Main Street",
        "Estatus": "Sin modificación", "Cliente/Proveedor": "Proveedor",
    }]})


def test_missing_country_known_name_and_changed_address_do_not_require_review(domain):
    session, user = domain
    seed(session, user)
    publish(session, user, 1, [invoice("PRECISION / COMPONENTS, LTD.", "US-112233", "", calle_proveedor="Another branch")])
    assert service.list_reviews(session, user.scope_id) == []
    suppliers = service.list_suppliers(session, user.scope_id)
    assert len(suppliers) == 1 and suppliers[0]["country"] == "USA"
    # The original erroneous/missing source values remain available as evidence.
    observation = session.scalar(select(SupplierObservation).where(SupplierObservation.source_row_id.not_like("507:%")))
    assert json.loads(observation.candidate_json)["country"] == ""


def test_foreign_supplier_is_not_reclassified_by_mex_country_and_nonnational_id(domain):
    session, user = domain
    seed(session, user)
    publish(session, user, 1, [invoice("Precision Components Limited", "06-1122334", "MEX")])
    assert service.list_reviews(session, user.scope_id) == []
    assert service.summary(session, user.scope_id)["foreign"] == 1
    assert service.summary(session, user.scope_id)["national"] == 0


def test_minor_typo_matches_and_a_distinct_subsidiary_is_added_separately(domain):
    session, user = domain
    publish(session, user, 1, [invoice("Precision Components Limited", "US-112233")])
    publish(session, user, 2, [invoice("Precisoin Components Limited", "US112233", calle_proveedor="Different branch")])
    assert service.list_reviews(session, user.scope_id) == []
    publish(session, user, 3, [invoice("Precision Components Asia Limited", "US112233")])
    assert service.list_reviews(session, user.scope_id) == []
    assert len(service.list_suppliers(session, user.scope_id)) == 2


def test_sn_is_missing_and_cannot_link_unrelated_suppliers(domain):
    session, user = domain
    publish(session, user, 1, [invoice("Precision Components Limited", "S/N"), invoice("Valley Metals Limited", "SN")])
    assert len(service.list_suppliers(session, user.scope_id)) == 2
    assert service.list_reviews(session, user.scope_id) == []


def test_later_complete_invoice_fills_an_earlier_optional_country_gap(domain):
    session, user = domain
    publish(session, user, 1, [invoice("Precision Components Limited", "US112233", "")])
    assert service.list_reviews(session, user.scope_id) == []
    assert service.list_suppliers(session, user.scope_id)[0]["country"] == ""
    publish(session, user, 2, [invoice("Precision Components Limited", "US112233", "USA")])
    suppliers = service.list_suppliers(session, user.scope_id)
    assert len(suppliers) == 1 and suppliers[0]["country"] == "USA"


def test_same_foreign_name_survives_optional_ids_and_addresses_without_duplicates(domain):
    session, user = domain
    publish(session, user, 1, [invoice("Precision Components Limited", "US112233")])
    publish(session, user, 2, [invoice("Precision Components Limited", "US445566", calle_proveedor="Branch A"),
                              invoice("Precision Components Limited", "US445566", calle_proveedor="Branch B")])
    publish(session, user, 3, [invoice("Precision Components Limited", "US445566", calle_proveedor="Branch C")])
    assert service.list_reviews(session, user.scope_id) == []
    assert len(service.list_suppliers(session, user.scope_id)) == 1


def test_original_lists_can_be_imported_after_processing_without_wiping_catalog(domain):
    session, user = domain
    publish(session, user, 1, [invoice("An existing supplier", "US998877")])
    publish(session, user, 2, [invoice("Precision Components Limited", "US112233", "")])
    assert service.summary(session, user.scope_id)["pending"] == 0
    result = seed(session, user)
    assert result["catalog"] == 2 and result["pending"] == 0
    assert seed(session, user)["catalog"] == 2


def test_customers_are_excluded_and_manual_suppliers_and_old_reports_are_preserved(domain):
    session, user = domain
    # Emulate the legacy extractor accepting a customer before the correction.
    seed(session, user, "A verified supplier")
    run = publish(session, user, 1, [invoice("An export customer", "US112233")])
    before = service.create_report(session, user, "before-exclusion-001")
    frozen = service.report_xlsx(session, user.scope_id, before["id"], "foreign")
    from app.persistence.business import BUSINESS_TABLES
    session.execute(BUSINESS_TABLES["501"].update().where(BUSINESS_TABLES["501"].c.processing_run_id == run.id).values(tipo_operacion="2"))
    for observation in session.scalars(select(SupplierObservation).where(SupplierObservation.run_id == run.id)):
        evidence = json.loads(observation.evidence_json)
        for record in evidence:
            if record["table"] == "501":
                record["values"]["tipo_operacion"] = "2"
        observation.evidence_json = json.dumps(evidence)
    session.flush()
    service.sync_active_history(session, user.scope_id, user.id)
    assert [s["name"] for s in service.list_suppliers(session, user.scope_id)] == ["A verified supplier"]
    assert len(list(session.scalars(select(Supplier)))) == 2  # Historical catalog is retained.
    assert service.report_xlsx(session, user.scope_id, before["id"], "foreign") == frozen
    later = service.create_report(session, user, "after-exclusion-001")
    assert later["foreignCount"] == 1


def test_sync_prepares_missing_pair_for_latest_existing_publication_and_is_idempotent(domain):
    session, user = domain
    run = publish(session, user, 1, [invoice("Precision Components Limited", "US112233")])
    assert service.monthly_report_state(session, user.scope_id, run.id)["status"] == "unavailable"
    service.sync_active_history(session, user.scope_id, user.id, schedule_missing_report=True)
    first = service.monthly_report_state(session, user.scope_id, run.id)
    assert first["status"] == "ready" and first["report"]["foreignCount"] == 1
    service.sync_active_history(session, user.scope_id, user.id, schedule_missing_report=True)
    assert service.monthly_report_state(session, user.scope_id, run.id)["report"]["id"] == first["report"]["id"]


def test_missing_optional_fields_leave_blank_cells_and_never_block_the_pair(domain):
    from io import BytesIO
    from openpyxl import load_workbook
    session, user = domain
    run = publish(session, user, 1, [invoice("Unknown new supplier", "", "", calle_proveedor="")])
    service.sync_active_history(session, user.scope_id, user.id, schedule_missing_report=True)
    state = service.monthly_report_state(session, user.scope_id, run.id)
    assert state["status"] == "ready" and state["pending"] == 0
    sheet = load_workbook(BytesIO(service.report_xlsx(session, user.scope_id, state["report"]["id"], "foreign"))).active
    assert sheet["A2"].value == "Unknown new supplier"
    assert sheet["D2"].value is None and sheet["E2"].value is None
    assert all(cell.fill.fgColor.rgb.endswith("FFFF00") for cell in sheet[2])


def test_confirmed_ptm_alias_uses_original_row_even_without_optional_invoice_fields(domain):
    session, user = domain
    seed(session, user, "PTM CORPORATION")
    publish(session, user, 1, [invoice("PTM-AEC", "", "", calle_proveedor="")])
    publish(session, user, 2, [invoice("PTM / AEC", "", "")])
    suppliers = service.list_suppliers(session, user.scope_id)
    assert len(suppliers) == 1 and suppliers[0]["name"] == "PTM CORPORATION"
    assert service.list_reviews(session, user.scope_id) == []


def test_507_never_adds_a_national_supplier_but_505_rfc_does_even_without_country(domain):
    session, user = domain
    publish(session, user, 1, [], [{"clave_caso": "V1", "identificador_caso": "ABC010101AB1", "complemento_caso": "CN"}])
    assert service.summary(session, user.scope_id)["national"] == 0
    publish(session, user, 2, [invoice("Proveedor nacional", "ABC010101AB1", "")])
    suppliers = service.list_suppliers(session, user.scope_id)
    assert len(suppliers) == 1 and suppliers[0]["kind"] == "national"
    assert suppliers[0]["taxId"] == "ABC010101AB1" and suppliers[0]["virtualOperations"] is True


def test_swiss_fiscal_ids_are_not_mistaken_for_mexican_rfcs(domain):
    session, user = domain
    publish(session, user, 1, [invoice("Swiss supplier", "CHE-103.592.307", ""),
                              invoice("Another Swiss supplier", "CHE-101772703", "")])
    assert service.summary(session, user.scope_id)["national"] == 0
    assert service.summary(session, user.scope_id)["foreign"] == 2


def test_plural_and_legal_suffix_variants_reuse_the_initial_name_and_country(domain):
    session, user = domain
    seed(session, user, "CARVEN CIRCUITS LTD", "HKG")
    publish(session, user, 1, [invoice("CARVEN CIRCUIT LIMITED", "91320282727423274", "USA")])
    suppliers = service.list_suppliers(session, user.scope_id)
    assert len(suppliers) == 1 and suppliers[0]["country"] == "HKG"


def test_same_foreign_vat_with_and_without_country_prefix_matches_the_identity(domain):
    session, user = domain
    publish(session, user, 1, [invoice("ATOP S.P.A.", "IT04492910486", "")])
    publish(session, user, 2, [invoice("IMA AUTOMATION", "04492910486", "")])
    assert len(service.list_suppliers(session, user.scope_id)) == 1


def test_refresh_is_idempotent_and_preserves_the_first_report_yellow_rows(domain):
    session, user = domain
    publish(session, user, 1, [invoice("A newly detected supplier", "US123456")])
    service.refresh_lists(session, user)
    first = service.list_reports(session, user.scope_id)[0]
    frozen = service.report_xlsx(session, user.scope_id, first["id"], "foreign")
    service.refresh_lists(session, user)
    assert len(service.list_reports(session, user.scope_id)) == 1
    assert service.report_xlsx(session, user.scope_id, first["id"], "foreign") == frozen


def test_country_can_be_learned_from_later_invoice_and_late_seed_import(domain):
    session, user = domain
    publish(session, user, 1, [invoice("JOHNSON ELECTRIC AUTOMOTIVO BRASIL LTDA", "", "")])
    publish(session, user, 2, [invoice("JOHNSON ELECTRIC AUTOMOTIVE BRASIL LTDA", "", "BRA")])
    assert len(service.list_suppliers(session, user.scope_id)) == 1
    seed(session, user, "JOHNSON ELECTRIC AUTOMOTIVO BRASIL LTDA", "BRA")
    suppliers = service.list_suppliers(session, user.scope_id)
    assert len(suppliers) == 1 and suppliers[0]["country"] == "BRA"
