"""Add market price history.

@brief Add daily market price history.

Revision ID: 20260524_0002
Revises: 20260523_0001
Create Date: 2026-05-24 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0002"
down_revision = "20260523_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=True),
        sa.Column("high", sa.Numeric(20, 8), nullable=True),
        sa.Column("low", sa.Numeric(20, 8), nullable=True),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(20, 8), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "price_date", "source", name="uq_market_price_history_symbol_date_source"),
    )
    op.create_index(op.f("ix_market_price_history_symbol"), "market_price_history", ["symbol"], unique=False)
    op.create_index(op.f("ix_market_price_history_price_date"), "market_price_history", ["price_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_market_price_history_price_date"), table_name="market_price_history")
    op.drop_index(op.f("ix_market_price_history_symbol"), table_name="market_price_history")
    op.drop_table("market_price_history")
