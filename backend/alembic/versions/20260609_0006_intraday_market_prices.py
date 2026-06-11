"""Add intraday market price history.

Revision ID: 20260609_0006
Revises: 20260607_0005
Create Date: 2026-06-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_0006"
down_revision = "20260607_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_price_intraday",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("price_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
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
        sa.UniqueConstraint(
            "symbol",
            "price_at",
            "interval",
            "source",
            name="uq_market_price_intraday_symbol_at_interval_source",
        ),
    )
    op.create_index(op.f("ix_market_price_intraday_interval"), "market_price_intraday", ["interval"], unique=False)
    op.create_index(op.f("ix_market_price_intraday_price_at"), "market_price_intraday", ["price_at"], unique=False)
    op.create_index(op.f("ix_market_price_intraday_symbol"), "market_price_intraday", ["symbol"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_market_price_intraday_symbol"), table_name="market_price_intraday")
    op.drop_index(op.f("ix_market_price_intraday_price_at"), table_name="market_price_intraday")
    op.drop_index(op.f("ix_market_price_intraday_interval"), table_name="market_price_intraday")
    op.drop_table("market_price_intraday")
