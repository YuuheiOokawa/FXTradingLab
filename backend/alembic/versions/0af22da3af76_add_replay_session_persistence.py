"""add replay session persistence

Revision ID: 0af22da3af76
Revises: 560e5f685016
Create Date: 2026-07-20 23:15:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.db.types


revision: str = '0af22da3af76'
down_revision: Union[str, None] = '560e5f685016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'replay_sessions',
        sa.Column('id', app.db.types.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('instrument_id', app.db.types.GUID(), nullable=False),
        sa.Column('granularity', sa.String(length=5), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('speed', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('initial_balance', sa.Float(), nullable=False),
        sa.Column('current_balance', sa.Float(), nullable=False),
        sa.Column('training_mode', sa.Boolean(), nullable=False),
        sa.Column('current_index', sa.Integer(), nullable=False),
        sa.Column('candles', app.db.types.PortableJSON(), nullable=False),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_replay_session_status', 'replay_sessions', ['status'])

    op.create_table(
        'replay_trades',
        sa.Column('id', app.db.types.GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('session_id', app.db.types.GUID(), nullable=False),
        sa.Column('decided_at_index', sa.Integer(), nullable=False),
        sa.Column('decided_at_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(length=10), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('stop_loss_pips', sa.Float(), nullable=True),
        sa.Column('take_profit_pips', sa.Float(), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('pnl', sa.Float(), nullable=True),
        sa.Column('max_favorable', sa.Float(), nullable=False),
        sa.Column('max_adverse', sa.Float(), nullable=False),
        sa.Column('signal_snapshot', app.db.types.PortableJSON(), nullable=False),
        sa.Column('judgment', sa.String(length=20), nullable=True),
        sa.Column('judgment_criteria', app.db.types.PortableJSON(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['replay_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('replay_trades')
    op.drop_index('ix_replay_session_status', table_name='replay_sessions')
    op.drop_table('replay_sessions')
