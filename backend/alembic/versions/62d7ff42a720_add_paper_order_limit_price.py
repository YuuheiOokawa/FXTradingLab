"""add paper order limit price

Revision ID: 62d7ff42a720
Revises: 0af22da3af76
Create Date: 2026-07-20 23:35:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.db.types


revision: str = '62d7ff42a720'
down_revision: Union[str, None] = '0af22da3af76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('paper_orders', sa.Column('limit_price', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('paper_orders', 'limit_price')
