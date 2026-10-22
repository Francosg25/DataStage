"""Owner-scoped, explicit personal memories; existing chats stay unchanged.

Revision ID: 20261022_0005
Revises: 20261022_0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

revision = "20261022_0005"
down_revision = "20261022_0004"
branch_labels = None
depends_on = None


def upgrade():
    date = sa.DateTime().with_variant(mssql.DATETIME2(), "mssql")
    op.create_table("agent_memory_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope_id", sa.Unicode(100), nullable=False),
        sa.Column("user_id", sa.Unicode(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", date, nullable=False),
        sa.UniqueConstraint("scope_id", "user_id", name="uq_agent_memory_owner"))
    op.create_table("agent_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("agent_memory_profiles.id"), nullable=False),
        sa.Column("title", sa.Unicode(160), nullable=False),
        sa.Column("content", sa.Unicode(1200), nullable=False),
        sa.Column("created_at", date, nullable=False),
        sa.Column("updated_at", date, nullable=False))
    op.create_index("ix_agent_memories_profile", "agent_memories", ["profile_id"])


def downgrade():
    op.drop_index("ix_agent_memories_profile", table_name="agent_memories")
    op.drop_table("agent_memories")
    op.drop_table("agent_memory_profiles")
