"""add monthly_budget to workspaces

Revision ID: a2b3c4d5e6f7
Revises: c1fbeb7669fc
Create Date: 2026-03-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'c1fbeb7669fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('workspaces', sa.Column('monthly_budget', sa.Float(), server_default='100.0'))

def downgrade() -> None:
    op.drop_column('workspaces', 'monthly_budget')
