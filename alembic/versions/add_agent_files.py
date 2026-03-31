"""Add agent_files table for DB-backed file storage.

Revision ID: add_agent_files
Revises: add_superadmin
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "add_agent_files"
down_revision = "add_superadmin"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), server_default=""),
        sa.Column("size", sa.Integer(), server_default="0"),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("agent_id", "filename", "workspace_id", name="uq_agent_file_workspace"),
    )


def downgrade():
    op.drop_table("agent_files")
