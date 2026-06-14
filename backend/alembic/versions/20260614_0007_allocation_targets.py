"""Add allocation targets.

@brief Add per-portfolio target allocation percentages.

Revision ID: 20260614_0007
Revises: 20260609_0006
Create Date: 2026-06-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260614_0007"
down_revision = "20260609_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allocation_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_record_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("target_percent", sa.Numeric(10, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_record_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_record_id", "ticker", name="uq_allocation_targets_portfolio_ticker"),
    )
    op.create_index(op.f("ix_allocation_targets_portfolio_record_id"), "allocation_targets", ["portfolio_record_id"], unique=False)
    op.create_index(op.f("ix_allocation_targets_ticker"), "allocation_targets", ["ticker"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_allocation_targets_ticker"), table_name="allocation_targets")
    op.drop_index(op.f("ix_allocation_targets_portfolio_record_id"), table_name="allocation_targets")
    op.drop_table("allocation_targets")
