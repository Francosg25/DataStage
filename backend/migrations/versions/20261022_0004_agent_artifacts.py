"""Private agent artifacts and response metadata; existing messages are retained.

Revision ID: 20261022_0004
Revises: 20261015_0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

revision = "20261022_0004"
down_revision = "20261015_0003"
branch_labels = None
depends_on = None


def upgrade():
    text = sa.UnicodeText().with_variant(mssql.NVARCHAR(None), "mssql")
    op.create_table("agent_message_details",
        sa.Column("message_id", sa.String(36), sa.ForeignKey("agent_messages.id"), primary_key=True),
        sa.Column("metadata_json", text, nullable=False))
    op.create_table("agent_artifacts",
        sa.Column("document_id", sa.String(36), sa.ForeignKey("stored_documents.id"), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("agent_conversations.id"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("manifest_json", text, nullable=False),
        sa.UniqueConstraint("conversation_id", "request_hash", name="uq_agent_artifact_request"))


def downgrade():
    op.drop_table("agent_artifacts")
    op.drop_table("agent_message_details")
