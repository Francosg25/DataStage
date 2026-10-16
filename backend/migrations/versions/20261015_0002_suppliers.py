"""Scoped cumulative suppliers and immutable paired reports.

Revision ID: 20261015_0002
Revises: 20260922_0001

Frozen definitions: source IDs intentionally have no run foreign keys, so
deleting a month retires evidence while retaining catalog/audit/report history.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

revision = "20261015_0002"
down_revision = "20260922_0001"
branch_labels = None
depends_on = None


def _text():
    return sa.UnicodeText().with_variant(mssql.NVARCHAR(None), "mssql")


def _date():
    return sa.DateTime().with_variant(mssql.DATETIME2(), "mssql")


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _scope():
    return sa.Column("scope_id", sa.Unicode(100), nullable=False)


def upgrade():
    op.create_table("supplier_scopes",
        sa.Column("scope_id", sa.Unicode(100), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("seeded", sa.Integer(), nullable=False),
        sa.Column("schemas_json", _text(), nullable=False),
        sa.Column("created_at", _date(), nullable=False))
    op.create_table("suppliers", _id(), _scope(),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("name", sa.Unicode(512), nullable=False),
        sa.Column("name_key", sa.Unicode(512), nullable=False),
        sa.Column("tax_id", sa.Unicode(100), nullable=False),
        sa.Column("country", sa.Unicode(100), nullable=False),
        sa.Column("data_json", _text(), nullable=False),
        sa.Column("original_status", sa.Unicode(100), nullable=True),
        sa.Column("virtual_confirmation", sa.Integer(), nullable=True),
        sa.Column("virtual_reason", _text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", _date(), nullable=False),
        sa.Column("updated_at", _date(), nullable=False),
        sa.CheckConstraint("kind IN ('national','foreign')", name="ck_supplier_kind"))
    op.create_index("ix_suppliers_scope", "suppliers", ["scope_id", "kind"])
    op.create_table("supplier_equivalences", _id(), _scope(),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("identity_json", _text(), nullable=False),
        sa.Column("supplier_id", sa.String(36), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", _text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", _date(), nullable=False),
        sa.Column("updated_at", _date(), nullable=False),
        sa.UniqueConstraint("scope_id", "identity_key", name="uq_supplier_alias_scope_identity"))
    op.create_index("ix_supplier_alias_scope", "supplier_equivalences", ["scope_id", "supplier_id"])
    op.create_table("supplier_observations", _id(), _scope(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("period_id", sa.String(36), nullable=False),
        sa.Column("period_name", sa.Unicode(100), nullable=False),
        sa.Column("source_row_id", sa.String(36), nullable=False),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("candidate_json", _text(), nullable=False),
        sa.Column("evidence_json", _text(), nullable=False),
        sa.Column("suggestions_json", _text(), nullable=False),
        sa.Column("supplier_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("virtual_confirmed", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", _date(), nullable=False),
        sa.UniqueConstraint("scope_id", "run_id", "source_row_id", name="uq_supplier_observation_source"))
    op.create_index("ix_supplier_observation_scope", "supplier_observations", ["scope_id", "active", "status"])
    op.create_index("ix_supplier_observation_supplier", "supplier_observations", ["scope_id", "supplier_id"])
    op.create_table("supplier_reports", _id(), _scope(),
        sa.Column("idempotency_key", sa.Unicode(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("label", sa.Unicode(200), nullable=False),
        sa.Column("snapshot_json", _text(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by", sa.Unicode(200), nullable=False),
        sa.Column("created_at", _date(), nullable=False),
        sa.UniqueConstraint("scope_id", "idempotency_key", name="uq_supplier_report_scope_key"))
    op.create_index("ix_supplier_reports_scope", "supplier_reports", ["scope_id", "created_at"])


def downgrade():
    for table in ("supplier_reports", "supplier_observations", "supplier_equivalences", "suppliers", "supplier_scopes"):
        op.drop_table(table)
