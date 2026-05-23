from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.domain import MarketSnapshot, Transaction, TransactionType
from app.models import AccountRecord, MarketPriceRecord, PortfolioRecord, TransactionRecord


DEFAULT_PORTFOLIO_ID = "default"
DEFAULT_PORTFOLIO_NAME = "Default Portfolio"


def ensure_portfolio(
    db: Session,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    name: str | None = None,
    base_currency: str = "EUR",
) -> PortfolioRecord:
    slug = _normalize_slug(portfolio_id)
    record = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if record is None:
        record = PortfolioRecord(slug=slug, name=name or DEFAULT_PORTFOLIO_NAME, base_currency=base_currency.upper())
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def create_portfolio(
    db: Session,
    name: str,
    slug: str | None = None,
    base_currency: str = "EUR",
) -> PortfolioRecord:
    normalized_slug = _normalize_slug(slug or name)
    record = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == normalized_slug))
    if record is None:
        record = PortfolioRecord(slug=normalized_slug, name=name.strip(), base_currency=base_currency.upper())
        db.add(record)
    else:
        record.name = name.strip()
        record.base_currency = base_currency.upper()
    db.commit()
    db.refresh(record)
    return record


def list_portfolios(db: Session) -> list[PortfolioRecord]:
    ensure_portfolio(db)
    statement = select(PortfolioRecord).order_by(PortfolioRecord.name, PortfolioRecord.slug)
    return list(db.scalars(statement))


def ensure_account(
    db: Session,
    name: str | None,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    institution: str | None = None,
    account_type: str | None = None,
    currency: str = "EUR",
) -> AccountRecord | None:
    normalized_name = _normalize_optional_text(name)
    if normalized_name is None:
        return None

    portfolio = ensure_portfolio(db, portfolio_id)
    statement = select(AccountRecord).where(
        AccountRecord.portfolio_record_id == portfolio.id,
        AccountRecord.name == normalized_name,
    )
    record = db.scalar(statement)
    if record is None:
        record = AccountRecord(
            portfolio_record_id=portfolio.id,
            name=normalized_name,
            institution=_normalize_optional_text(institution),
            account_type=_normalize_optional_text(account_type),
            currency=currency.upper(),
        )
        db.add(record)
    else:
        if institution is not None:
            record.institution = _normalize_optional_text(institution)
        if account_type is not None:
            record.account_type = _normalize_optional_text(account_type)
        record.currency = currency.upper()
    db.commit()
    db.refresh(record)
    return record


def list_accounts(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> list[AccountRecord]:
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return []
    statement = (
        select(AccountRecord)
        .where(AccountRecord.portfolio_record_id == portfolio.id)
        .order_by(AccountRecord.name)
    )
    return list(db.scalars(statement))


def bootstrap_reference_data(db: Session) -> None:
    ensure_portfolio(db)
    statement = select(
        distinct(TransactionRecord.portfolio_id),
        TransactionRecord.account,
        TransactionRecord.currency,
    ).where(TransactionRecord.account.is_not(None))

    for portfolio_id, account_name, currency in db.execute(statement):
        ensure_account(db, name=account_name, portfolio_id=portfolio_id or DEFAULT_PORTFOLIO_ID, currency=currency or "EUR")


def add_transaction(db: Session, transaction: Transaction, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> TransactionRecord:
    portfolio = ensure_portfolio(db, portfolio_id)
    ensure_account(db, name=transaction.account, portfolio_id=portfolio.slug, currency=transaction.currency)
    record = TransactionRecord(
        portfolio_id=portfolio.slug,
        transaction_date=transaction.transaction_date,
        ticker=transaction.ticker.upper(),
        transaction_type=transaction.transaction_type.value,
        quantity=transaction.quantity,
        price=transaction.price,
        fees=transaction.fees,
        currency=transaction.currency.upper(),
        account=transaction.account,
        description=transaction.description,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def add_transactions(db: Session, transactions: list[Transaction], portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> int:
    portfolio = ensure_portfolio(db, portfolio_id)
    for transaction in transactions:
        ensure_account(db, name=transaction.account, portfolio_id=portfolio.slug, currency=transaction.currency)

    records = [
        TransactionRecord(
            portfolio_id=portfolio.slug,
            transaction_date=transaction.transaction_date,
            ticker=transaction.ticker.upper(),
            transaction_type=transaction.transaction_type.value,
            quantity=transaction.quantity,
            price=transaction.price,
            fees=transaction.fees,
            currency=transaction.currency.upper(),
            account=transaction.account,
            description=transaction.description,
        )
        for transaction in transactions
    ]
    db.add_all(records)
    db.commit()
    return len(records)


def list_transactions(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> list[Transaction]:
    slug = _normalize_slug(portfolio_id)
    statement = (
        select(TransactionRecord)
        .where(TransactionRecord.portfolio_id == slug)
        .order_by(TransactionRecord.transaction_date, TransactionRecord.id)
    )
    return [_transaction_from_record(record) for record in db.scalars(statement)]


def count_transactions(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> int:
    return len(list_transactions(db, portfolio_id))


def upsert_market_price(
    db: Session,
    symbol: str,
    close: Decimal,
    previous_close: Decimal | None = None,
    currency: str = "EUR",
    source: str = "manual",
    as_of: datetime | None = None,
) -> MarketPriceRecord:
    normalized_symbol = symbol.upper()
    record = db.scalar(select(MarketPriceRecord).where(MarketPriceRecord.symbol == normalized_symbol))
    if record is None:
        record = MarketPriceRecord(symbol=normalized_symbol, close=close)
        db.add(record)

    record.close = close
    record.previous_close = previous_close
    record.currency = currency.upper()
    record.source = source
    record.as_of = as_of or datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


def get_market_prices(db: Session) -> dict[str, Decimal]:
    statement = select(MarketPriceRecord).order_by(MarketPriceRecord.symbol)
    return {record.symbol: record.close for record in db.scalars(statement)}


def market_snapshot_from_record(record: MarketPriceRecord) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=record.symbol,
        close=record.close,
        previous_close=record.previous_close,
        as_of=record.as_of,
        currency=record.currency,
    )


def _transaction_from_record(record: TransactionRecord) -> Transaction:
    return Transaction(
        transaction_date=record.transaction_date,
        ticker=record.ticker,
        transaction_type=TransactionType(record.transaction_type),
        quantity=record.quantity,
        price=record.price,
        fees=record.fees,
        currency=record.currency,
        account=record.account,
        description=record.description,
    )


def _normalize_slug(value: str | None) -> str:
    raw_value = value or DEFAULT_PORTFOLIO_ID
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw_value.strip().lower()).strip("-")
    return slug or DEFAULT_PORTFOLIO_ID


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
