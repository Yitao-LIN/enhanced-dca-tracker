"""Add DCA settings.

@brief Add portfolio-specific DCA settings.

Revision ID: 20260524_0003
Revises: 20260524_0002
Create Date: 2026-05-24 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0003"
down_revision = "20260524_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dca_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_record_id", sa.Integer(), nullable=False),
        sa.Column("base_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("preferred_benchmark", sa.String(length=32), nullable=False),
        sa.Column("min_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("max_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("contribution_frequency", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_record_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_record_id", name="uq_dca_settings_portfolio"),
    )
    op.create_index(op.f("ix_dca_settings_portfolio_record_id"), "dca_settings", ["portfolio_record_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dca_settings_portfolio_record_id"), table_name="dca_settings")
    op.drop_table("dca_settings")
