"""Private conversational source files; additive, preserves existing data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

revision = "20261022_0006"
down_revision = "20261022_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_uploads",
        sa.Column("document_id", sa.String(36), sa.ForeignKey("stored_documents.id"), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("agent_conversations.id"), nullable=False),
        sa.Column("parsed_document_id", sa.String(36), sa.ForeignKey("stored_documents.id"), nullable=False),
        sa.Column("metadata_json", sa.UnicodeText().with_variant(mssql.NVARCHAR(None), "mssql"), nullable=False),
        sa.UniqueConstraint("parsed_document_id"))
    op.create_index("ix_agent_uploads_conversation", "agent_uploads", ["conversation_id"])


def downgrade():
    op.drop_index("ix_agent_uploads_conversation", table_name="agent_uploads")
    op.drop_table("agent_uploads")
