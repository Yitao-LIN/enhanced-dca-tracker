from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import re

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.domain import MarketSnapshot, Transaction, TransactionType
from app.models import (
    AccountRecord,
    ImportSessionRecord,
    MarketPriceRecord,
    PortfolioRecord,
    TransactionFingerprintRecord,
    TransactionRecord,
)


DEFAULT_PORTFOLIO_ID = "default"
DEFAULT_PORTFOLIO_NAME = "Default Portfolio"
DECIMAL_FINGERPRINT_PRECISION = Decimal("0.00000001")


@dataclass(frozen=True)
class ImportSummary:
    import_session_id: int
    portfolio_id: str
    filename: str | None
    file_hash: str
    row_count: int
    imported_count: int
    duplicate_count: int
    total_count: int


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

    for record in db.scalars(select(TransactionRecord).order_by(TransactionRecord.id)):
        transaction = _transaction_from_record(record)
        fingerprint = transaction_fingerprint(transaction)
        existing = db.scalar(
            select(TransactionFingerprintRecord).where(
                TransactionFingerprintRecord.portfolio_id == record.portfolio_id,
                TransactionFingerprintRecord.fingerprint == fingerprint,
            )
        )
        if existing is None:
            db.add(
                TransactionFingerprintRecord(
                    portfolio_id=record.portfolio_id,
                    fingerprint=fingerprint,
                    transaction_record_id=record.id,
                )
            )
    db.commit()


def add_transaction(db: Session, transaction: Transaction, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> TransactionRecord:
    portfolio = ensure_portfolio(db, portfolio_id)
    ensure_account(db, name=transaction.account, portfolio_id=portfolio.slug, currency=transaction.currency)
    fingerprint = transaction_fingerprint(transaction)
    existing = db.scalar(
        select(TransactionRecord)
        .join(
            TransactionFingerprintRecord,
            TransactionFingerprintRecord.transaction_record_id == TransactionRecord.id,
        )
        .where(
            TransactionFingerprintRecord.portfolio_id == portfolio.slug,
            TransactionFingerprintRecord.fingerprint == fingerprint,
        )
    )
    if existing is not None:
        return existing

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
    db.flush()
    db.add(
        TransactionFingerprintRecord(
            portfolio_id=portfolio.slug,
            fingerprint=fingerprint,
            transaction_record_id=record.id,
        )
    )
    db.commit()
    db.refresh(record)
    return record


def add_transactions(db: Session, transactions: list[Transaction], portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> int:
    return import_transactions(db, transactions, portfolio_id=portfolio_id).imported_count


def import_transactions(
    db: Session,
    transactions: list[Transaction],
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    filename: str | None = None,
    file_content: bytes | str | None = None,
    source: str = "csv",
) -> ImportSummary:
    portfolio = ensure_portfolio(db, portfolio_id)
    for transaction in transactions:
        ensure_account(db, name=transaction.account, portfolio_id=portfolio.slug, currency=transaction.currency)

    fingerprints = [transaction_fingerprint(transaction) for transaction in transactions]
    existing_fingerprints = _existing_fingerprints(db, portfolio.slug, fingerprints)
    imported_count = 0
    duplicate_count = 0
    seen_in_import: set[str] = set()

    for transaction, fingerprint in zip(transactions, fingerprints):
        if fingerprint in existing_fingerprints or fingerprint in seen_in_import:
            duplicate_count += 1
            continue

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
        db.flush()
        db.add(
            TransactionFingerprintRecord(
                portfolio_id=portfolio.slug,
                fingerprint=fingerprint,
                transaction_record_id=record.id,
            )
        )
        imported_count += 1
        seen_in_import.add(fingerprint)

    import_session = ImportSessionRecord(
        portfolio_id=portfolio.slug,
        filename=filename,
        file_hash=_hash_import_payload(file_content, fingerprints),
        source=source,
        row_count=len(transactions),
        imported_count=imported_count,
        duplicate_count=duplicate_count,
    )
    db.add(import_session)
    db.commit()
    db.refresh(import_session)

    return ImportSummary(
        import_session_id=import_session.id,
        portfolio_id=portfolio.slug,
        filename=filename,
        file_hash=import_session.file_hash,
        row_count=len(transactions),
        imported_count=imported_count,
        duplicate_count=duplicate_count,
        total_count=count_transactions(db, portfolio_id=portfolio.slug),
    )


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


def transaction_fingerprint(transaction: Transaction) -> str:
    parts = [
        transaction.transaction_date.isoformat(),
        transaction.ticker.strip().upper(),
        transaction.transaction_type.value,
        _decimal_key(transaction.quantity),
        _decimal_key(transaction.price),
        _decimal_key(transaction.fees),
        transaction.currency.strip().upper(),
        (transaction.account or "").strip().upper(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_slug(value: str | None) -> str:
    raw_value = value or DEFAULT_PORTFOLIO_ID
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw_value.strip().lower()).strip("-")
    return slug or DEFAULT_PORTFOLIO_ID


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _decimal_key(value: Decimal) -> str:
    return str(value.quantize(DECIMAL_FINGERPRINT_PRECISION))


def _existing_fingerprints(db: Session, portfolio_id: str, fingerprints: list[str]) -> set[str]:
    if not fingerprints:
        return set()
    statement = select(TransactionFingerprintRecord.fingerprint).where(
        TransactionFingerprintRecord.portfolio_id == portfolio_id,
        TransactionFingerprintRecord.fingerprint.in_(fingerprints),
    )
    return set(db.scalars(statement))


def _hash_import_payload(file_content: bytes | str | None, fingerprints: list[str]) -> str:
    if isinstance(file_content, str):
        payload = file_content.encode("utf-8")
    elif file_content is not None:
        payload = file_content
    else:
        payload = "\n".join(fingerprints).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
