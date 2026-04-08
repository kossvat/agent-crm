"""initial

Revision ID: c1fbeb7669fc
Revises:
Create Date: 2026-03-28 17:25:11.029521

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1fbeb7669fc'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('telegram_id', sa.Integer(), unique=True, nullable=True),
        sa.Column('email', sa.String(255), unique=True, nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True)),
        sa.Column('onboarding_complete', sa.Boolean(), default=False),
    )

    op.create_table(
        'workspaces',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('openclaw_url', sa.String(500), nullable=True),
        sa.Column('api_key', sa.String(500), nullable=True),
        sa.Column('tier', sa.String(20), default='hobby'),
        sa.Column('agent_limit', sa.Integer(), default=3),
        sa.Column('created', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'agents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('emoji', sa.String(10), default='🤖'),
        sa.Column('model', sa.String(100), default=''),
        sa.Column('status', sa.String(20), default='idle'),
        sa.Column('session_key', sa.String(255), default=''),
        sa.Column('last_active', sa.DateTime(timezone=True), nullable=True),
        sa.Column('role', sa.String(100), default=''),
        sa.Column('bio', sa.Text(), default=''),
        sa.Column('daily_cost', sa.Float(), default=0.0),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), default=''),
        sa.Column('status', sa.String(20), default='todo'),
        sa.Column('priority', sa.String(20), default='medium'),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('created_by', sa.String(100), default=''),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('category', sa.String(50), default=''),
        sa.Column('reminder_1h_sent', sa.Boolean(), default=False),
        sa.Column('reminder_due_sent', sa.Boolean(), default=False),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True)),
        sa.Column('updated', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'crons',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('schedule', sa.String(100), nullable=False),
        sa.Column('command', sa.Text(), default=''),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('last_run', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run', sa.DateTime(timezone=True), nullable=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'costs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), default=0),
        sa.Column('output_tokens', sa.Integer(), default=0),
        sa.Column('cost_usd', sa.Float(), default=0.0),
        sa.Column('model', sa.String(100), default=''),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id'), nullable=True),
    )

    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('content', sa.Text(), default=''),
        sa.Column('source', sa.String(50), default='manual'),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True)),
        sa.Column('updated', sa.DateTime(timezone=True)),
    )

    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id'), nullable=True),
        sa.Column('type', sa.String(20), default='info'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True)),
        sa.Column('is_read', sa.Boolean(), default=False),
    )


def downgrade() -> None:
    op.drop_table('alerts')
    op.drop_table('journal_entries')
    op.drop_table('costs')
    op.drop_table('crons')
    op.drop_table('tasks')
    op.drop_table('agents')
    op.drop_table('workspaces')
    op.drop_table('users')
