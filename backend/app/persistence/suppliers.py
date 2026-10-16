"""Scoped cumulative supplier catalog, decisions, provenance and immutable reports."""
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Integer, String, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from . import Base
from .models import Identity, LargeText, UTCDateTime, utcnow


class SupplierScope(Base):
    __tablename__ = "supplier_scopes"
    scope_id: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    seeded: Mapped[int] = mapped_column(Integer, default=0)
    schemas_json: Mapped[str] = mapped_column(LargeText, default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Supplier(Identity, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("kind IN ('national','foreign')", name="ck_supplier_kind"),
        Index("ix_suppliers_scope", "scope_id", "kind"),
    )
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(Unicode(512))
    name_key: Mapped[str] = mapped_column(Unicode(512))
    tax_id: Mapped[str] = mapped_column(Unicode(100), default="")
    country: Mapped[str] = mapped_column(Unicode(100), default="")
    data_json: Mapped[str] = mapped_column(LargeText, default="{}")
    original_status: Mapped[str | None] = mapped_column(Unicode(100))
    virtual_confirmation: Mapped[int | None] = mapped_column(Integer)
    virtual_reason: Mapped[str | None] = mapped_column(LargeText)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SupplierEquivalence(Identity, Base):
    __tablename__ = "supplier_equivalences"
    __table_args__ = (
        UniqueConstraint("scope_id", "identity_key", name="uq_supplier_alias_scope_identity"),
        Index("ix_supplier_alias_scope", "scope_id", "supplier_id"),
    )
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    identity_key: Mapped[str] = mapped_column(String(64))
    identity_json: Mapped[str] = mapped_column(LargeText)
    # Detached IDs retain a decision and its audit even if source months are deleted.
    supplier_id: Mapped[str] = mapped_column(String(36))
    active: Mapped[int] = mapped_column(Integer, default=1)
    decision: Mapped[str] = mapped_column(String(20), default="same")
    reason: Mapped[str] = mapped_column(LargeText, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SupplierObservation(Identity, Base):
    __tablename__ = "supplier_observations"
    __table_args__ = (
        UniqueConstraint("scope_id", "run_id", "source_row_id", name="uq_supplier_observation_source"),
        Index("ix_supplier_observation_scope", "scope_id", "active", "status"),
        Index("ix_supplier_observation_supplier", "scope_id", "supplier_id"),
    )
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    run_id: Mapped[str] = mapped_column(String(36))
    source_kind: Mapped[str] = mapped_column(String(20), default="monthly")
    period_id: Mapped[str] = mapped_column(String(36))
    period_name: Mapped[str] = mapped_column(Unicode(100))
    source_row_id: Mapped[str] = mapped_column(String(36))
    identity_key: Mapped[str] = mapped_column(String(64))
    candidate_json: Mapped[str] = mapped_column(LargeText)
    evidence_json: Mapped[str] = mapped_column(LargeText)
    suggestions_json: Mapped[str] = mapped_column(LargeText, default="[]")
    supplier_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reason: Mapped[str] = mapped_column(String(40), default="")
    active: Mapped[int] = mapped_column(Integer, default=1)
    virtual_confirmed: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SupplierReport(Identity, Base):
    __tablename__ = "supplier_reports"
    __table_args__ = (
        UniqueConstraint("scope_id", "idempotency_key", name="uq_supplier_report_scope_key"),
        Index("ix_supplier_reports_scope", "scope_id", "created_at"),
    )
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    idempotency_key: Mapped[str] = mapped_column(Unicode(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(Unicode(200))
    snapshot_json: Mapped[str] = mapped_column(LargeText)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(Unicode(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SupplierReportRequest(Identity, Base):
    __tablename__ = "supplier_report_requests"
    __table_args__ = (
        UniqueConstraint("scope_id", "source_run_id", name="uq_supplier_report_request_run"),
        Index("ix_supplier_report_requests_scope", "scope_id", "created_at"),
    )
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    source_run_id: Mapped[str] = mapped_column(String(36))
    period_name: Mapped[str] = mapped_column(Unicode(100))
    state: Mapped[str] = mapped_column(String(30), default="pending_review")
    report_id: Mapped[str | None] = mapped_column(String(36))
    draft_json: Mapped[str] = mapped_column(LargeText)
    created_by: Mapped[str] = mapped_column(Unicode(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
