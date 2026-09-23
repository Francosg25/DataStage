"""Operational records. All datetimes are naive UTC; business dates retain local meaning."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, CheckConstraint, DDL, DateTime, ForeignKey, Index, Integer, String, Unicode, UnicodeText, UniqueConstraint, event, inspect
from sqlalchemy.dialects.mssql import DATETIME2, NVARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


def uuid_string():
    return str(uuid4())


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


UTCDateTime = DateTime().with_variant(DATETIME2(), "mssql")
LargeText = UnicodeText().with_variant(NVARCHAR(None), "mssql")


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)


class Period(Identity, Base):
    __tablename__ = "periods"
    __table_args__ = (UniqueConstraint("scope_id", "year", "month", name="uq_period_scope_year_month"), CheckConstraint("month >= 1 AND month <= 12", name="ck_period_month"))
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Unicode(100))
    active_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("processing_runs.id", use_alter=True, name="fk_period_active_run"))
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Run(Identity, Base):
    __tablename__ = "processing_runs"
    __table_args__ = (UniqueConstraint("scope_id", "input_fingerprint", name="uq_run_scope_fingerprint"), Index("ix_runs_scope_created", "scope_id", "created_at"))
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    kind: Mapped[str] = mapped_column(String(20), default="monthly")
    period_id: Mapped[str | None] = mapped_column(ForeignKey("periods.id"))
    year: Mapped[int] = mapped_column(Integer)
    range_name: Mapped[str | None] = mapped_column(Unicode(100))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    phase: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    functional_result: Mapped[str | None] = mapped_column(String(20))
    publication_status: Mapped[str] = mapped_column(String(30), default="pending")
    export_status: Mapped[str] = mapped_column(String(30), default="pending")
    created_by: Mapped[str] = mapped_column(Unicode(200), default="system")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    engine_version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    options_json: Mapped[str] = mapped_column(LargeText, default="{}")
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    expected_period_version: Mapped[int] = mapped_column(Integer, default=0)
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("processing_runs.id"))
    source_manifest_json: Mapped[str] = mapped_column(LargeText, default="[]")
    result_document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("stored_documents.id", use_alter=True, name="fk_run_result_document"))
    export_document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("stored_documents.id", use_alter=True, name="fk_run_export_document"))
    error_message: Mapped[str | None] = mapped_column(LargeText)
    counts_json: Mapped[str] = mapped_column(LargeText, default="{}")


class StoredDocument(Identity, Base):
    __tablename__ = "stored_documents"
    __table_args__ = (Index("ix_documents_scope_sha", "scope_id", "sha256"),)
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("processing_runs.id"))
    kind: Mapped[str] = mapped_column(String(30))
    original_name: Mapped[str] = mapped_column(Unicode(512))
    storage_key: Mapped[str] = mapped_column(Unicode(512))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(30), default="available")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ProcessingFile(Identity, Base):
    __tablename__ = "processing_files"
    __table_args__ = (UniqueConstraint("run_id", "ordinal", name="uq_file_run_ordinal"), Index("ix_files_run", "run_id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    period_id: Mapped[str | None] = mapped_column(ForeignKey("periods.id"))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("stored_documents.id"))
    file_name: Mapped[str] = mapped_column(Unicode(512))
    table_code: Mapped[str] = mapped_column(Unicode(100))
    folio: Mapped[str] = mapped_column(Unicode(512), default="")
    sha256: Mapped[str] = mapped_column(String(64))
    ordinal: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    message: Mapped[str] = mapped_column(LargeText, default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    date_column_count: Mapped[int] = mapped_column(Integer, default=0)
    headers_json: Mapped[str] = mapped_column(LargeText, default="[]")


class ProcessingTable(Identity, Base):
    __tablename__ = "processing_tables"
    __table_args__ = (UniqueConstraint("run_id", "table_code", name="uq_processing_table_run_code"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    table_code: Mapped[str] = mapped_column(Unicode(100))
    sheet_name: Mapped[str] = mapped_column(Unicode(31))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    date_column_count: Mapped[int] = mapped_column(Integer, default=0)
    headers_json: Mapped[str] = mapped_column(LargeText, default="[]")


class Issue(Identity, Base):
    __tablename__ = "processing_issues"
    __table_args__ = (CheckConstraint("severity IN ('error', 'warning')", name="ck_issue_severity"), Index("ix_issues_run_severity", "run_id", "severity"))
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    file_id: Mapped[str | None] = mapped_column(ForeignKey("processing_files.id"))
    severity: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(LargeText)
    row_number: Mapped[int | None] = mapped_column(Integer)
    column_name: Mapped[str | None] = mapped_column(Unicode(512))
    original_value: Mapped[str | None] = mapped_column(LargeText)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_scope_created", "scope_id", "created_at"),)
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("processing_runs.id"))
    actor: Mapped[str] = mapped_column(Unicode(200))
    action: Mapped[str] = mapped_column(String(100))
    details_json: Mapped[str] = mapped_column(LargeText, default="{}")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Job(Identity, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "available_at"), Index("ix_jobs_run", "run_id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    fence: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(LargeText, default="{}")
    last_error: Mapped[str | None] = mapped_column(LargeText)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OutboxMessage(Identity, Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (Index("ix_outbox_pending", "status", "created_at"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(LargeText, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class IdempotencyRequest(Identity, Base):
    __tablename__ = "idempotency_requests"
    __table_args__ = (UniqueConstraint("scope_id", "key", name="uq_idempotency_scope_key"),)
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    key: Mapped[str] = mapped_column(Unicode(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))


class AnnualSource(Identity, Base):
    __tablename__ = "annual_sources"
    __table_args__ = (UniqueConstraint("annual_run_id", "monthly_run_id", name="uq_annual_monthly_source"),)
    annual_run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    monthly_run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id"))
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"))


class Conversation(Identity, Base):
    __tablename__ = "agent_conversations"
    scope_id: Mapped[str] = mapped_column(Unicode(100))
    user_id: Mapped[str] = mapped_column(Unicode(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AgentMessage(Identity, Base):
    __tablename__ = "agent_messages"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("agent_conversations.id"))
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(LargeText)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# Errors and warnings expose separate read-only contracts backed by one indexed
# issue store. Application writes use Issue so severity validation is centralized.
@event.listens_for(Base.metadata, "after_create")
def _create_issue_views(metadata, connection, **kwargs):
    existing = set(inspect(connection).get_view_names())
    for view_name, severity in (("processing_errors", "error"), ("processing_warnings", "warning")):
        if view_name not in existing:
            connection.execute(DDL(f"CREATE VIEW {view_name} AS SELECT * FROM processing_issues WHERE severity = '{severity}'"))


@event.listens_for(Base.metadata, "before_drop")
def _drop_issue_views(metadata, connection, **kwargs):
    existing = set(inspect(connection).get_view_names())
    for view_name in ("processing_errors", "processing_warnings"):
        if view_name in existing:
            connection.execute(DDL(f"DROP VIEW {view_name}"))

