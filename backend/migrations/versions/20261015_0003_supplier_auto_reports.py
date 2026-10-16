"""Durable monthly supplier report requests and frozen review drafts.

Revision ID: 20261015_0003
Revises: 20261015_0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

revision = "20261015_0003"
down_revision = "20261015_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("supplier_report_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope_id", sa.Unicode(100), nullable=False),
        sa.Column("source_run_id", sa.String(36), nullable=False),
        sa.Column("period_name", sa.Unicode(100), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=True),
        sa.Column("draft_json", sa.UnicodeText().with_variant(mssql.NVARCHAR(None), "mssql"), nullable=False),
        sa.Column("created_by", sa.Unicode(200), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(mssql.DATETIME2(), "mssql"), nullable=False),
        sa.UniqueConstraint("scope_id", "source_run_id", name="uq_supplier_report_request_run"))
    op.create_index("ix_supplier_report_requests_scope", "supplier_report_requests", ["scope_id", "created_at"])


def downgrade():
    op.drop_table("supplier_report_requests")
