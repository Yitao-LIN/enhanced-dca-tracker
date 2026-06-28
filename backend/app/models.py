"""@file
@brief SQLAlchemy ORM table definitions for the tracker database.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortfolioRecord(Base):
    """@brief Persisted portfolio namespace such as the default or long-term portfolio."""

    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("slug", name="uq_portfolios_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(100))
    base_currency: Mapped[str] = mapped_column(String(8), default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AccountRecord(Base):
    """@brief Brokerage/account container scoped to one portfolio."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("portfolio_record_id", "name", name="uq_accounts_portfolio_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_record_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    institution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TransactionRecord(Base):
    """@brief Persisted investment transaction imported from CSV or submitted through the API."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    transaction_type: Mapped[str] = mapped_column(String(16), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    fees: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TransactionFingerprintRecord(Base):
    """@brief Stable duplicate-detection hash for an imported transaction."""

    __tablename__ = "transaction_fingerprints"
    __table_args__ = (UniqueConstraint("portfolio_id", "fingerprint", name="uq_transaction_fingerprint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    transaction_record_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ImportSessionRecord(Base):
    """@brief Audit row summarizing one CSV upload attempt."""

    __tablename__ = "import_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32), default="csv")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SecurityMappingRecord(Base):
    """@brief Saved Fortuneo security-label to ticker mapping scoped to one portfolio."""

    __tablename__ = "security_mappings"
    __table_args__ = (
        UniqueConstraint("portfolio_record_id", "normalized_label", name="uq_security_mappings_portfolio_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_record_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    normalized_label: Mapped[str] = mapped_column(String(255), index=True)
    display_label: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="manual")
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_exchange: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_quote_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class HiddenSecurityRecord(Base):
    """@brief Ticker hidden from tracking views without deleting its transactions."""

    __tablename__ = "hidden_securities"
    __table_args__ = (UniqueConstraint("portfolio_record_id", "ticker", name="uq_hidden_securities_portfolio_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_record_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AllocationTargetRecord(Base):
    """@brief Target portfolio allocation percentage for one ticker."""

    __tablename__ = "allocation_targets"
    __table_args__ = (UniqueConstraint("portfolio_record_id", "ticker", name="uq_allocation_targets_portfolio_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_record_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    target_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MarketPriceRecord(Base):
    """@brief Latest known market price for one symbol."""

    __tablename__ = "market_prices"
    __table_args__ = (UniqueConstraint("symbol", name="uq_market_prices_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    source: Mapped[str] = mapped_column(String(32), default="manual")


class MarketPriceHistoryRecord(Base):
    """@brief Daily historical market price for one symbol, date, and source."""

    __tablename__ = "market_price_history"
    __table_args__ = (UniqueConstraint("symbol", "price_date", "source", name="uq_market_price_history_symbol_date_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    price_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IntradayMarketPriceRecord(Base):
    """@brief Intraday historical market price for one symbol, timestamp, interval, and source."""

    __tablename__ = "market_price_intraday"
    __table_args__ = (
        UniqueConstraint("symbol", "price_at", "interval", "source", name="uq_market_price_intraday_symbol_at_interval_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    price_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="30m", index=True)
    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    source: Mapped[str] = mapped_column(String(32), default="yfinance")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DcaPlanRecord(Base):
    """@brief Named DCA strategy plan scoped to one portfolio."""

    __tablename__ = "dca_plans"
    __table_args__ = (UniqueConstraint("portfolio_record_id", "name", name="uq_dca_plans_portfolio_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_record_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    model_type: Mapped[str] = mapped_column(String(32), default="enhanced", index=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("1000"))
    preferred_benchmark: Mapped[str] = mapped_column(String(32), default="^GSPC")
    min_multiplier: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.7000"))
    max_multiplier: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("1.5000"))
    contribution_frequency: Mapped[str] = mapped_column(String(32), default="monthly")
    is_default: Mapped[bool] = mapped_column(Boolean(), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
