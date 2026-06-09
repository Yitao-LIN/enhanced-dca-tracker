"""Add hidden securities.

Revision ID: 20260607_0005
Revises: 20260530_0004
Create Date: 2026-06-07 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_0005"
down_revision = "20260530_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hidden_securities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_record_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_record_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_record_id", "ticker", name="uq_hidden_securities_portfolio_ticker"),
    )
    op.create_index(op.f("ix_hidden_securities_portfolio_record_id"), "hidden_securities", ["portfolio_record_id"], unique=False)
    op.create_index(op.f("ix_hidden_securities_ticker"), "hidden_securities", ["ticker"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_hidden_securities_ticker"), table_name="hidden_securities")
    op.drop_index(op.f("ix_hidden_securities_portfolio_record_id"), table_name="hidden_securities")
    op.drop_table("hidden_securities")
