from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import MarketSnapshot, Transaction, TransactionType
from app.models import MarketPriceRecord, TransactionRecord


def add_transaction(db: Session, transaction: Transaction, portfolio_id: str = "default") -> TransactionRecord:
    record = TransactionRecord(
        portfolio_id=portfolio_id,
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


def add_transactions(db: Session, transactions: list[Transaction], portfolio_id: str = "default") -> int:
    records = [
        TransactionRecord(
            portfolio_id=portfolio_id,
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


def list_transactions(db: Session, portfolio_id: str = "default") -> list[Transaction]:
    statement = (
        select(TransactionRecord)
        .where(TransactionRecord.portfolio_id == portfolio_id)
        .order_by(TransactionRecord.transaction_date, TransactionRecord.id)
    )
    return [_transaction_from_record(record) for record in db.scalars(statement)]


def count_transactions(db: Session, portfolio_id: str = "default") -> int:
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
