"""@file
@brief Persistence adapters that translate between ORM rows and domain objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import re

from sqlalchemy import distinct, inspect, select, text
from sqlalchemy.orm import Session

from app.domain import MarketSnapshot, Transaction, TransactionType
from app.models import (
    AccountRecord,
    AllocationTargetRecord,
    DcaPlanRecord,
    HiddenSecurityRecord,
    ImportSessionRecord,
    IntradayMarketPriceRecord,
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
DEFAULT_DCA_PLAN_NAME = "Default Enhanced DCA"
DCA_MODEL_TYPES = {"normal", "enhanced"}


@dataclass(frozen=True)
class ImportSummary:
    """@brief Result of a duplicate-aware CSV import session."""

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
    """@brief Repository input for one daily market-history price point."""

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
class IntradayMarketPricePoint:
    """@brief Repository input for one intraday market-history price point."""

    symbol: str
    price_at: datetime
    interval: str
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    adjusted_close: Decimal | None = None
    volume: int | None = None
    currency: str = "EUR"
    source: str = "yfinance"


@dataclass(frozen=True)
class DcaPlan:
    """@brief Value object for a saved DCA strategy plan."""

    portfolio_id: str = DEFAULT_PORTFOLIO_ID
    name: str = DEFAULT_DCA_PLAN_NAME
    model_type: str = "enhanced"
    base_amount: Decimal = DEFAULT_DCA_BASE_AMOUNT
    preferred_benchmark: str = DEFAULT_DCA_BENCHMARK
    min_multiplier: Decimal = Decimal("0.7")
    max_multiplier: Decimal = Decimal("1.5")
    contribution_frequency: str = "monthly"
    is_default: bool = False


@dataclass(frozen=True)
class SecurityMapping:
    """@brief Value object for a Fortuneo security-label to ticker mapping."""

    security_label: str
    ticker: str
    provider: str = "manual"
    provider_name: str | None = None
    provider_exchange: str | None = None
    provider_quote_type: str | None = None
    provider_currency: str | None = None


@dataclass(frozen=True)
class AllocationTarget:
    """@brief Value object for one target allocation percentage."""

    ticker: str
    target_percent: Decimal


def ensure_portfolio(
    db: Session,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    name: str | None = None,
    base_currency: str = "EUR",
) -> PortfolioRecord:
    """@brief Return an existing portfolio or create it with defaults."""
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
    """@brief Create or update a portfolio by normalized slug."""
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
    """@brief Return an existing account or create it inside the selected portfolio."""
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
    """@brief Return normalized security-label to ticker mappings for CSV parsing."""
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
    """@brief Save one security-label mapping, preserving provider metadata when supplied."""
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
    """@brief Save unique security-label mappings in one transaction."""
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
    """@brief Return hidden ticker symbols for a portfolio."""
    return {record.ticker for record in list_hidden_securities(db, portfolio_id=portfolio_id)}


def upsert_hidden_security(db: Session, ticker: str, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> HiddenSecurityRecord:
    """@brief Hide one ticker from tracking views without deleting transactions."""
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
    """@brief Restore one ticker to tracking views."""
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


def list_allocation_targets(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> list[AllocationTargetRecord]:
    """@brief List allocation targets for one portfolio."""
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return []
    statement = (
        select(AllocationTargetRecord)
        .where(AllocationTargetRecord.portfolio_record_id == portfolio.id)
        .order_by(AllocationTargetRecord.ticker)
    )
    return list(db.scalars(statement))


def replace_allocation_targets(
    db: Session,
    targets: list[AllocationTarget],
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
) -> list[AllocationTargetRecord]:
    """@brief Replace all allocation targets for one portfolio after validating percentages."""
    portfolio = ensure_portfolio(db, portfolio_id)
    normalized_targets = _normalize_allocation_targets(targets)
    for record in list_allocation_targets(db, portfolio_id=portfolio.slug):
        db.delete(record)
    records = [
        AllocationTargetRecord(
            portfolio_record_id=portfolio.id,
            ticker=target.ticker,
            target_percent=target.target_percent,
        )
        for target in normalized_targets
    ]
    db.add_all(records)
    db.commit()
    for record in records:
        db.refresh(record)
    return records


def bootstrap_reference_data(db: Session) -> None:
    """@brief Ensure default rows and fingerprints exist for older local databases."""
    ensure_portfolio(db)
    _bootstrap_legacy_dca_settings(db)
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


def list_dca_plans(db: Session, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> list[DcaPlanRecord]:
    """@brief List saved DCA plans for one portfolio."""
    slug = _normalize_slug(portfolio_id)
    portfolio = db.scalar(select(PortfolioRecord).where(PortfolioRecord.slug == slug))
    if portfolio is None:
        return []
    statement = (
        select(DcaPlanRecord)
        .where(DcaPlanRecord.portfolio_record_id == portfolio.id)
        .order_by(DcaPlanRecord.is_default.desc(), DcaPlanRecord.name)
    )
    return list(db.scalars(statement))


def get_dca_plan(db: Session, plan_id: int) -> DcaPlanRecord | None:
    """@brief Load one saved DCA plan by primary key."""
    return db.get(DcaPlanRecord, plan_id)


def create_dca_plan(db: Session, plan: DcaPlan) -> DcaPlanRecord:
    """@brief Create a validated DCA plan and maintain one default plan per portfolio."""
    normalized = _normalize_dca_plan(plan)
    portfolio = ensure_portfolio(db, normalized.portfolio_id)
    _assert_dca_plan_name_available(db, portfolio.id, normalized.name)
    existing_plan = db.scalar(select(DcaPlanRecord.id).where(DcaPlanRecord.portfolio_record_id == portfolio.id))
    is_default = normalized.is_default or existing_plan is None
    if is_default:
        _unset_default_dca_plans(db, portfolio.id)
    record = DcaPlanRecord(
        portfolio_record_id=portfolio.id,
        name=normalized.name,
        model_type=normalized.model_type,
        base_amount=normalized.base_amount,
        preferred_benchmark=normalized.preferred_benchmark,
        min_multiplier=normalized.min_multiplier,
        max_multiplier=normalized.max_multiplier,
        contribution_frequency=normalized.contribution_frequency,
        is_default=is_default,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_dca_plan(db: Session, plan_id: int, plan: DcaPlan) -> DcaPlanRecord | None:
    """@brief Update a saved DCA plan without moving it between portfolios."""
    record = get_dca_plan(db, plan_id)
    if record is None:
        return None
    portfolio_slug = portfolio_id_for_record_id(db, record.portfolio_record_id)
    normalized = _normalize_dca_plan(DcaPlan(**{**plan.__dict__, "portfolio_id": portfolio_slug}))
    _assert_dca_plan_name_available(db, record.portfolio_record_id, normalized.name, exclude_plan_id=record.id)
    existing_other_plan = db.scalar(
        select(DcaPlanRecord.id).where(
            DcaPlanRecord.portfolio_record_id == record.portfolio_record_id,
            DcaPlanRecord.id != record.id,
        )
    )
    is_default = normalized.is_default or existing_other_plan is None
    if is_default:
        _unset_default_dca_plans(db, record.portfolio_record_id, exclude_plan_id=record.id)

    record.name = normalized.name
    record.model_type = normalized.model_type
    record.base_amount = normalized.base_amount
    record.preferred_benchmark = normalized.preferred_benchmark
    record.min_multiplier = normalized.min_multiplier
    record.max_multiplier = normalized.max_multiplier
    record.contribution_frequency = normalized.contribution_frequency
    record.is_default = is_default
    db.commit()
    db.refresh(record)
    return record


def delete_dca_plan(db: Session, plan_id: int) -> bool:
    """@brief Delete a DCA plan and promote another plan if the default was removed."""
    record = get_dca_plan(db, plan_id)
    if record is None:
        return False
    portfolio_record_id = record.portfolio_record_id
    was_default = record.is_default
    db.delete(record)
    db.commit()
    if was_default:
        replacement = db.scalar(
            select(DcaPlanRecord)
            .where(DcaPlanRecord.portfolio_record_id == portfolio_record_id)
            .order_by(DcaPlanRecord.name)
        )
        if replacement is not None:
            replacement.is_default = True
            db.commit()
    return True


def portfolio_id_for_record_id(db: Session, portfolio_record_id: int) -> str:
    """@brief Resolve a portfolio record id back to its public slug."""
    portfolio = db.get(PortfolioRecord, portfolio_record_id)
    return portfolio.slug if portfolio is not None else DEFAULT_PORTFOLIO_ID


def add_transaction(db: Session, transaction: Transaction, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> TransactionRecord:
    """@brief Add one transaction unless its fingerprint already exists in the portfolio."""
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
    """@brief Persist a batch of transactions while skipping duplicates and recording the import."""
    portfolio = ensure_portfolio(db, portfolio_id)
    for transaction in transactions:
        ensure_account(db, name=transaction.account, portfolio_id=portfolio.slug, currency=transaction.currency)

    fingerprints = [transaction_fingerprint(transaction) for transaction in transactions]
    existing_fingerprints = _existing_fingerprints(db, portfolio.slug, fingerprints)
    imported_count = 0
    duplicate_count = 0
    seen_in_import: set[str] = set()

    for transaction, fingerprint in zip(transactions, fingerprints):
        # Fingerprints protect both against old database rows and repeated rows in the same file.
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


def delete_transactions_for_ticker(db: Session, ticker: str, portfolio_id: str = DEFAULT_PORTFOLIO_ID) -> int:
    """@brief Delete all transactions and import fingerprints for one ticker."""
    slug = _normalize_slug(portfolio_id)
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return 0

    records = list(
        db.scalars(
            select(TransactionRecord).where(
                TransactionRecord.portfolio_id == slug,
                TransactionRecord.ticker == normalized_ticker,
            )
        )
    )
    if not records:
        delete_hidden_security(db, normalized_ticker, portfolio_id=slug)
        return 0

    record_ids = [record.id for record in records]
    for fingerprint in db.scalars(
        select(TransactionFingerprintRecord).where(
            TransactionFingerprintRecord.portfolio_id == slug,
            TransactionFingerprintRecord.transaction_record_id.in_(record_ids),
        )
    ):
        db.delete(fingerprint)
    for record in records:
        db.delete(record)

    delete_hidden_security(db, normalized_ticker, portfolio_id=slug)
    db.commit()
    return len(records)


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
    """@brief Save the latest market price and optionally mirror it into daily history."""
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
    """@brief Upsert one daily market-history row by symbol, date, and source."""
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
    """@brief Upsert multiple daily market-history points in one commit."""
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
    """@brief List daily market-history rows filtered by symbol, date range, and source."""
    statement = select(MarketPriceHistoryRecord).where(MarketPriceHistoryRecord.symbol == symbol.upper())
    if start_date is not None:
        statement = statement.where(MarketPriceHistoryRecord.price_date >= start_date)
    if end_date is not None:
        statement = statement.where(MarketPriceHistoryRecord.price_date <= end_date)
    if source is not None:
        statement = statement.where(MarketPriceHistoryRecord.source == source.lower())
    statement = statement.order_by(MarketPriceHistoryRecord.price_date, MarketPriceHistoryRecord.source)
    return list(db.scalars(statement))


def upsert_intraday_market_price(
    db: Session,
    point: IntradayMarketPricePoint,
    commit: bool = True,
) -> IntradayMarketPriceRecord:
    """@brief Upsert one intraday market-history row by symbol, timestamp, interval, and source."""
    normalized_symbol = point.symbol.upper()
    normalized_source = point.source.lower()
    normalized_interval = point.interval.lower()
    statement = select(IntradayMarketPriceRecord).where(
        IntradayMarketPriceRecord.symbol == normalized_symbol,
        IntradayMarketPriceRecord.price_at == point.price_at,
        IntradayMarketPriceRecord.interval == normalized_interval,
        IntradayMarketPriceRecord.source == normalized_source,
    )
    record = db.scalar(statement)
    if record is None:
        record = IntradayMarketPriceRecord(
            symbol=normalized_symbol,
            price_at=point.price_at,
            interval=normalized_interval,
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


def upsert_intraday_market_prices_many(db: Session, points: list[IntradayMarketPricePoint]) -> int:
    """@brief Upsert multiple intraday market-history points in one commit."""
    for point in points:
        upsert_intraday_market_price(db, point, commit=False)
    db.commit()
    return len(points)


def list_intraday_market_prices(
    db: Session,
    symbol: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    interval: str | None = None,
    source: str | None = None,
) -> list[IntradayMarketPriceRecord]:
    """@brief List intraday market-history rows filtered by symbol, timestamp range, interval, and source."""
    statement = select(IntradayMarketPriceRecord).where(IntradayMarketPriceRecord.symbol == symbol.upper())
    if start_at is not None:
        statement = statement.where(IntradayMarketPriceRecord.price_at >= start_at)
    if end_at is not None:
        statement = statement.where(IntradayMarketPriceRecord.price_at <= end_at)
    if interval is not None:
        statement = statement.where(IntradayMarketPriceRecord.interval == interval.lower())
    if source is not None:
        statement = statement.where(IntradayMarketPriceRecord.source == source.lower())
    statement = statement.order_by(IntradayMarketPriceRecord.price_at, IntradayMarketPriceRecord.source)
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
    """@brief Build the stable SHA-256 duplicate key for a transaction."""
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


def _normalize_dca_plan(plan: DcaPlan) -> DcaPlan:
    """@brief Normalize and validate a saved DCA strategy plan."""
    name = re.sub(r"\s+", " ", plan.name).strip()
    if not name:
        raise ValueError("DCA plan name is required.")
    model_type = plan.model_type.strip().lower()
    if model_type not in DCA_MODEL_TYPES:
        raise ValueError("model_type must be one of: enhanced, normal.")
    if plan.base_amount < 0:
        raise ValueError("base_amount must be greater than or equal to 0.")
    if plan.min_multiplier <= 0 or plan.max_multiplier <= 0:
        raise ValueError("DCA multipliers must be greater than 0.")
    if plan.min_multiplier > plan.max_multiplier:
        raise ValueError("min_multiplier must be less than or equal to max_multiplier.")
    preferred_benchmark = plan.preferred_benchmark.strip().upper() or DEFAULT_DCA_BENCHMARK
    contribution_frequency = plan.contribution_frequency.strip().lower() or "monthly"
    return DcaPlan(
        portfolio_id=_normalize_slug(plan.portfolio_id),
        name=name,
        model_type=model_type,
        base_amount=plan.base_amount,
        preferred_benchmark=preferred_benchmark,
        min_multiplier=plan.min_multiplier,
        max_multiplier=plan.max_multiplier,
        contribution_frequency=contribution_frequency,
        is_default=bool(plan.is_default),
    )


def _assert_dca_plan_name_available(
    db: Session,
    portfolio_record_id: int,
    name: str,
    exclude_plan_id: int | None = None,
) -> None:
    """@brief Reject duplicate DCA plan names inside one portfolio."""
    statement = select(DcaPlanRecord).where(
        DcaPlanRecord.portfolio_record_id == portfolio_record_id,
        DcaPlanRecord.name == name,
    )
    if exclude_plan_id is not None:
        statement = statement.where(DcaPlanRecord.id != exclude_plan_id)
    if db.scalar(statement) is not None:
        raise ValueError("DCA plan name already exists for this portfolio.")


def _unset_default_dca_plans(
    db: Session,
    portfolio_record_id: int,
    exclude_plan_id: int | None = None,
) -> None:
    """@brief Clear the default flag from sibling plans before saving a new default."""
    statement = select(DcaPlanRecord).where(DcaPlanRecord.portfolio_record_id == portfolio_record_id)
    if exclude_plan_id is not None:
        statement = statement.where(DcaPlanRecord.id != exclude_plan_id)
    for record in db.scalars(statement):
        record.is_default = False


def _bootstrap_legacy_dca_settings(db: Session) -> None:
    """@brief Seed DCA plans from legacy direct-created dca_settings tables when present."""
    if db.bind is None:
        return
    table_names = set(inspect(db.bind).get_table_names())
    if "dca_settings" not in table_names or "dca_plans" not in table_names:
        return
    rows = db.execute(
        text(
            """
            SELECT
                portfolio_record_id,
                base_amount,
                preferred_benchmark,
                min_multiplier,
                max_multiplier,
                contribution_frequency,
                created_at,
                updated_at
            FROM dca_settings
            """
        )
    ).mappings()
    for row in rows:
        existing_plan_id = db.scalar(
            select(DcaPlanRecord.id).where(DcaPlanRecord.portfolio_record_id == row["portfolio_record_id"])
        )
        if existing_plan_id is not None:
            continue
        db.add(
            DcaPlanRecord(
                portfolio_record_id=row["portfolio_record_id"],
                name=DEFAULT_DCA_PLAN_NAME,
                model_type="enhanced",
                base_amount=row["base_amount"],
                preferred_benchmark=row["preferred_benchmark"],
                min_multiplier=row["min_multiplier"],
                max_multiplier=row["max_multiplier"],
                contribution_frequency=row["contribution_frequency"],
                is_default=True,
                created_at=_coerce_datetime(row["created_at"]),
                updated_at=_coerce_datetime(row["updated_at"]),
            )
        )


def _coerce_datetime(value: object) -> datetime:
    """@brief Convert raw SQLite legacy timestamp values into datetimes."""
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _normalize_allocation_targets(targets: list[AllocationTarget]) -> list[AllocationTarget]:
    """@brief Normalize, de-duplicate, and validate target allocation rows before persistence."""
    unique: dict[str, Decimal] = {}
    for target in targets:
        ticker = target.ticker.strip().upper()
        if not ticker:
            raise ValueError("Ticker is required.")
        if target.target_percent < 0 or target.target_percent > 100:
            raise ValueError("Target percent must be between 0 and 100.")
        unique[ticker] = target.target_percent

    total_percent = sum(unique.values(), Decimal("0"))
    if total_percent > Decimal("100"):
        raise ValueError("Total target percent must be less than or equal to 100.")
    return [
        AllocationTarget(ticker=ticker, target_percent=percent)
        for ticker, percent in sorted(unique.items())
    ]


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
