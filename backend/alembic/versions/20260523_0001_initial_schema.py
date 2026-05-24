"""Initial schema.

Revision ID: 20260523_0001
Revises:
Create Date: 2026-05-23 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_portfolios_slug"),
    )
    op.create_index(op.f("ix_portfolios_slug"), "portfolios", ["slug"], unique=False)

    op.create_table(
        "market_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("previous_close", sa.Numeric(20, 8), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uq_market_prices_symbol"),
    )
    op.create_index(op.f("ix_market_prices_symbol"), "market_prices", ["symbol"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.String(length=64), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("transaction_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("fees", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("account", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transactions_portfolio_id"), "transactions", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_transactions_transaction_date"), "transactions", ["transaction_date"], unique=False)
    op.create_index(op.f("ix_transactions_ticker"), "transactions", ["ticker"], unique=False)
    op.create_index(op.f("ix_transactions_transaction_type"), "transactions", ["transaction_type"], unique=False)

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_record_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("institution", sa.String(length=100), nullable=True),
        sa.Column("account_type", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_record_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_record_id", "name", name="uq_accounts_portfolio_name"),
    )
    op.create_index(op.f("ix_accounts_portfolio_record_id"), "accounts", ["portfolio_record_id"], unique=False)

    op.create_table(
        "import_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_import_sessions_portfolio_id"), "import_sessions", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_import_sessions_file_hash"), "import_sessions", ["file_hash"], unique=False)

    op.create_table(
        "transaction_fingerprints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("transaction_record_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transaction_record_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_id", "fingerprint", name="uq_transaction_fingerprint"),
    )
    op.create_index(op.f("ix_transaction_fingerprints_portfolio_id"), "transaction_fingerprints", ["portfolio_id"], unique=False)
    op.create_index(op.f("ix_transaction_fingerprints_fingerprint"), "transaction_fingerprints", ["fingerprint"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transaction_fingerprints_fingerprint"), table_name="transaction_fingerprints")
    op.drop_index(op.f("ix_transaction_fingerprints_portfolio_id"), table_name="transaction_fingerprints")
    op.drop_table("transaction_fingerprints")

    op.drop_index(op.f("ix_import_sessions_file_hash"), table_name="import_sessions")
    op.drop_index(op.f("ix_import_sessions_portfolio_id"), table_name="import_sessions")
    op.drop_table("import_sessions")

    op.drop_index(op.f("ix_accounts_portfolio_record_id"), table_name="accounts")
    op.drop_table("accounts")

    op.drop_index(op.f("ix_transactions_transaction_type"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_ticker"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_transaction_date"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_portfolio_id"), table_name="transactions")
    op.drop_table("transactions")

    op.drop_index(op.f("ix_market_prices_symbol"), table_name="market_prices")
    op.drop_table("market_prices")

    op.drop_index(op.f("ix_portfolios_slug"), table_name="portfolios")
    op.drop_table("portfolios")
