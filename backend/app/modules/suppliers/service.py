"""Transactional supplier identity review and immutable, paired report snapshots.

Only 505 supplies a supplier's fiscal identity. A 501 RFC belongs to the
contributor; V1/IM in 507 is an IMMEX authorization, never a supplier RFC.
Mutators do not commit: publication, audit and catalog share the caller's unit
of work. A scope row serializes decisions and report creation across workers.
"""
from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
from io import BytesIO
import json
import re
import unicodedata
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.modules.engine import parse_period
from app.modules.processing.service import audit, json_text, validate_key
from app.persistence.business import BUSINESS_TABLES, column_name
from app.persistence.models import Period, Run
from app.persistence.suppliers import (
    Supplier, SupplierEquivalence, SupplierObservation, SupplierReport, SupplierReportRequest, SupplierScope,
)


DEFAULT_SCHEMAS = {
    "national": ["RFC", "Operaciones virtuales", "Estatus"],
    "foreign": ["Nombre o Razón social", "Apellido Paterno", "Apellido Materno", "País ",
                "Domicilio", "Cliente/Proveedor", "Estatus"],
}
RFC = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
COUNTRIES = {
    "China (República Popular)": "CHN", "Estados Unidos de América": "USA", "Italia (República Italiana)": "ITA",
    "Hong Kong (Región Administrativa Especial de la República)": "HKG", "Japón": "JPN",
    "Alemania (República Federal de)": "DEU", "República de Serbia": "SRB", "Brasil (República Federativa de)": "BRA",
    "India (República de)": "IND", "Suiza (Confederación)": "CHE", "Canadá": "CAN", "Malasia": "MYS",
    "Francia (República Francesa)": "FRA", "Costa Rica (República de)": "CRI",
    "Corea (República de) (Corea del Sur)": "KOR", "Hungría (República de)": "HUN", "Reino Unido": "GBR",
    "Argentina (República Argentina)": "ARG", "Mexico": "MEX", "MX": "MEX", "484": "MEX",
    "United States": "USA", "US": "USA", "China": "CHN", "CN": "CHN",
}
FIELDS = ("name", "taxId", "country", "address", "externalNumber", "internalNumber", "postalCode", "city", "state")


def normalized(value):
    """Punctuation, accents, spacing and case are presentation, not identity."""
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper())


def fiscal(value):
    value = re.sub(r"[^A-Z0-9Ñ&]", "", str(value or "").upper())
    return "" if normalized(value) in {"NA", "NONE", "NULL", "SINDATO", "NOAPLICA", "USA", "MEX", "CHN",
                                        "XEXX010101000", "XAXX010101000"} else value


def _hash(value):
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def _iso(value):
    return value.isoformat() + "Z" if value else None


def _error(code, detail, status=409):
    raise ApplicationError(status, code, detail)


def ensure_initialized(session, scope, actor="system"):
    """Create an empty scoped catalog; importing a personal seed is explicit."""
    state = session.get(SupplierScope, scope)
    if state is None:
        try:
            with session.begin_nested():
                state = SupplierScope(scope_id=scope, schemas_json=json_text(DEFAULT_SCHEMAS))
                session.add(state)
                session.flush()
        except IntegrityError:
            # Two first publications can initialize the same scope together.
            # Roll back only this savepoint and use the winning scope row.
            state = session.get(SupplierScope, scope)
            if state is None:
                raise
        else:
            audit(session, scope, actor, "suppliers.initialized")
    return state


def _lock(session, scope, actor="system"):
    state = ensure_initialized(session, scope, actor)
    # UPDATE locks a SQL Server scope row until commit; it also acquires SQLite's
    # write lock before reading any mutable catalog/report state.
    session.execute(update(SupplierScope).where(SupplierScope.scope_id == scope)
                    .values(version=SupplierScope.version + 1))
    session.refresh(state)
    return state


def _scoped(session, model, object_id, scope):
    item = session.get(model, object_id)
    if item is None or item.scope_id != scope:
        _error("SUPPLIER_NOT_FOUND", "No se encontró el registro de proveedores", 404)
    return item


def _expected(item, expected):
    if expected is None or item.version != expected:
        _error("VERSION_CONFLICT", "El registro cambió; actualiza antes de guardar")


def _data(raw, *, existing=None, validate=True):
    data = {**(existing or {}), **raw}
    data["type"] = data.get("type", data.get("kind", "foreign"))
    if "kind" in raw and "type" not in raw:
        data["type"] = raw["kind"]
    if "virtualConfirmation" in raw:
        data["virtualOperations"] = raw["virtualConfirmation"]
    if data["type"] not in ("national", "foreign"):
        _error("INVALID_SUPPLIER_TYPE", "Selecciona un proveedor nacional o extranjero", 400)
    if "municipality" in raw and "city" not in raw:
        data["city"] = raw["municipality"]
    for field in FIELDS:
        data[field] = str(data.get(field) or "").strip()
        if len(data[field]) > (512 if field == "name" else 100 if field in {"taxId", "country"} else 4000):
            _error("SUPPLIER_FIELD_TOO_LONG", "Un dato del proveedor excede el límite", 400)
    data["taxId"] = fiscal(data["taxId"])
    data["country"] = _country(data["country"])
    if not data["name"] and data["type"] == "national":
        data["name"] = data["taxId"]
    if validate and not data["name"]:
        _error("SUPPLIER_NAME_REQUIRED", "Escribe el nombre del proveedor", 400)
    if validate and data["type"] == "national" and not RFC.fullmatch(data["taxId"]):
        _error("INVALID_SUPPLIER_RFC", "El RFC del proveedor nacional no es válido", 400)
    if data["type"] == "national" and not data["country"]:
        data["country"] = "MEX"
    virtual = data.get("virtualOperations")
    if virtual is not None and type(virtual) is not bool:
        _error("INVALID_VIRTUAL_CONFIRMATION", "Confirma Sí o No para operaciones virtuales", 400)
    return data


def _identity(data):
    return _hash({"type": data["type"], "name": normalized(data["name"]),
                  "taxId": fiscal(data["taxId"]), "country": normalized(data["country"]),
                  **{k: normalized(data.get(k)) for k in ("address", "externalNumber", "internalNumber", "postalCode", "city", "state")}})


def _supplier_data(item):
    return {**json.loads(item.data_json), "type": item.kind, "name": item.name,
            "taxId": item.tax_id, "country": item.country}


def _observations(session, scope, supplier_id=None, active=None):
    query = select(SupplierObservation).where(SupplierObservation.scope_id == scope)
    if supplier_id is not None:
        query = query.where(SupplierObservation.supplier_id == supplier_id)
    if active is not None:
        query = query.where(SupplierObservation.active == int(active))
    return list(session.scalars(query.order_by(SupplierObservation.created_at, SupplierObservation.id)))


def _virtual(item, observations):
    if item.virtual_confirmation == 1 or any(o.active and o.virtual_confirmed for o in observations):
        return True
    return False if item.virtual_confirmation == 0 else None


def supplier_response(session, item, *, evidence=False):
    count, virtual_support = session.execute(select(func.count(), func.max(SupplierObservation.virtual_confirmed))
        .where(SupplierObservation.scope_id == item.scope_id, SupplierObservation.supplier_id == item.id,
               SupplierObservation.active == 1)).one()
    data = _supplier_data(item)
    virtual = True if item.virtual_confirmation == 1 or virtual_support else False if item.virtual_confirmation == 0 else None
    result = {**data, "id": item.id, "kind": item.kind, "municipality": data.get("city", ""),
              "version": item.version, "virtualOperations": virtual,
              "virtualConfirmation": None if item.virtual_confirmation is None else bool(item.virtual_confirmation),
              "originalStatus": item.original_status, "evidenceCount": count,
              "createdAt": _iso(item.created_at), "updatedAt": _iso(item.updated_at)}
    if evidence:
        page = get_supplier_evidence(session, item.scope_id, item.id, limit=20)
        result["evidence"] = page["items"]
        result["evidenceTotal"] = page["total"]
        result["evidenceHasMore"] = page["total"] > len(page["items"])
    return result


def _seed_evidence(item):
    data = _supplier_data(item)
    if not data.get("seedEvidence"):
        return None
    return {"id": "seed:" + item.id, "period": "Inicialización", "sourceKind": "seed", "active": True,
            "virtualConfirmed": item.virtual_confirmation == 1,
            "records": [{"table": "seed", "values": data.get("originalRow", {}),
                         "fileName": data["seedEvidence"].get("file"),
                         "rowNumber": data["seedEvidence"].get("row"), "source": data["seedEvidence"]}]}


def get_supplier_evidence(session, scope, supplier_id, offset=0, limit=100):
    item = _scoped(session, Supplier, supplier_id, scope)
    seed = _seed_evidence(item)
    condition = (SupplierObservation.scope_id == scope, SupplierObservation.supplier_id == supplier_id)
    total = session.scalar(select(func.count()).select_from(SupplierObservation).where(*condition)) + bool(seed)
    result = [seed] if seed and offset == 0 else []
    rows = session.scalars(select(SupplierObservation).where(*condition)
        .order_by(SupplierObservation.created_at, SupplierObservation.id)
        .offset(max(0, offset - bool(seed))).limit(max(0, limit - len(result))))
    result.extend(_evidence_response(o) for o in rows)
    return {"items": result, "total": total, "offset": offset, "limit": limit}


def _evidence_response(observation):
    return {"id": observation.id, "runId": observation.run_id, "periodId": observation.period_id,
            "sourceKind": "baseline" if observation.source_kind.startswith("baseline") else observation.source_kind,
            "period": observation.period_name, "active": bool(observation.active),
            "virtualConfirmed": bool(observation.virtual_confirmed),
            "records": json.loads(observation.evidence_json)}


def get_supplier(session, scope, supplier_id):
    return supplier_response(session, _scoped(session, Supplier, supplier_id, scope), evidence=True)


def list_suppliers(session, scope, search="", kind=None):
    key = normalized(search)
    items = list(session.scalars(select(Supplier).where(Supplier.scope_id == scope).order_by(Supplier.name, Supplier.id)))
    return [supplier_response(session, item) for item in items
            if (not kind or item.kind == kind) and (not key or key in normalized(item.name + item.tax_id + item.country))]


def _new_supplier(session, scope, data, actor, *, original_status=None, manual=False, reason=""):
    confirmation = data.get("virtualOperations")
    if manual and data["type"] == "national" and confirmation is None:
        _error("VIRTUAL_CONFIRMATION_REQUIRED", "Confirma Sí o No para operaciones virtuales", 400)
    item = Supplier(id=str(uuid4()), scope_id=scope, kind=data["type"], name=data["name"],
                    name_key=normalized(data["name"]), tax_id=data["taxId"], country=data["country"],
                    data_json=json_text(data), original_status=original_status,
                    virtual_confirmation=int(confirmation) if confirmation is not None else None,
                    virtual_reason=reason or None)
    session.add(item)
    session.flush()
    audit(session, scope, actor, "supplier.created", supplierId=item.id, reason=reason,
          originalStatus=original_status, data=data)
    return item


def _exact(items, data):
    candidates = []
    for item in items:
        if item.kind != data["type"]:
            continue
        tax_match = data["taxId"] and item.tax_id and fiscal(data["taxId"]) == fiscal(item.tax_id)
        name_match = normalized(data["name"]) == item.name_key
        country_match = normalized(data["country"]) == normalized(item.country)
        conflict = bool((item.tax_id and data["taxId"] and not tax_match)
                        or (item.country and data["country"] and not country_match))
        if (tax_match or name_match) and not conflict:
            candidates.append(item)
    return candidates


def _similar(items, data):
    result = []
    name = normalized(data["name"])
    for item in items:
        if item.kind != data["type"]:
            continue
        same_tax = bool(item.tax_id and data["taxId"] and fiscal(item.tax_id) == fiscal(data["taxId"]))
        ratio = SequenceMatcher(None, item.name_key, name).ratio() if min(len(item.name_key), len(name)) > 4 else 0
        # Never fuzzy-match RFCs when the national template has no supplier name.
        if RFC.fullmatch(item.name.upper()) or RFC.fullmatch(data["name"].upper()):
            ratio = 0
        if same_tax or ratio >= .86:
            result.append(item)
    return result


def _alias(session, scope, identity_key):
    return session.scalar(select(SupplierEquivalence).where(
        SupplierEquivalence.scope_id == scope, SupplierEquivalence.identity_key == identity_key))


def _remember(session, scope, data, supplier, decision, reason):
    key = _identity(data)
    alias = _alias(session, scope, key)
    if alias is None:
        alias = SupplierEquivalence(scope_id=scope, identity_key=key, identity_json=json_text(data),
                                    supplier_id=supplier.id, decision=decision, reason=reason)
        session.add(alias)
    else:
        alias.supplier_id, alias.active, alias.decision = supplier.id, 1, decision
        alias.reason, alias.version = reason, alias.version + 1
    session.flush()
    return alias


def create_supplier(session, principal, data):
    principal.require("Operator")
    _lock(session, principal.scope_id, principal.id)
    data = _data(data)
    items = list(session.scalars(select(Supplier).where(Supplier.scope_id == principal.scope_id)))
    if _exact(items, data):
        _error("SUPPLIER_ALREADY_EXISTS", "El proveedor ya existe en el catálogo")
    item = _new_supplier(session, principal.scope_id, data, principal.id, manual=True, reason=data.get("reason", ""))
    _remember(session, principal.scope_id, data, item, "new", data.get("reason", ""))
    finalize_ready_monthly_reports(session, principal.scope_id, principal.id)
    return supplier_response(session, item, evidence=True)


def update_supplier(session, principal, supplier_id, data, expected_version):
    principal.require("Operator")
    _lock(session, principal.scope_id, principal.id)
    item = _scoped(session, Supplier, supplier_id, principal.scope_id)
    _expected(item, expected_version)
    before = _supplier_data(item)
    updated = _data(data, existing=before)
    if updated["type"] != item.kind:
        _error("SUPPLIER_TYPE_IMMUTABLE", "El tipo de proveedor no puede cambiar")
    others = list(session.scalars(select(Supplier).where(Supplier.scope_id == principal.scope_id, Supplier.id != item.id)))
    if _exact(others, updated):
        _error("SUPPLIER_ALREADY_EXISTS", "Los datos identifican a otro proveedor del catálogo")
    item.name, item.name_key, item.tax_id, item.country = updated["name"], normalized(updated["name"]), updated["taxId"], updated["country"]
    item.data_json = json_text(updated)
    if "virtualOperations" in data or "virtualConfirmation" in data:
        value = data.get("virtualConfirmation", data.get("virtualOperations"))
        item.virtual_confirmation = None if value is None else int(value)
        item.virtual_reason = data.get("reason", "")
    item.version += 1
    session.flush()
    audit(session, principal.scope_id, principal.id, "supplier.updated", supplierId=item.id,
          before=before, after=updated, reason=data.get("reason", ""))
    finalize_ready_monthly_reports(session, principal.scope_id, principal.id)
    return supplier_response(session, item, evidence=True)


def _record(row, code):
    return {"table": code, "rowId": row["id"], "fileId": row.get("processing_file_id"),
            "fileName": row.get("archivo_origen"), "rowNumber": row.get("source_row_number"),
            "pedimento": row.get("pedimento_completo"),
            "source": row.get("source"),
            "values": {k: v for k, v in row.items() if k not in {"original_dates_json", "ingested_at"}}}


def _operation_key(row):
    complete = normalized(row.get("pedimento_completo"))
    if complete:
        return ("complete", complete)
    parts = tuple(normalized(row.get(k)) for k in ("patente", "pedimento", "seccion_aduanera"))
    return ("parts", *parts) if all(parts) else None


def _operation_keys(row):
    keys = []
    complete = normalized(row.get("pedimento_completo"))
    if complete:
        keys.append(("complete", complete))
    parts = tuple(normalized(row.get(k)).lstrip("0") or ("0" if normalized(row.get(k)) else "")
                  for k in ("patente", "pedimento", "seccion_aduanera"))
    if all(parts):
        keys.append(("parts", *parts))
    return keys


def _join_operation(index, row):
    keys = _operation_keys(row)
    if keys and keys[0][0] == "complete" and keys[0] in index:
        return index[keys[0]]
    # Composite fallback is safe only if no contradictory complete identifier
    # is present. All joins are additionally isolated by monthly run/period.
    found = []
    for key in keys:
        for candidate in index.get(key, []):
            a, b = normalized(row.get("pedimento_completo")), normalized(candidate.get("pedimento_completo"))
            if a and b and a != b:
                continue
            if candidate not in found:
                found.append(candidate)
    return found


@lru_cache(maxsize=256)
def _country(value):
    value = str(value or "").strip().upper()
    return {normalized(k): v for k, v in COUNTRIES.items()}.get(normalized(value), value)


def _rows_for_run(session, run_id, period_id):
    rows = {}
    for code in ("501", "505", "507"):
        table = BUSINESS_TABLES[code]
        rows[code] = [dict(row) for row in session.execute(select(table).where(
            table.c.processing_run_id == run_id, table.c.period_id == period_id)).mappings()]
    return rows


def _extract_run(session, run, period):
    """Join only records of this monthly run and the same complete operation."""
    return _extract_rows(_rows_for_run(session, run.id, period.id))


def _extract_rows(rows):
    joined = {code: {} for code in ("501", "507")}
    for code in joined:
        for row in rows[code]:
            for key in _operation_keys(row):
                joined[code].setdefault(key, []).append(row)
    for row in rows["505"]:
        headers = _join_operation(joined["501"], row)
        identifiers = _join_operation(joined["507"], row)
        country = _country(row.get("pais_facturacion"))
        tax_id = fiscal(row.get("indent_fiscal_proveedor"))
        contributor_rfcs = {fiscal(h.get("rfc")) for h in headers if h.get("rfc")}
        invalid_identity = tax_id in contributor_rfcs if tax_id else False
        data = _data({"type": "national" if country == "MEX" else "foreign",
                      "name": row.get("proveedor_mercancia"), "taxId": tax_id,
                      "country": country, "address": row.get("calle_proveedor"),
                      "externalNumber": row.get("num_exterior_proveedor"),
                      "internalNumber": row.get("num_interior_proveedor"),
                      "postalCode": row.get("cp_proveedor"), "city": row.get("municipio_proveedor"),
                      "state": row.get("entidad_fed_facturacion")}, validate=False)
        evidence = [_record(row, "505")] + [_record(h, "501") for h in headers] + [_record(i, "507") for i in identifiers]
        virtual = False
        for identifier in identifiers:
            # V1 identifies a virtual transfer. IM is an authorization number.
            # CN explicitly carries the counterparty RFC in IdentificadorCaso.
            if not headers:
                continue
            counterpart = _virtual_counterpart(identifier)
            if counterpart and counterpart == tax_id and counterpart not in contributor_rfcs:
                virtual = True
        if invalid_identity:
            # Display the contradictory source, but never promote contributor RFC
            # into a supplier's fiscal identity automatically.
            data["taxId"] = ""
            data["identityConflict"] = "contributor_rfc"
        missing = not data["name"] or not country or (data["type"] == "national" and not RFC.fullmatch(data["taxId"]))
        yield row, data, evidence, virtual, "missing_identity" if missing or invalid_identity else ""


def _assign(session, scope, observation, items, cache=None, confirmed_rfcs=frozenset()):
    key = (observation.identity_key, bool(observation.virtual_confirmed))
    cached = cache.get(key) if cache is not None else None
    if cached and cached[0] == len(items):
        observation.supplier_id, observation.status, observation.reason, observation.suggestions_json = cached[1:]
        return
    _assign_uncached(session, scope, observation, items, confirmed_rfcs)
    if cache is not None:
        cache[key] = (len(items), observation.supplier_id, observation.status, observation.reason,
                      observation.suggestions_json or "[]")


def _assign_uncached(session, scope, observation, items, confirmed_rfcs):
    data = json.loads(observation.candidate_json)
    alias = _alias(session, scope, observation.identity_key)
    if alias is not None and alias.active:
        target = _scoped(session, Supplier, alias.supplier_id, scope)
        observation.supplier_id, observation.status, observation.reason = target.id, "resolved", ""
        return
    # A revoked decision must return to review even when the canonical name
    # matches; otherwise revocation would silently recreate the old decision.
    if alias is not None and not alias.active:
        observation.status, observation.reason = "pending", "equivalence_revoked"
        observation.suggestions_json = json_text([alias.supplier_id])
        return
    matches = _exact(items, data)
    suggestions = _similar(items, data)
    if observation.reason == "missing_identity":
        observation.suggestions_json = json_text([s.id for s in suggestions])
        return
    if len(matches) == 1:
        target = matches[0]
        # Same fiscal identity but materially different name is reviewable.
        canonical_rfc_name = bool(RFC.fullmatch(target.name.upper()))
        address_conflict = _contradictory_data(_supplier_data(target), data)
        if (target.name_key != normalized(data["name"]) and not canonical_rfc_name) or address_conflict:
            observation.reason = "conflicting_data"
        else:
            observation.supplier_id, observation.status, observation.reason = target.id, "resolved", ""
            return
    elif suggestions or len(matches) > 1:
        observation.reason = "conflicting_data" if any(s.name_key == normalized(data["name"]) for s in suggestions) else "similar_name"
    elif data["type"] == "national" and not observation.virtual_confirmed and data["taxId"] not in confirmed_rfcs:
        observation.reason = "virtual_confirmation"
    else:
        target = _new_supplier(session, scope, data, "worker")
        items.append(target)
        observation.supplier_id, observation.status, observation.reason = target.id, "resolved", ""
        return
    observation.suggestions_json = json_text([s.id for s in (suggestions or matches)])


def _contradictory_data(left, right):
    for field in ("address", "externalNumber", "internalNumber", "postalCode", "city", "state"):
        a, b = normalized(left.get(field)), normalized(right.get(field))
        if a and b and a != b:
            # Template addresses combine street, city and postal code; a street
            # present as an exact substring is consistent with that full address.
            if field == "address" and (a in b or b in a):
                continue
            return True
    return False


def _add_counterparty_evidence(session, scope, run_id, period_id, period_name, rows, items, by_source,
                               source_kind="monthly"):
    """A 507 CN RFC may corroborate an existing supplier without creating one.

    Virtual pedimentos frequently have no 505 invoice. Their counterpart still
    corroborates an already identified RFC after a strict join to 501.
    """
    headers = {}
    for row in rows["501"]:
        for key in _operation_keys(row):
            headers.setdefault(key, []).append(row)
    added = 0
    for identifier in rows["507"]:
        rfc = _virtual_counterpart(identifier)
        joined = _join_operation(headers, identifier)
        if not RFC.fullmatch(rfc) or not joined or rfc in {fiscal(h.get("rfc")) for h in joined}:
            continue
        matches = [i for i in items if i.kind == "national" and i.tax_id == rfc]
        if len(matches) > 1:
            continue
        source = (run_id, "507:" + str(identifier["id"]))
        if source in by_source:
            existing = by_source[source]
            if not existing.supplier_id and len(matches) == 1:
                existing.supplier_id, existing.status = matches[0].id, "resolved"
                existing.version += 1
            continue
        target = matches[0] if matches else None
        # Unmatched counterparty evidence is retained without creating a
        # supplier. A later 505 can identify it and inherit the live support.
        data = _data({"type": "national", "name": "", "taxId": rfc, "country": "MEX"}, validate=False)
        data["name"] = ""
        observation = SupplierObservation(id=str(uuid4()), scope_id=scope, run_id=run_id, source_kind=source_kind,
            period_id=period_id, period_name=period_name, source_row_id=source[1], identity_key=_identity(data),
            candidate_json=json_text(data), evidence_json=json_text([_record(identifier, "507")] + [_record(h, "501") for h in joined]),
            supplier_id=target.id if target else None, status="resolved" if target else "evidence", reason="",
            active=1, virtual_confirmed=1, version=1)
        session.add(observation)
        by_source[source] = observation
        added += 1
    return added


def _confirmed_rfcs(observations):
    result = set()
    for observation in observations:
        if observation.active and observation.virtual_confirmed:
            data = json.loads(observation.candidate_json)
            if data.get("type") == "national" and RFC.fullmatch(data.get("taxId", "")):
                result.add(data["taxId"])
    return result


def _link_unmatched_evidence(observations, items):
    for observation in observations:
        if observation.status != "evidence" or observation.supplier_id:
            continue
        data = json.loads(observation.candidate_json)
        matches = [i for i in items if i.kind == "national" and i.tax_id == data.get("taxId")]
        if len(matches) == 1:
            observation.supplier_id, observation.status = matches[0].id, "resolved"
            observation.version += 1


def _resolve_supported_pending(session, scope, items, confirmed_rfcs):
    # Newly arrived independent virtual evidence can complete an older national
    # alta that was waiting only for the Yes/No confirmation.
    for observation in _observations(session, scope, active=True):
        if observation.status == "pending" and observation.reason == "virtual_confirmation":
            _assign(session, scope, observation, items, confirmed_rfcs=confirmed_rfcs)


def _virtual_counterpart(identifier):
    """Anexo 22 appendix 8: distinguish RFC modes from IM/AE authorizations.

    V3 direction-dependent complements and V4/V7 authorizations deliberately do
    not identify suppliers. The RFC must still join to an identified supplier.
    """
    code = normalized(identifier.get("clave_caso"))
    mode = normalized(identifier.get("complemento_caso"))
    supported = ((code == "V1" and mode in {"CN", "RFE", "V2"})
                 or (code in {"V2", "V8", "V5", "V6"} and not mode))
    rfc = fiscal(identifier.get("identificador_caso"))
    return rfc if supported and RFC.fullmatch(rfc) else ""


def _period_key(name):
    try:
        year, month, _ = parse_period(name)
        return year, month
    except ValueError:
        return normalized(name)


def ingest_baseline(session, principal, payload):
    """Explicitly import the user's historical workbook as supplier evidence.

    This creates neither fake monthly processing runs nor business rows. Its
    provenance includes the source hash, sheet and row and stays independent
    from later monthly replacements. Reimporting the same source is harmless.
    """
    principal.require("Admin")
    _lock(session, principal.scope_id, principal.id)
    baseline = payload.get("baseline", payload)
    raw_tables = baseline.get("tables", {})
    source_info = baseline.get("source", {})
    source_hash = source_info.get("sha256") or _hash(raw_tables)
    run_id = str(uuid5(NAMESPACE_URL, "supplier-baseline:" + principal.scope_id + ":" + source_hash))
    groups = {}
    for code in ("501", "505", "507"):
        for index, raw in enumerate(raw_tables.get(code, [])):
            row = {column_name(k): v for k, v in raw.items() if k != "source"}
            source = {**source_info, **raw.get("source", {})}
            row.update(id=str(index + 1), source=source,
                       archivo_origen=row.get("archivo_origen", source.get("file", "")),
                       source_row_number=source.get("row", index + 2))
            period_name = str(row.get("periodo") or "Histórico inicial")
            groups.setdefault(period_name, {"501": [], "505": [], "507": []})[code].append(row)
    existing = _observations(session, principal.scope_id)
    by_source = {(o.run_id, o.source_row_id): o for o in existing}
    items = list(session.scalars(select(Supplier).where(Supplier.scope_id == principal.scope_id)))
    assignment_cache = {}
    added = 0
    for period_name, rows in groups.items():
        period_id = str(uuid5(NAMESPACE_URL, run_id + ":" + period_name))
        added += _add_counterparty_evidence(session, principal.scope_id, run_id, period_id, period_name,
                    rows, items, by_source, source_kind="baseline")
    confirmed_rfcs = _confirmed_rfcs(by_source.values())
    for period_name, rows in groups.items():
        period_id = str(uuid5(NAMESPACE_URL, run_id + ":" + period_name))
        for row, data, evidence, virtual, reason in _extract_rows(rows):
            source = (run_id, str(row["id"]))
            if source in by_source:
                continue
            observation = SupplierObservation(id=str(uuid4()), scope_id=principal.scope_id, run_id=run_id,
                source_kind="baseline", period_id=period_id, period_name=period_name, source_row_id=source[1],
                identity_key=_identity(data), candidate_json=json_text(data), evidence_json=json_text(evidence),
                virtual_confirmed=int(virtual), reason=reason, status="pending", active=1, version=1)
            session.add(observation)
            _assign(session, principal.scope_id, observation, items, assignment_cache, confirmed_rfcs)
            by_source[source] = observation
            added += 1
        added += _add_counterparty_evidence(session, principal.scope_id, run_id, period_id, period_name,
                    rows, items, by_source, source_kind="baseline")
    session.flush()
    _link_unmatched_evidence(by_source.values(), items)
    session.flush()
    audit(session, principal.scope_id, principal.id, "suppliers.baseline_imported", source=source_info,
          observations=added, baselineId=run_id)
    return sync_active_history(session, principal.scope_id, principal.id)


import_baseline = ingest_baseline


def sync_active_history(session, scope, actor="system"):
    """Detect unseen 505 rows and retire evidence from replaced/deleted months."""
    _lock(session, scope, actor)
    active = list(session.execute(select(Run, Period).join(Period, Period.active_run_id == Run.id)
                  .where(Run.scope_id == scope, Period.scope_id == scope, Run.kind == "monthly",
                         Run.publication_status == "published").order_by(Period.year, Period.month)).all())
    active_ids = {run.id for run, _ in active}
    active_months = {_period_key(period.name) for _, period in active}
    existing = _observations(session, scope)
    for observation in existing:
        if observation.source_kind == "baseline":
            if _period_key(observation.period_name) in active_months:
                observation.source_kind, observation.active = "baseline_retired", 0
        elif observation.source_kind == "baseline_retired":
            observation.active = 0
        else:
            observation.active = int(observation.run_id in active_ids)
    by_source = {(o.run_id, o.source_row_id): o for o in existing}
    items = list(session.scalars(select(Supplier).where(Supplier.scope_id == scope)))
    assignment_cache = {}
    added = 0
    work = [(run, period, _rows_for_run(session, run.id, period.id)) for run, period in active]
    for run, period, rows in work:
        added += _add_counterparty_evidence(session, scope, run.id, period.id, period.name,
                                             rows, items, by_source)
    confirmed_rfcs = _confirmed_rfcs(by_source.values())
    for run, period, rows in work:
        for row, data, evidence, virtual, reason in _extract_rows(rows):
            source = (run.id, str(row["id"]))
            if source in by_source:
                continue
            observation = SupplierObservation(id=str(uuid4()), scope_id=scope, run_id=run.id,
                period_id=period.id, period_name=period.name, source_row_id=str(row["id"]),
                identity_key=_identity(data), candidate_json=json_text(data), evidence_json=json_text(evidence),
                virtual_confirmed=int(virtual), reason=reason)
            session.add(observation)
            # Defaults apply on INSERT; make pending status explicit before assigning.
            observation.status, observation.active, observation.version = "pending", 1, 1
            _assign(session, scope, observation, items, assignment_cache, confirmed_rfcs)
            by_source[source] = observation
            added += 1
    for run, period, rows in work:
        _add_counterparty_evidence(session, scope, run.id, period.id, period.name, rows, items, by_source)
    _link_unmatched_evidence(by_source.values(), items)
    session.flush()
    _resolve_supported_pending(session, scope, items, confirmed_rfcs)
    _link_unmatched_evidence(by_source.values(), items)
    session.flush()
    if added:
        audit(session, scope, actor, "suppliers.detected", observations=added, activeRuns=sorted(active_ids))
    finalize_ready_monthly_reports(session, scope, actor)
    return summary(session, scope)


def retire_runs(session, scope, run_ids, actor="system"):
    """Preserve catalog, evidence and reports while removing obsolete live evidence."""
    _lock(session, scope, actor)
    session.execute(update(SupplierObservation).where(SupplierObservation.scope_id == scope,
                    SupplierObservation.run_id.in_(run_ids)).values(active=0))
    audit(session, scope, actor, "suppliers.sources_retired", runIds=list(run_ids))
    session.flush()
    finalize_ready_monthly_reports(session, scope, actor)


def review_response(session, observation):
    suggestions = []
    for supplier_id in json.loads(observation.suggestions_json):
        item = session.get(Supplier, supplier_id)
        if item is not None and item.scope_id == observation.scope_id:
            suggestions.append(supplier_response(session, item))
    candidate = json.loads(observation.candidate_json)
    candidate.update(kind=candidate["type"], municipality=candidate.get("city", ""))
    return {"id": observation.id, "version": observation.version, "reason": observation.reason,
            "candidate": candidate, "suggestions": suggestions,
            "evidence": [_evidence_response(observation)], "runId": observation.run_id,
            "period": observation.period_name, "virtualConfirmed": bool(observation.virtual_confirmed)}


def list_reviews(session, scope, search=""):
    key = normalized(search)
    groups = {}
    for observation in _observations(session, scope, active=True):
        if observation.status == "pending" and (not key or key in normalized(observation.candidate_json + observation.period_name)):
            groups.setdefault(observation.identity_key, []).append(observation)
    results = []
    for observations in groups.values():
        result = review_response(session, observations[0])
        result["evidenceCount"] = len(observations)
        result["evidence"] = [_evidence_response(o) for o in observations[:20]]
        result["evidenceHasMore"] = len(observations) > 20
        results.append(result)
    return results


def get_review_evidence(session, scope, review_id, offset=0, limit=100):
    item = _scoped(session, SupplierObservation, review_id, scope)
    observations = [o for o in _observations(session, scope, active=True) if o.identity_key == item.identity_key]
    return {"items": [_evidence_response(o) for o in observations[offset:offset + limit]],
            "total": len(observations), "offset": offset, "limit": limit}


def resolve_review(session, principal, review_id, decision, supplier_id=None,
                   virtual_operations=None, expected_version=None, reason="", data=None, supplier_data=None):
    principal.require("Operator")
    _lock(session, principal.scope_id, principal.id)
    observation = _scoped(session, SupplierObservation, review_id, principal.scope_id)
    _expected(observation, expected_version)
    required_ids = _pending_request_observation_ids(session, principal.scope_id)
    if (not observation.active and observation.id not in required_ids) or observation.status != "pending":
        _error("REVIEW_NOT_PENDING", "La revisión ya no está pendiente")
    if decision not in {"same", "new"}:
        _error("INVALID_SUPPLIER_DECISION", "Selecciona si es el mismo proveedor o uno nuevo", 400)
    candidate = json.loads(observation.candidate_json)
    if decision == "same":
        if not supplier_id:
            _error("SUPPLIER_REQUIRED", "Selecciona el proveedor existente", 400)
        item = _scoped(session, Supplier, supplier_id, principal.scope_id)
        # A 505 country can contradict its foreign fiscal ID/address. Explicit
        # identity confirmation can correct this provisional classification.
    else:
        candidate = _data(supplier_data or data or {}, existing=candidate)
        if candidate["type"] == "national" and not observation.virtual_confirmed and virtual_operations is None:
            _error("VIRTUAL_CONFIRMATION_REQUIRED", "Confirma Sí o No para operaciones virtuales", 400)
        candidate["virtualOperations"] = virtual_operations
        items = list(session.scalars(select(Supplier).where(Supplier.scope_id == principal.scope_id)))
        # Explicit "new" is the user's durable distinction between namesakes;
        # identical tax IDs however identify the same legal supplier.
        if candidate["taxId"] and any(i.kind == candidate["type"] and i.tax_id == candidate["taxId"]
                                      and i.country == candidate["country"] for i in items):
            _error("SUPPLIER_ALREADY_EXISTS", "El identificador fiscal ya existe; selecciona el mismo proveedor")
        item = _new_supplier(session, principal.scope_id, candidate, principal.id, reason=reason)
    if virtual_operations is not None:
        if type(virtual_operations) is not bool:
            _error("INVALID_VIRTUAL_CONFIRMATION", "Confirma Sí o No para operaciones virtuales", 400)
        item.virtual_confirmation, item.virtual_reason = int(virtual_operations), reason
        item.version += 1
    original_candidate = json.loads(observation.candidate_json)
    alias = _remember(session, principal.scope_id, original_candidate, item, decision, reason)
    for other in _observations(session, principal.scope_id):
        if other.identity_key == observation.identity_key:
            other.supplier_id, other.status, other.reason = item.id, "resolved", ""
            other.version += 1
    session.flush()
    audit(session, principal.scope_id, principal.id, "supplier.review_resolved", reviewId=review_id,
          supplierId=item.id, decision=decision, equivalenceId=alias.id, reason=reason,
          virtualOperations=virtual_operations)
    finalize_ready_monthly_reports(session, principal.scope_id, principal.id)
    return supplier_response(session, item, evidence=True)


def equivalence_response(session, alias):
    candidate = json.loads(alias.identity_json)
    supplier = _scoped(session, Supplier, alias.supplier_id, alias.scope_id)
    return {"id": alias.id, "version": alias.version, "identityName": candidate.get("name", ""),
            "identityTaxId": candidate.get("taxId", ""), "identityCountry": candidate.get("country", ""),
            "candidate": candidate, "supplierId": alias.supplier_id, "supplierName": supplier.name,
            "active": bool(alias.active), "decision": alias.decision, "reason": alias.reason,
            "createdAt": _iso(alias.created_at), "updatedAt": _iso(alias.updated_at)}


def list_equivalences(session, scope, search=""):
    key = normalized(search)
    return [equivalence_response(session, item) for item in session.scalars(select(SupplierEquivalence)
            .where(SupplierEquivalence.scope_id == scope).order_by(SupplierEquivalence.created_at.desc()))
            if not key or key in normalized(item.identity_json)]


def update_equivalence(session, principal, alias_id, supplier_id=None, expected_version=None,
                       active=True, reason=""):
    principal.require("Operator")
    _lock(session, principal.scope_id, principal.id)
    alias = _scoped(session, SupplierEquivalence, alias_id, principal.scope_id)
    _expected(alias, expected_version)
    before = equivalence_response(session, alias)
    if supplier_id is not None:
        target = _scoped(session, Supplier, supplier_id, principal.scope_id)
        alias.supplier_id = target.id
    alias.active, alias.reason, alias.version = int(active), reason, alias.version + 1
    for observation in _observations(session, principal.scope_id):
        if observation.identity_key == alias.identity_key:
            observation.supplier_id = alias.supplier_id if active else None
            observation.status = "resolved" if active else "pending"
            observation.reason = "" if active else "equivalence_revoked"
            observation.suggestions_json = json_text([alias.supplier_id])
            observation.version += 1
    session.flush()
    after = equivalence_response(session, alias)
    audit(session, principal.scope_id, principal.id, "supplier.equivalence_updated", before=before, after=after, reason=reason)
    finalize_ready_monthly_reports(session, principal.scope_id, principal.id)
    return after


def summary(session, scope):
    # Counts stay cheap as the cumulative provenance grows; no source JSON is
    # needed to display the navigation and summary badges.
    counts = dict(session.execute(select(Supplier.kind, func.count(Supplier.id))
                  .where(Supplier.scope_id == scope).group_by(Supplier.kind)).all())
    return {"catalog": sum(counts.values()), "national": counts.get("national", 0),
            "foreign": counts.get("foreign", 0),
            "pending": session.scalar(select(func.count(SupplierObservation.identity_key.distinct())).where(
                SupplierObservation.scope_id == scope, SupplierObservation.active == 1,
                SupplierObservation.status == "pending")),
            "equivalences": session.scalar(select(func.count(SupplierEquivalence.id)).where(
                SupplierEquivalence.scope_id == scope, SupplierEquivalence.active == 1)),
            "reports": session.scalar(select(func.count(SupplierReport.id)).where(SupplierReport.scope_id == scope))}


def initialize_seed(session, principal, seed_payload):
    """Explicit seed import, preserving original columns, values and statuses."""
    principal.require("Admin")
    state = _lock(session, principal.scope_id, principal.id)
    if state.seeded:
        return summary(session, principal.scope_id)
    if session.scalar(select(Supplier.id).where(Supplier.scope_id == principal.scope_id).limit(1)):
        _error("SUPPLIER_SEED_NOT_EMPTY", "Inicializa las listas antes de incorporar movimientos")
    schemas = seed_payload.get("schemas", DEFAULT_SCHEMAS)
    if any(schemas.get(kind) != DEFAULT_SCHEMAS[kind] for kind in DEFAULT_SCHEMAS):
        _error("INVALID_SUPPLIER_SCHEMA", "Las columnas de las listas no coinciden con las listas originales", 400)
    state.schemas_json = json_text(schemas)
    for kind in ("national", "foreign"):
        for position, raw in enumerate(seed_payload.get(kind, [])):
            if kind == "national":
                values = {"type": kind, "name": raw.get("name", raw.get("RFC", "")),
                          "taxId": raw.get("taxId", raw.get("RFC", "")), "country": "MEX"}
                virtual = raw.get("virtualOperations", raw.get("Operaciones virtuales"))
                if type(virtual) is not bool:
                    virtual = normalized(virtual) in {"SI", "YES", "TRUE", "1"} if virtual is not None else None
                values["virtualOperations"] = virtual
            else:
                values = {"type": kind, "name": raw.get("name", raw.get("Nombre o Razón social", "")),
                          "country": raw.get("country", raw.get("País ", "")),
                          "taxId": raw.get("taxId", ""), "address": raw.get("address", raw.get("Domicilio", ""))}
            data = _data({**raw, **values})
            data["originalRow"] = {h: raw.get(h, "") for h in schemas[kind]}
            data["seedOrder"] = position
            data["seedEvidence"] = raw.get("source", seed_payload.get("source"))
            status = raw.get("originalStatus", raw.get("status", raw.get("Estatus", "Sin modificación")))
            _new_supplier(session, principal.scope_id, data, principal.id, original_status=status,
                          reason="Inicialización de listas originales")
    state.seeded = 1
    session.flush()
    audit(session, principal.scope_id, principal.id, "suppliers.seed_imported", counts={
        k: len(seed_payload.get(k, [])) for k in ("national", "foreign")}, source=seed_payload.get("source"))
    return summary(session, principal.scope_id)


def report_response(report):
    snapshot = json.loads(report.snapshot_json)
    return {"id": report.id, "label": report.label, "createdAt": _iso(report.created_at),
            "status": "ready",
            "nationalCount": len(snapshot["national"]), "foreignCount": len(snapshot["foreign"]),
            "sourceFingerprint": report.source_fingerprint, "createdBy": report.created_by}


def _freeze_supplier(item):
    return {key: getattr(item, key) for key in ("id", "kind", "name", "tax_id", "country", "data_json",
                                                "original_status", "version")}


def _observation_states(session, scope):
    fields = (SupplierObservation.id, SupplierObservation.active, SupplierObservation.status,
              SupplierObservation.supplier_id, SupplierObservation.identity_key)
    return {row.id: row for row in session.execute(select(*fields).where(SupplierObservation.scope_id == scope))}


def _previous_report_ids(session, scope):
    previous = session.scalar(select(SupplierReport).where(SupplierReport.scope_id == scope)
        .order_by(SupplierReport.created_at.desc(), SupplierReport.id.desc()).limit(1))
    if not previous:
        return set(), False
    snapshot = json.loads(previous.snapshot_json)
    return {row["supplierId"] for kind in ("national", "foreign") for row in snapshot[kind]}, True


def request_monthly_report(session, run, actor="worker"):
    """Freeze the publication's cumulative source set before later months arrive."""
    if run.kind != "monthly" or run.publication_status != "published":
        return None
    _lock(session, run.scope_id, actor)
    request = session.scalar(select(SupplierReportRequest).where(
        SupplierReportRequest.scope_id == run.scope_id, SupplierReportRequest.source_run_id == run.id))
    if request is None:
        period = session.get(Period, run.period_id)
        if not period or period.active_run_id != run.id:
            return None
        state = ensure_initialized(session, run.scope_id, actor)
        observations = _observations(session, run.scope_id, active=True)
        draft = {"schemas": json.loads(state.schemas_json),
                 "suppliers": [_freeze_supplier(item) for item in session.scalars(select(Supplier)
                                .where(Supplier.scope_id == run.scope_id))],
                 "observations": [{"id": o.id, "virtualConfirmed": bool(o.virtual_confirmed)} for o in observations],
                 "sourceRuns": sorted({o.run_id for o in observations}),
                 "monthlyRuns": list(session.scalars(select(Period.active_run_id).where(
                     Period.scope_id == run.scope_id, Period.active_run_id.is_not(None))))}
        request = SupplierReportRequest(id=str(uuid4()), scope_id=run.scope_id, source_run_id=run.id,
            period_name=period.name, state="pending_review", draft_json=json_text(draft), created_by=run.created_by)
        session.add(request)
        session.flush()
        audit(session, run.scope_id, actor, "suppliers.monthly_report_requested", run.id,
              requestId=request.id, period=period.name)
    finalize_ready_monthly_reports(session, run.scope_id, actor)
    return request_response(session, request)


def _draft_state(session, request, observations, items, active_runs):
    draft = json.loads(request.draft_json)
    if request.source_run_id not in active_runs or not set(draft.get("monthlyRuns", [])).issubset(active_runs):
        return None, 0, "source_superseded"
    captured = []
    for entry in draft["observations"]:
        observation = observations.get(entry["id"])
        if observation is None or not observation.active:
            return None, 0, "source_superseded"
        captured.append((observation, entry))
    pending = {o.identity_key for o, _ in captured if o.status == "pending"}
    if pending:
        return None, len(pending), None
    records = {record["id"]: record for record in draft["suppliers"]}
    virtual_evidence = set()
    for observation, entry in captured:
        if observation.supplier_id and observation.supplier_id in items:
            records.setdefault(observation.supplier_id, _freeze_supplier(items[observation.supplier_id]))
            if entry["virtualConfirmed"]:
                virtual_evidence.add(observation.supplier_id)
    previous_ids, has_previous = _previous_report_ids(session, request.scope_id)
    snapshot = {"schemas": draft["schemas"], "national": [], "foreign": [],
                "sourceRuns": draft["sourceRuns"], "monthlyRunId": request.source_run_id}
    unknown_confirmations = 0
    ordered = sorted(records.values(), key=lambda record: (record["kind"],
        "seedOrder" not in json.loads(record["data_json"]), json.loads(record["data_json"]).get("seedOrder", 0),
        record["name"], record["id"]))
    for record in ordered:
        current = items.get(record["id"])
        if current is None:
            return None, 0, "supplier_unavailable"
        virtual = (True if current.virtual_confirmation == 1 or current.id in virtual_evidence
                   else False if current.virtual_confirmation == 0 else None)
        if record["kind"] == "national" and virtual is None and current.id not in previous_ids:
            unknown_confirmations += 1
            continue
        item = SimpleNamespace(**record)
        is_new = item.id not in previous_ids and item.original_status is None
        status = "Alta" if is_new else (item.original_status if not has_previous and item.original_status is not None else "Sin modificación")
        snapshot[item.kind].append(_report_row(item, virtual, status, is_new))
    if unknown_confirmations:
        return None, unknown_confirmations, None
    return snapshot, 0, None


def finalize_ready_monthly_reports(session, scope, actor="worker"):
    """Finish durable drafts in publication order after their decisions are ready."""
    requests = list(session.scalars(select(SupplierReportRequest).where(
        SupplierReportRequest.scope_id == scope, SupplierReportRequest.state == "pending_review")
        .order_by(SupplierReportRequest.created_at, SupplierReportRequest.id)))
    if not requests:
        return
    _lock(session, scope, actor)
    session.flush()
    observations = _observation_states(session, scope)
    items = {item.id: item for item in session.scalars(select(Supplier).where(Supplier.scope_id == scope))}
    active_runs = set(session.scalars(select(Period.active_run_id).where(
        Period.scope_id == scope, Period.active_run_id.is_not(None))))
    for request in requests:
        snapshot, pending, cancelled = _draft_state(session, request, observations, items, active_runs)
        if cancelled:
            request.state = "cancelled"
            draft = json.loads(request.draft_json)
            draft["cancelReason"] = cancelled
            request.draft_json = json_text(draft)
            audit(session, scope, actor, "suppliers.monthly_report_cancelled", requestId=request.id,
                  runId=request.source_run_id, reason=cancelled)
            session.flush()
            continue
        if pending:
            # Later cumulative drafts must not consume an earlier draft's altas.
            break
        key = "supplier-monthly:" + request.source_run_id
        existing = session.scalar(select(SupplierReport).where(SupplierReport.scope_id == scope,
                                   SupplierReport.idempotency_key == key))
        if existing is None:
            existing = SupplierReport(id=str(uuid4()), scope_id=scope, idempotency_key=key,
                request_hash=_hash({"monthlyRunId": request.source_run_id}),
                label="Proveedores · " + request.period_name, snapshot_json=json_text(snapshot),
                source_fingerprint=_hash(snapshot), created_by=request.created_by)
            session.add(existing)
            session.flush()
            audit(session, scope, actor, "suppliers.monthly_report_ready", reportId=existing.id,
                  runId=request.source_run_id, requestId=request.id, sourceFingerprint=existing.source_fingerprint)
        request.state, request.report_id = "ready", existing.id
        session.flush()


def _pending_request_observation_ids(session, scope):
    return {entry["id"] for request in session.scalars(select(SupplierReportRequest).where(
        SupplierReportRequest.scope_id == scope, SupplierReportRequest.state == "pending_review"))
        for entry in json.loads(request.draft_json)["observations"]}


def request_response(session, request, context=None):
    pending = 0
    if request.state == "pending_review":
        if context is None:
            observations = _observation_states(session, request.scope_id)
            items = {item.id: item for item in session.scalars(select(Supplier).where(Supplier.scope_id == request.scope_id))}
            active_runs = set(session.scalars(select(Period.active_run_id).where(
                Period.scope_id == request.scope_id, Period.active_run_id.is_not(None))))
        else:
            observations, items, active_runs = context
        _, pending, _ = _draft_state(session, request, observations, items, active_runs)
    return {"id": request.id, "runId": request.source_run_id, "period": request.period_name,
            "createdAt": _iso(request.created_at), "status": request.state, "reportId": request.report_id,
            "pending": pending, "reason": json.loads(request.draft_json).get("cancelReason")}


def list_report_requests(session, scope):
    requests = list(session.scalars(select(SupplierReportRequest).where(SupplierReportRequest.scope_id == scope)
                    .order_by(SupplierReportRequest.created_at.desc())))
    context = None
    if any(r.state == "pending_review" for r in requests):
        context = (_observation_states(session, scope),
            {item.id: item for item in session.scalars(select(Supplier).where(Supplier.scope_id == scope))},
            set(session.scalars(select(Period.active_run_id).where(Period.scope_id == scope,
                                                                  Period.active_run_id.is_not(None)))))
    return [request_response(session, request, context) for request in requests]


def monthly_report_state(session, scope, run_id):
    _scoped(session, Run, run_id, scope)
    request = session.scalar(select(SupplierReportRequest).where(
        SupplierReportRequest.scope_id == scope, SupplierReportRequest.source_run_id == run_id))
    if request is None or request.state == "cancelled":
        return {"runId": run_id, "status": "unavailable", "report": None, "pending": 0}
    if request.state == "ready":
        report = _scoped(session, SupplierReport, request.report_id, scope)
        return {"runId": run_id, "status": "ready", "report": report_response(report), "pending": 0}
    state = request_response(session, request)
    return {"runId": run_id, "status": "pending_review", "report": None, "pending": state["pending"]}


def list_reports(session, scope, search=""):
    key = normalized(search)
    return [report_response(r) for r in session.scalars(select(SupplierReport).where(
            SupplierReport.scope_id == scope).order_by(SupplierReport.created_at.desc(), SupplierReport.id.desc()))
            if not key or key in normalized(r.label)]


def _report_row(item, virtual, status, is_new):
    data = _supplier_data(item)
    original = data.get("originalRow", {})
    if item.kind == "national":
        cells = [item.tax_id, "Si" if virtual else "No", status]
    else:
        address = " ".join(filter(None, [data.get("address"), data.get("externalNumber"),
                                         data.get("internalNumber"), data.get("postalCode"),
                                         data.get("city"), data.get("state")]))
        cells = [item.name, original.get("Apellido Paterno", ""), original.get("Apellido Materno", ""),
                 item.country, address, original.get("Cliente/Proveedor", "Proveedor") or "Proveedor", status]
    if original and item.version == 1:
        cells = [original.get(h, "") for h in DEFAULT_SCHEMAS[item.kind]]
        cells[-1] = status
        if item.kind == "national":
            cells[1] = "Si" if virtual else "No"
    return {"supplierId": item.id, "values": cells, "highlight": bool(is_new), "status": status}


def create_report(session, principal, key, label=None):
    principal.require("Operator")
    validate_key(key)
    state = _lock(session, principal.scope_id, principal.id)
    label = str(label or "Reporte de proveedores").strip()
    if not label or len(label) > 200:
        _error("INVALID_REPORT_LABEL", "El nombre del reporte debe tener entre 1 y 200 caracteres", 400)
    request_hash = _hash({"label": label})
    previous = session.scalar(select(SupplierReport).where(SupplierReport.scope_id == principal.scope_id,
                              SupplierReport.idempotency_key == key))
    if previous:
        if previous.request_hash != request_hash:
            _error("IDEMPOTENCY_CONFLICT", "La clave de idempotencia ya se usó con otra solicitud")
        return report_response(previous)
    if session.scalar(select(SupplierObservation.id).where(SupplierObservation.scope_id == principal.scope_id,
                      SupplierObservation.active == 1, SupplierObservation.status == "pending").limit(1)):
        _error("SUPPLIERS_PENDING_REVIEW", "Resuelve los proveedores pendientes antes de generar ambas listas")
    reports = list(session.scalars(select(SupplierReport).where(SupplierReport.scope_id == principal.scope_id)
                                  .order_by(SupplierReport.created_at.desc(), SupplierReport.id.desc())))
    previous_ids = set()
    if reports:
        snapshot = json.loads(reports[0].snapshot_json)
        previous_ids = {r["supplierId"] for kind in ("national", "foreign") for r in snapshot[kind]}
    snapshot = {"schemas": json.loads(state.schemas_json), "national": [], "foreign": [],
                "sourceRuns": sorted({o.run_id for o in _observations(session, principal.scope_id, active=True)})}
    items = list(session.scalars(select(Supplier).where(Supplier.scope_id == principal.scope_id)))
    items.sort(key=lambda i: (i.kind, "seedOrder" not in json.loads(i.data_json),
                              json.loads(i.data_json).get("seedOrder", 0), i.name, i.id))
    for item in items:
        observations = _observations(session, principal.scope_id, item.id)
        virtual = _virtual(item, observations)
        if item.kind == "national" and virtual is None:
            _error("VIRTUAL_CONFIRMATION_REQUIRED", "Confirma Sí o No para los proveedores nacionales sin evidencia")
        is_new = item.id not in previous_ids and item.original_status is None
        # The first snapshot preserves the imported statuses verbatim. An imported
        # Alta is historical and does not become a new, yellow row.
        status = "Alta" if is_new else (item.original_status if not reports and item.original_status is not None else "Sin modificación")
        snapshot[item.kind].append(_report_row(item, virtual, status, is_new))
    report = SupplierReport(id=str(uuid4()), scope_id=principal.scope_id, idempotency_key=key,
        request_hash=request_hash, label=label, snapshot_json=json_text(snapshot),
        source_fingerprint=_hash(snapshot), created_by=principal.id)
    session.add(report)
    session.flush()
    audit(session, principal.scope_id, principal.id, "suppliers.report_created", reportId=report.id,
          sourceFingerprint=report.source_fingerprint, national=len(snapshot["national"]), foreign=len(snapshot["foreign"]))
    return report_response(report)


def report_xlsx(session, scope, report_id, kind):
    """Both files derive only from one frozen snapshot; downloads never mutate it."""
    if kind not in ("national", "foreign"):
        _error("INVALID_SUPPLIER_TYPE", "Selecciona la lista nacional o extranjera", 400)
    report = _scoped(session, SupplierReport, report_id, scope)
    snapshot = json.loads(report.snapshot_json)
    import xlsxwriter
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False,
                                            "strings_to_urls": False})
    # A fixed property makes repeated downloads byte-stable as well as cell-stable.
    workbook.set_properties({"created": datetime(2026, 1, 1), "title": report.label})
    worksheet = workbook.add_worksheet("Sheet1")
    header = workbook.add_format({"bold": True, "bg_color": "#D9E2F3", "border": 1, "text_wrap": True, "valign": "vcenter"})
    body = workbook.add_format({"text_wrap": True, "valign": "top"})
    yellow = workbook.add_format({"bg_color": "#FFFF00", "text_wrap": True, "valign": "top"})
    headers = snapshot["schemas"][kind]
    widths = [23, 26, 24] if kind == "national" else [44, 24, 24, 40, 90, 24, 24]
    worksheet.set_row(0, 32)
    for column, value in enumerate(headers):
        worksheet.write_string(0, column, value, header)
        worksheet.set_column(column, column, widths[column])
    for row_number, row in enumerate(snapshot[kind], 1):
        style = yellow if row["highlight"] else body
        lines = max((len(str(value or "")) // max(widths[column] - 3, 1) + 1
                     for column, value in enumerate(row["values"])), default=1)
        worksheet.set_row(row_number, min(409, max(20, lines * 15)))
        for column, value in enumerate(row["values"]):
            if value is None or value == "":
                worksheet.write_blank(row_number, column, None, style)
            else:
                worksheet.write_string(row_number, column, str(value), style)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, len(snapshot[kind]), len(headers) - 1)
    workbook.close()
    return output.getvalue()
