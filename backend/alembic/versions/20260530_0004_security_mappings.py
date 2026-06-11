"""Add security mappings.

@brief Add Fortuneo security-label mappings.

Revision ID: 20260530_0004
Revises: 20260524_0003
Create Date: 2026-05-30 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260530_0004"
down_revision = "20260524_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_record_id", sa.Integer(), nullable=False),
        sa.Column("normalized_label", sa.String(length=255), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("provider_exchange", sa.String(length=64), nullable=True),
        sa.Column("provider_quote_type", sa.String(length=64), nullable=True),
        sa.Column("provider_currency", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_record_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_record_id", "normalized_label", name="uq_security_mappings_portfolio_label"),
    )
    op.create_index(op.f("ix_security_mappings_portfolio_record_id"), "security_mappings", ["portfolio_record_id"], unique=False)
    op.create_index(op.f("ix_security_mappings_normalized_label"), "security_mappings", ["normalized_label"], unique=False)
    op.create_index(op.f("ix_security_mappings_ticker"), "security_mappings", ["ticker"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_security_mappings_ticker"), table_name="security_mappings")
    op.drop_index(op.f("ix_security_mappings_normalized_label"), table_name="security_mappings")
    op.drop_index(op.f("ix_security_mappings_portfolio_record_id"), table_name="security_mappings")
    op.drop_table("security_mappings")
