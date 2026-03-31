"""Add pending_commands table for bidirectional CRM-OpenClaw sync.

Revision ID: add_pending_commands
Revises: add_agent_files
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "add_pending_commands"
down_revision = "add_agent_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_commands",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("command_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pending_commands")
