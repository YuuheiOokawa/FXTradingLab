"""add signal outcome tracking

Revision ID: 560e5f685016
Revises: dc1b9e1731d9
Create Date: 2026-07-20 09:10:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.db.types


revision: str = '560e5f685016'
down_revision: Union[str, None] = 'dc1b9e1731d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('signals', sa.Column('entry_price', sa.Float(), nullable=False, server_default='0'))
    op.alter_column('signals', 'entry_price', server_default=None)
    op.add_column('signals', sa.Column('outcome_computed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('signals', sa.Column('max_favorable_pips', sa.Float(), nullable=True))
    op.add_column('signals', sa.Column('max_adverse_pips', sa.Float(), nullable=True))
    op.add_column('signals', sa.Column('price_after_horizon_pips', sa.Float(), nullable=True))
    op.add_column('signals', sa.Column('tp_reached', sa.Boolean(), nullable=True))
    op.add_column('signals', sa.Column('sl_reached', sa.Boolean(), nullable=True))
    op.create_unique_constraint(
        'uq_signal_instrument_granularity_ts', 'signals', ['instrument_id', 'granularity', 'ts']
    )
    op.create_index('ix_signal_outcome_pending', 'signals', ['outcome_computed_at', 'ts'])


def downgrade() -> None:
    op.drop_index('ix_signal_outcome_pending', table_name='signals')
    op.drop_constraint('uq_signal_instrument_granularity_ts', 'signals', type_='unique')
    op.drop_column('signals', 'sl_reached')
    op.drop_column('signals', 'tp_reached')
    op.drop_column('signals', 'price_after_horizon_pips')
    op.drop_column('signals', 'max_adverse_pips')
    op.drop_column('signals', 'max_favorable_pips')
    op.drop_column('signals', 'outcome_computed_at')
    op.drop_column('signals', 'entry_price')
