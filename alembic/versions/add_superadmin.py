"""add is_superadmin to users

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-03-31
"""
import os
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_superadmin', sa.Boolean(), server_default='false', nullable=False))
    # Seed superadmin
    owner_id = os.getenv("OWNER_TELEGRAM_ID", "0")
    op.execute(f"UPDATE users SET is_superadmin = true WHERE telegram_id = {owner_id}")


def downgrade() -> None:
    op.drop_column('users', 'is_superadmin')
