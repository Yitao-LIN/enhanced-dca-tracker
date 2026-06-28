"""Add DCA strategy plans.

@brief Replace one-per-portfolio DCA settings with named DCA plans.

Revision ID: 20260614_0008
Revises: 20260614_0007
Create Date: 2026-06-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260614_0008"
down_revision = "20260614_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dca_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_record_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("model_type", sa.String(length=32), nullable=False),
        sa.Column("base_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("preferred_benchmark", sa.String(length=32), nullable=False),
        sa.Column("min_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("max_multiplier", sa.Numeric(10, 4), nullable=False),
        sa.Column("contribution_frequency", sa.String(length=32), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_record_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_record_id", "name", name="uq_dca_plans_portfolio_name"),
    )
    op.create_index(op.f("ix_dca_plans_model_type"), "dca_plans", ["model_type"], unique=False)
    op.create_index(op.f("ix_dca_plans_portfolio_record_id"), "dca_plans", ["portfolio_record_id"], unique=False)

    op.execute(
        """
        INSERT INTO dca_plans (
            portfolio_record_id,
            name,
            model_type,
            base_amount,
            preferred_benchmark,
            min_multiplier,
            max_multiplier,
            contribution_frequency,
            is_default,
            created_at,
            updated_at
        )
        SELECT
            portfolio_record_id,
            'Default Enhanced DCA',
            'enhanced',
            base_amount,
            preferred_benchmark,
            min_multiplier,
            max_multiplier,
            contribution_frequency,
            1,
            created_at,
            updated_at
        FROM dca_settings
        """
    )

    op.drop_index(op.f("ix_dca_settings_portfolio_record_id"), table_name="dca_settings")
    op.drop_table("dca_settings")


def downgrade() -> None:
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
    op.execute(
        """
        INSERT INTO dca_settings (
            portfolio_record_id,
            base_amount,
            preferred_benchmark,
            min_multiplier,
            max_multiplier,
            contribution_frequency,
            created_at,
            updated_at
        )
        SELECT
            portfolio_record_id,
            base_amount,
            preferred_benchmark,
            min_multiplier,
            max_multiplier,
            contribution_frequency,
            created_at,
            updated_at
        FROM dca_plans
        WHERE is_default = 1
        """
    )
    op.drop_index(op.f("ix_dca_plans_portfolio_record_id"), table_name="dca_plans")
    op.drop_index(op.f("ix_dca_plans_model_type"), table_name="dca_plans")
    op.drop_table("dca_plans")
