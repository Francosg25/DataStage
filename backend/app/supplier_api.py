"""Scoped supplier catalog, review decisions and immutable paired reports."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.responses import Response
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.api import db_session
from app.modules.identity.auth import Principal, current_principal, require_reader
from app.modules.processing.service import audit, commit_or_conflict, validate_key
from app.modules.suppliers import service

router = APIRouter(prefix="/api/v1/suppliers", tags=["Suppliers"])
DB = Annotated[object, Depends(db_session)]
Reader = Annotated[Principal, Depends(require_reader)]
Identity = Annotated[Principal, Depends(current_principal)]
Kind = Literal["national", "foreign"]
Search = Annotated[str, Query(max_length=250)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SupplierFields(StrictModel):
    kind: Kind = Field(validation_alias=AliasChoices("kind", "type"))
    name: str = Field(min_length=1, max_length=512)
    taxId: str = Field(default="", max_length=100)
    country: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=1000)
    externalNumber: str = Field(default="", max_length=100)
    internalNumber: str = Field(default="", max_length=100)
    postalCode: str = Field(default="", max_length=30)
    municipality: str = Field(default="", max_length=200, validation_alias=AliasChoices("municipality", "city"))
    state: str = Field(default="", max_length=200)
    virtualConfirmation: bool | None = Field(default=None, strict=True)
    reason: str = Field(default="Actualización del catálogo", min_length=3, max_length=1000)


class SupplierEdit(SupplierFields):
    expectedVersion: int = Field(ge=0, strict=True)


class ReviewDecision(StrictModel):
    decision: Literal["same", "new"]
    supplierId: str | None = Field(default=None, max_length=36)
    virtualOperations: bool | None = Field(default=None, strict=True)
    expectedVersion: int = Field(ge=0, strict=True)
    reason: str = Field(default="Identidad confirmada", min_length=3, max_length=1000)
    supplier: SupplierFields | None = None


class EquivalenceEdit(StrictModel):
    supplierId: str | None = Field(default=None, max_length=36)
    active: bool = Field(default=True, strict=True)
    expectedVersion: int = Field(ge=0, strict=True)
    reason: str = Field(default="Corrección de equivalencia", min_length=3, max_length=1000)


class ReportRequest(StrictModel):
    label: str | None = Field(default=None, max_length=200)


def page(items, offset, limit):
    return {"items": items[offset:offset + limit], "total": len(items), "offset": offset, "limit": limit}


@router.get("/summary")
def summary(session: DB, principal: Reader):
    return service.summary(session, principal.scope_id)


@router.get("")
def catalog(session: DB, principal: Reader, search: Search = "", type: Kind | None = None,
            kind: Kind | None = None, offset: Offset = 0, limit: Limit = 50):
    return page(service.list_suppliers(session, principal.scope_id, search=search, kind=kind or type), offset, limit)


@router.get("/reviews")
def reviews(session: DB, principal: Reader, search: Search = "", type: Kind | None = None,
            offset: Offset = 0, limit: Limit = 50):
    items = service.list_reviews(session, principal.scope_id, search=search)
    if type:
        items = [item for item in items if item["candidate"].get("kind", item["candidate"].get("type")) == type]
    return page(items, offset, limit)


@router.get("/equivalences")
def equivalences(session: DB, principal: Reader, search: Search = "", type: Kind | None = None,
                 offset: Offset = 0, limit: Limit = 50):
    items = service.list_equivalences(session, principal.scope_id, search=search)
    if type:
        items = [item for item in items if item.get("candidate", {}).get("type") == type]
    return page(items, offset, limit)


@router.get("/reviews/{review_id}/evidence")
def review_evidence(review_id: str, session: DB, principal: Reader,
                    offset: Offset = 0, limit: Limit = 50):
    return service.get_review_evidence(session, principal.scope_id, review_id, offset=offset, limit=limit)


@router.get("/reports")
def reports(session: DB, principal: Reader, search: Search = "", offset: Offset = 0, limit: Limit = 50):
    items = service.list_reports(session, principal.scope_id)
    if search:
        items = [item for item in items if search.casefold() in str(item.get("label", "")).casefold()]
    return page(items, offset, limit)


@router.get("/report-requests")
def report_requests(session: DB, principal: Reader, offset: Offset = 0, limit: Limit = 50):
    return page(service.list_report_requests(session, principal.scope_id), offset, limit)


@router.get("/runs/{run_id}/report")
def monthly_supplier_report(run_id: str, session: DB, principal: Reader):
    return service.monthly_report_state(session, principal.scope_id, run_id)


@router.post("/sync")
def synchronize(session: DB, principal: Identity):
    principal.require("Operator")
    result = service.refresh_lists(session, principal)
    commit_or_conflict(session)
    return result


@router.post("/import")
async def import_lists(session: DB, principal: Identity,
                       national: Annotated[UploadFile, File()], foreign: Annotated[UploadFile, File()]):
    principal.require("Admin")
    from app.modules.suppliers.importer import MAX_BYTES, read_workbook
    payload = {"schemas": {**service.DEFAULT_SCHEMAS, "_templates": {}}}
    for kind, upload in (("national", national), ("foreign", foreign)):
        payload[kind], payload["schemas"]["_templates"][kind] = read_workbook(
            await upload.read(MAX_BYTES + 1), upload.filename or "", kind)
    service.initialize_seed(session, principal, payload, synchronize=False)
    result = service.refresh_lists(session, principal)
    commit_or_conflict(session)
    return result


@router.post("", status_code=201)
def create_supplier(body: SupplierFields, session: DB, principal: Identity):
    principal.require("Operator")
    result = service.create_supplier(session, principal, body.model_dump(exclude_unset=True))
    commit_or_conflict(session)
    return result


@router.patch("/{supplier_id}")
def edit_supplier(supplier_id: str, body: SupplierEdit, session: DB, principal: Identity):
    principal.require("Operator")
    values = body.model_dump(exclude_unset=True, exclude={"expectedVersion"})
    result = service.update_supplier(session, principal, supplier_id, values, body.expectedVersion)
    commit_or_conflict(session)
    return result


@router.post("/reviews/{review_id}/resolve")
def resolve_review(review_id: str, body: ReviewDecision, session: DB, principal: Identity):
    principal.require("Operator")
    result = service.resolve_review(session, principal, review_id, body.decision,
                                    supplier_id=body.supplierId, virtual_operations=body.virtualOperations,
                                    expected_version=body.expectedVersion, reason=body.reason,
                                    supplier_data=body.supplier.model_dump(exclude_unset=True) if body.supplier else None)
    commit_or_conflict(session)
    return result


@router.patch("/equivalences/{equivalence_id}")
def edit_equivalence(equivalence_id: str, body: EquivalenceEdit, session: DB, principal: Identity):
    principal.require("Operator")
    result = service.update_equivalence(session, principal, equivalence_id, body.supplierId,
                                        body.expectedVersion, active=body.active, reason=body.reason)
    commit_or_conflict(session)
    return result


@router.post("/reports", status_code=201)
def create_report(body: ReportRequest, session: DB, principal: Identity,
                  key: Annotated[str, Header(alias="Idempotency-Key")]):
    principal.require("Operator")
    validate_key(key)
    result = service.create_report(session, principal, key, label=body.label)
    commit_or_conflict(session)
    return result


@router.get("/reports/{report_id}/{kind}.xlsx")
def download_report(report_id: str, kind: Kind, session: DB, principal: Reader):
    content = service.report_xlsx(session, principal.scope_id, report_id, kind)
    audit(session, principal.scope_id, principal.id, "supplier.report.download", reportId=report_id, kind=kind)
    commit_or_conflict(session)
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="proveedores_{kind}_{report_id}.xlsx"'})


@router.get("/{supplier_id}")
def supplier_detail(supplier_id: str, session: DB, principal: Reader):
    return service.get_supplier(session, principal.scope_id, supplier_id)


@router.get("/{supplier_id}/evidence")
def supplier_evidence(supplier_id: str, session: DB, principal: Reader,
                      offset: Offset = 0, limit: Limit = 50):
    return service.get_supplier_evidence(session, principal.scope_id, supplier_id, offset=offset, limit=limit)
