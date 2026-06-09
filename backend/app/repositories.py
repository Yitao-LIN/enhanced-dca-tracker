from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import re

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.domain import MarketSnapshot, Transaction, TransactionType
from app.models import (
    AccountRecord,
    DcaSettingsRecord,
    HiddenSecurityRecord,
    ImportSessionRecord,
    MarketPriceRecord,
    MarketPriceHistoryRecord,
    PortfolioRecord,
    SecurityMappingRecord,
    TransactionFingerprintRecord,
    TransactionRecord,
)
from app.services.csv_import import normalize_security_label


DEFAULT_PORTFOLIO_ID = "default"
DEFAULT_PORTFOLIO_NAME = "Default Portfolio"
DECIMAL_FINGERPRINT_PRECISION = Decimal("0.00000001")
DEFAULT_DCA_BASE_AMOUNT = Decimal("1000")
DEFAULT_DCA_BENCHMARK = "^GSPC"


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


@dataclass(frozen=True)
class MarketPriceHistoryPoint:
    symbol: str
    price_date: date
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    adjusted_close: Decimal | None = None
    volume: int | None = None
    currency: str = "EUR"
    source: str = "manual"


@dataclass(frozen=True)
class DcaSettings:
    portfolio_id: str = DEFAULT_PORTFOLIO_ID
    base_amount: Decimal = DEFAULT_DCA_BASE_AMOUNT
    preferred_benchmark: str = DEFAULT_DCA_BENCHMARK
    min_multiplier: Decimal = Decimal("0.7")
    max_multiplier: Decimal = Decimal("1.5")
    contribution_frequency: str = "monthly"


@dataclass(frozen=True)
class SecurityMapping:
    security_label: str
    ticker: str
    provider: str = "manual"
    provider_name: str | None = None
    provider_exchange: str | None = None
    provider_quote_type: str | None = None
    provider_currency: str | None = None


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


def get_security_mapping_symbols(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> dict[str, str]:
    return {
        record.normalized_label: record.ticker
        for record in list_security_mappings(db, portfolio_id=portfolio_id)
    }


def list_security_mappings(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> list[SecurityMappingRecord]:
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return []
    statement = (
        select(SecurityMappingRecord)
        .where(SecurityMappingRecord.portfolio_record_id == portfolio.id)
        .order_by(SecurityMappingRecord.display_label)
    )
    return list(db.scalars(statement))


def delete_security_mapping(db: Session, security_label: str, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> bool:
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return False

    normalized_label = normalize_security_label(security_label)
    if not normalized_label:
        return False

    record = db.scalar(
        select(SecurityMappingRecord).where(
            SecurityMappingRecord.portfolio_record_id == portfolio.id,
            SecurityMappingRecord.normalized_label == normalized_label,
        )
    )
    if record is None:
        return False

    db.delete(record)
    db.commit()
    return True


def upsert_security_mapping(
    db: Session,
    mapping: SecurityMapping,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    commit: bool = True,
) -> SecurityMappingRecord:
    portfolio = ensure_portfolio(db, portfolio_id)
    display_label = mapping.security_label.strip()
    normalized_label = normalize_security_label(display_label)
    if not normalized_label:
        raise ValueError("Security label is required.")
    ticker = mapping.ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker is required.")

    statement = select(SecurityMappingRecord).where(
        SecurityMappingRecord.portfolio_record_id == portfolio.id,
        SecurityMappingRecord.normalized_label == normalized_label,
    )
    record = db.scalar(statement)
    if record is None:
        record = SecurityMappingRecord(
            portfolio_record_id=portfolio.id,
            normalized_label=normalized_label,
            display_label=display_label,
            ticker=ticker,
        )
        db.add(record)

    record.display_label = display_label
    record.ticker = ticker
    record.provider = (mapping.provider or "manual").strip().lower()
    record.provider_name = _normalize_optional_text(mapping.provider_name)
    record.provider_exchange = _normalize_optional_text(mapping.provider_exchange)
    record.provider_quote_type = _normalize_optional_text(mapping.provider_quote_type)
    record.provider_currency = _normalize_optional_text(mapping.provider_currency)
    if record.provider_currency is not None:
        record.provider_currency = record.provider_currency.upper()

    if commit:
        db.commit()
        db.refresh(record)
    return record


def upsert_security_mappings(
    db: Session,
    mappings: list[SecurityMapping],
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
) -> list[SecurityMappingRecord]:
    unique_mappings: dict[str, SecurityMapping] = {}
    for mapping in mappings:
        normalized_label = normalize_security_label(mapping.security_label)
        if normalized_label:
            unique_mappings[normalized_label] = mapping

    records = [
        upsert_security_mapping(db, mapping, portfolio_id=portfolio_id, commit=False)
        for mapping in unique_mappings.values()
    ]
    db.commit()
    for record in records:
        db.refresh(record)
    return records


def list_hidden_securities(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> list[HiddenSecurityRecord]:
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return []
    statement = (
        select(HiddenSecurityRecord)
        .where(HiddenSecurityRecord.portfolio_record_id == portfolio.id)
        .order_by(HiddenSecurityRecord.ticker)
    )
    return list(db.scalars(statement))


def get_hidden_security_symbols(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> set[str]:
    return {record.ticker for record in list_hidden_securities(db, portfolio_id=portfolio_id)}


def upsert_hidden_security(db: Session, ticker: str, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> HiddenSecurityRecord:
    portfolio = ensure_portfolio(db, portfolio_id)
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker is required.")

    record = db.scalar(
        select(HiddenSecurityRecord).where(
            HiddenSecurityRecord.portfolio_record_id == portfolio.id,
            HiddenSecurityRecord.ticker == normalized_ticker,
        )
    )
    if record is None:
        record = HiddenSecurityRecord(portfolio_record_id=portfolio.id, ticker=normalized_ticker)
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


def delete_hidden_security(db: Session, ticker: str, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> bool:
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return False

    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return False

    record = db.scalar(
        select(HiddenSecurityRecord).where(
            HiddenSecurityRecord.portfolio_record_id == portfolio.id,
            HiddenSecurityRecord.ticker == normalized_ticker,
        )
    )
    if record is None:
        return False

    db.delete(record)
    db.commit()
    return True


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


def get_dca_settings(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> DcaSettingsRecord:
    portfolio = ensure_portfolio(db, portfolio_id)
    record = db.scalar(select(DcaSettingsRecord).where(DcaSettingsRecord.portfolio_record_id == portfolio.id))
    if record is None:
        record = DcaSettingsRecord(
            portfolio_record_id=portfolio.id,
            base_amount=DEFAULT_DCA_BASE_AMOUNT,
            preferred_benchmark=DEFAULT_DCA_BENCHMARK,
            min_multiplier=Decimal("0.7"),
            max_multiplier=Decimal("1.5"),
            contribution_frequency="monthly",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def upsert_dca_settings(db: Session, settings: DcaSettings) -> DcaSettingsRecord:
    portfolio = ensure_portfolio(db, settings.portfolio_id)
    record = db.scalar(select(DcaSettingsRecord).where(DcaSettingsRecord.portfolio_record_id == portfolio.id))
    if record is None:
        record = DcaSettingsRecord(portfolio_record_id=portfolio.id)
        db.add(record)

    record.base_amount = settings.base_amount
    record.preferred_benchmark = settings.preferred_benchmark.upper()
    record.min_multiplier = settings.min_multiplier
    record.max_multiplier = settings.max_multiplier
    record.contribution_frequency = settings.contribution_frequency.lower()
    db.commit()
    db.refresh(record)
    return record


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
    write_history: bool = True,
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
    if write_history:
        upsert_market_price_history(
            db,
            MarketPriceHistoryPoint(
                symbol=normalized_symbol,
                price_date=(as_of or datetime.now(timezone.utc)).date(),
                close=close,
                currency=currency,
                source=source,
            ),
            commit=True,
        )
    return record


def get_market_prices(db: Session) -> dict[str, Decimal]:
    statement = select(MarketPriceRecord).order_by(MarketPriceRecord.symbol)
    return {record.symbol: record.close for record in db.scalars(statement)}


def upsert_market_price_history(
    db: Session,
    point: MarketPriceHistoryPoint,
    commit: bool = True,
) -> MarketPriceHistoryRecord:
    normalized_symbol = point.symbol.upper()
    normalized_source = point.source.lower()
    statement = select(MarketPriceHistoryRecord).where(
        MarketPriceHistoryRecord.symbol == normalized_symbol,
        MarketPriceHistoryRecord.price_date == point.price_date,
        MarketPriceHistoryRecord.source == normalized_source,
    )
    record = db.scalar(statement)
    if record is None:
        record = MarketPriceHistoryRecord(
            symbol=normalized_symbol,
            price_date=point.price_date,
            close=point.close,
        )
        db.add(record)

    record.open = point.open
    record.high = point.high
    record.low = point.low
    record.close = point.close
    record.adjusted_close = point.adjusted_close
    record.volume = point.volume
    record.currency = point.currency.upper()
    record.source = normalized_source

    if commit:
        db.commit()
        db.refresh(record)
    return record


def upsert_market_price_history_many(db: Session, points: list[MarketPriceHistoryPoint]) -> int:
    for point in points:
        upsert_market_price_history(db, point, commit=False)
    db.commit()
    return len(points)


def list_market_price_history(
    db: Session,
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
) -> list[MarketPriceHistoryRecord]:
    statement = select(MarketPriceHistoryRecord).where(MarketPriceHistoryRecord.symbol == symbol.upper())
    if start_date is not None:
        statement = statement.where(MarketPriceHistoryRecord.price_date >= start_date)
    if end_date is not None:
        statement = statement.where(MarketPriceHistoryRecord.price_date <= end_date)
    if source is not None:
        statement = statement.where(MarketPriceHistoryRecord.source == source.lower())
    statement = statement.order_by(MarketPriceHistoryRecord.price_date, MarketPriceHistoryRecord.source)
    return list(db.scalars(statement))


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


def existing_transaction_fingerprints(db: Session, portfolio_id: str, fingerprints: list[str]) -> set[str]:
    return _existing_fingerprints(db, _normalize_slug(portfolio_id), fingerprints)


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
