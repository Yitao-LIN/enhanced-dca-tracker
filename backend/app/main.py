"""@file
@brief FastAPI application, route handlers, and API payload adapters.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db, initialize_database
from app.domain import Transaction, TransactionType
from app.repositories import (
    DEFAULT_PORTFOLIO_ID,
    AllocationTarget,
    add_transaction as save_transaction,
    bootstrap_reference_data,
    count_transactions,
    create_portfolio,
    create_dca_plan,
    delete_dca_plan,
    delete_hidden_security,
    delete_security_mapping,
    delete_transactions_for_ticker,
    ensure_account,
    existing_transaction_fingerprints,
    get_dca_plan as load_dca_plan,
    get_hidden_security_symbols,
    get_market_prices,
    get_security_mapping_symbols,
    import_transactions,
    IntradayMarketPricePoint,
    list_allocation_targets as load_allocation_targets,
    list_intraday_market_prices,
    list_hidden_securities as load_hidden_securities,
    list_market_price_history,
    list_accounts as load_accounts,
    list_dca_plans as load_dca_plans,
    list_portfolios as load_portfolios,
    list_security_mappings as load_security_mappings,
    list_transactions as load_transactions,
    MarketPriceHistoryPoint,
    DcaPlan,
    portfolio_id_for_record_id,
    SecurityMapping,
    transaction_fingerprint,
    replace_allocation_targets,
    update_dca_plan,
    upsert_hidden_security,
    upsert_intraday_market_prices_many,
    upsert_market_price,
    upsert_market_price_history_many,
    upsert_security_mappings,
)
from app.schemas import (
    AccountIn,
    AccountOut,
    AllocationTargetIn,
    AllocationTargetOut,
    DeletedCountOut,
    DcaPlanIn,
    DcaPlanOut,
    DcaPlanUpdateIn,
    DcaRecommendationRequest,
    DcaRecommendationOut,
    HealthOut,
    HiddenSecurityIn,
    HiddenSecurityOut,
    ImportPreviewOut,
    ImportSummaryOut,
    IntradayMarketBackfillOut,
    IntradayMarketBackfillRequest,
    MarketHistoryBackfillOut,
    MarketHistoryBackfillRequest,
    MarketPriceHistoryIn,
    MarketPriceHistoryPointOut,
    MarketQuoteOut,
    PortfolioHistoryPointOut,
    PortfolioIntradayHistoryPointOut,
    PortfolioAnalyticsOut,
    PortfolioIn,
    PortfolioOut,
    PortfolioSummaryOut,
    PriceMap,
    SecurityMappingIn,
    SecurityMappingOut,
    SymbolSearchCandidateOut,
    TransactionCreateOut,
    TransactionIn,
    TransactionOut,
    UpdatedCountOut,
)
from app.services.csv_import import preview_transactions_csv, parse_transactions_csv
from app.services.dca import build_dca_allocation_suggestions, calculate_enhanced_dca, calculate_normal_dca
from app.services.market_data import DEFAULT_BENCHMARKS, YFinanceMarketDataProvider
from app.services.portfolio import summarize_portfolio
from app.services.portfolio_analytics import AllocationTargetInput, build_portfolio_analytics
from app.services.portfolio_history import build_portfolio_history
from app.services.portfolio_intraday import build_portfolio_intraday_history


app = FastAPI(title="Enhanced DCA Investment Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_symbol_search_provider() -> YFinanceMarketDataProvider:
    """@brief Dependency hook for ticker search so tests can inject a stub provider."""
    return YFinanceMarketDataProvider()


@app.on_event("startup")
def on_startup() -> None:
    """@brief Run migrations and bootstrap reference data before serving API requests."""
    initialize_database()
    with SessionLocal() as db:
        bootstrap_reference_data(db)


@app.get("/api/health", response_model=HealthOut)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/portfolios", response_model=list[PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    return [_portfolio_payload(record) for record in load_portfolios(db)]


@app.post("/api/portfolios", response_model=PortfolioOut)
def add_portfolio(payload: PortfolioIn, db: Session = Depends(get_db)) -> dict[str, object]:
    record = create_portfolio(
        db,
        name=payload.name,
        slug=payload.slug,
        base_currency=payload.base_currency,
    )
    return _portfolio_payload(record)


@app.get("/api/accounts", response_model=list[AccountOut])
def list_accounts(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [_account_payload(record) for record in load_accounts(db, portfolio_id=portfolio_id)]


@app.post("/api/accounts", response_model=AccountOut)
def add_account(payload: AccountIn, db: Session = Depends(get_db)) -> dict[str, object]:
    record = ensure_account(
        db,
        name=payload.name,
        portfolio_id=payload.portfolio_id,
        institution=payload.institution,
        account_type=payload.account_type,
        currency=payload.currency,
    )
    return _account_payload(record)


@app.post("/api/transactions", response_model=TransactionCreateOut)
def add_transaction(payload: TransactionIn, db: Session = Depends(get_db)) -> dict[str, object]:
    count_before = count_transactions(db, portfolio_id=payload.portfolio_id)
    transaction = Transaction(
        transaction_date=payload.transaction_date,
        ticker=payload.ticker.upper(),
        transaction_type=TransactionType(payload.transaction_type),
        quantity=payload.quantity,
        price=payload.price,
        fees=payload.fees,
        currency=payload.currency.upper(),
        account=payload.account,
        description=payload.description,
    )
    save_transaction(db, transaction, portfolio_id=payload.portfolio_id)
    count_after = count_transactions(db, portfolio_id=payload.portfolio_id)
    return {"created": count_after > count_before, "count": count_after}


@app.post("/api/transactions/upload", response_model=ImportSummaryOut)
async def upload_transactions(
    file: UploadFile = File(...),
    mappings: str | None = Form(default=None),
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Import a CSV/ZIP upload, saving confirmed mappings before parsing rows."""
    try:
        content = await file.read()
        submitted_mappings = _parse_security_mappings_form(mappings)
        if submitted_mappings:
            upsert_security_mappings(db, submitted_mappings, portfolio_id=portfolio_id)
        security_mappings = get_security_mapping_symbols(db, portfolio_id=portfolio_id)
        imported = parse_transactions_csv(content, security_mappings=security_mappings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = import_transactions(
        db,
        imported,
        portfolio_id=portfolio_id,
        filename=file.filename,
        file_content=content,
    )
    return {
        "import_session_id": summary.import_session_id,
        "portfolio_id": summary.portfolio_id,
        "filename": summary.filename,
        "file_hash": summary.file_hash,
        "row_count": summary.row_count,
        "imported": summary.imported_count,
        "duplicates": summary.duplicate_count,
        "total": summary.total_count,
    }


@app.post("/api/transactions/preview", response_model=ImportPreviewOut, response_model_exclude_none=True)
async def preview_transactions(
    file: UploadFile = File(...),
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
    search_provider: YFinanceMarketDataProvider = Depends(get_symbol_search_provider),
) -> dict[str, object]:
    """@brief Preview a CSV/ZIP upload without writing transactions to the database."""
    content = await file.read()
    security_mappings = get_security_mapping_symbols(db, portfolio_id=portfolio_id)
    preview_rows = preview_transactions_csv(content, security_mappings=security_mappings)
    fingerprints = [
        transaction_fingerprint(row.transaction)
        for row in preview_rows
        if row.transaction is not None
    ]
    existing_fingerprints = existing_transaction_fingerprints(db, portfolio_id, fingerprints)
    seen_in_file: set[str] = set()
    rows = []
    valid_count = 0
    duplicate_count = 0
    error_count = 0
    mapping_count = 0
    suggestion_cache: dict[str, tuple[list[dict[str, object]], str | None]] = {}

    for row in preview_rows:
        # Preview keeps mapping rows editable even if live symbol search is offline.
        if row.security_label is not None:
            mapping_count += 1
            suggestions, search_error = _search_suggestions(row.security_label, suggestion_cache, search_provider)
            rows.append(
                {
                    "row_number": row.row_number,
                    "status": "needs_mapping",
                    "security_label": row.security_label,
                    "error": row.error,
                    "suggestions": suggestions,
                    "search_error": search_error,
                }
            )
            continue

        if row.transaction is None:
            error_count += 1
            rows.append({"row_number": row.row_number, "status": "invalid", "error": row.error})
            continue

        valid_count += 1
        fingerprint = transaction_fingerprint(row.transaction)
        if fingerprint in seen_in_file:
            status = "duplicate_in_file"
            duplicate_count += 1
        elif fingerprint in existing_fingerprints:
            status = "duplicate_existing"
            duplicate_count += 1
        else:
            status = "new"
        seen_in_file.add(fingerprint)
        rows.append(_import_preview_row_payload(row.row_number, status, row.transaction))

    payload = {
        "row_count": len(preview_rows),
        "valid_count": valid_count,
        "duplicate_count": duplicate_count,
        "error_count": error_count,
        "rows": rows,
    }
    if mapping_count:
        payload["mapping_count"] = mapping_count
    return payload


@app.get("/api/transactions", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[Transaction]:
    return load_transactions(db, portfolio_id=portfolio_id)


@app.delete("/api/transactions/{ticker}", response_model=DeletedCountOut)
def remove_transactions_for_ticker(
    ticker: str,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """@brief Delete all imported transactions for one ticker so it can be re-imported cleanly."""
    return {"deleted": delete_transactions_for_ticker(db, ticker=ticker, portfolio_id=portfolio_id)}


@app.get("/api/security-mappings", response_model=list[SecurityMappingOut])
def list_security_mappings(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [_security_mapping_payload(record, portfolio_id) for record in load_security_mappings(db, portfolio_id=portfolio_id)]


@app.put("/api/security-mappings", response_model=SecurityMappingOut)
def set_security_mapping(
    payload: SecurityMappingIn,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        record = upsert_security_mappings(
            db,
            [
                SecurityMapping(
                    security_label=payload.security_label,
                    ticker=payload.ticker,
                    provider=payload.provider,
                    provider_name=payload.provider_name,
                    provider_exchange=payload.provider_exchange,
                    provider_quote_type=payload.provider_quote_type,
                    provider_currency=payload.provider_currency,
                )
            ],
            portfolio_id=portfolio_id,
        )[0]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _security_mapping_payload(record, portfolio_id)


@app.delete("/api/security-mappings", response_model=DeletedCountOut)
def remove_security_mapping(
    security_label: str,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return {"deleted": int(delete_security_mapping(db, security_label=security_label, portfolio_id=portfolio_id))}


@app.get("/api/hidden-securities", response_model=list[HiddenSecurityOut])
def list_hidden_tracking_securities(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [_hidden_security_payload(record, portfolio_id) for record in load_hidden_securities(db, portfolio_id=portfolio_id)]


@app.put("/api/hidden-securities", response_model=HiddenSecurityOut)
def hide_tracking_security(
    payload: HiddenSecurityIn,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Hide a ticker from portfolio tracking without removing its transactions."""
    try:
        record = upsert_hidden_security(db, ticker=payload.ticker, portfolio_id=portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _hidden_security_payload(record, portfolio_id)


@app.delete("/api/hidden-securities", response_model=DeletedCountOut)
def restore_tracking_security(
    ticker: str,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """@brief Restore a hidden ticker to portfolio tracking."""
    return {"deleted": int(delete_hidden_security(db, ticker=ticker, portfolio_id=portfolio_id))}


@app.get("/api/allocation-targets", response_model=list[AllocationTargetOut])
def list_allocation_targets(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """@brief Return saved target allocations for one portfolio."""
    return [_allocation_target_payload(record, portfolio_id) for record in load_allocation_targets(db, portfolio_id=portfolio_id)]


@app.put("/api/allocation-targets", response_model=list[AllocationTargetOut])
def set_allocation_targets(
    payload: list[AllocationTargetIn],
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """@brief Replace a portfolio's target allocations with one validated bulk payload."""
    try:
        records = replace_allocation_targets(
            db,
            [
                AllocationTarget(ticker=target.ticker, target_percent=target.target_percent)
                for target in payload
            ],
            portfolio_id=portfolio_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_allocation_target_payload(record, portfolio_id) for record in records]


@app.get("/api/securities/search", response_model=list[SymbolSearchCandidateOut])
def search_securities(
    query: str,
    limit: int = 5,
    search_provider: YFinanceMarketDataProvider = Depends(get_symbol_search_provider),
) -> list[dict[str, object]]:
    try:
        return [_symbol_search_payload(result, query=query) for result in search_provider.search_symbols(query, limit=limit)]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.put("/api/market/prices", response_model=UpdatedCountOut)
def set_prices(payload: PriceMap, db: Session = Depends(get_db)) -> dict[str, object]:
    for ticker, price in payload.prices.items():
        upsert_market_price(db, symbol=ticker, close=price, source="manual")
    return {"updated": len(payload.prices)}


@app.get("/api/market/{ticker}", response_model=MarketQuoteOut)
def get_market_quote(ticker: str, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        quote = YFinanceMarketDataProvider().quote(ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    upsert_market_price(
        db,
        symbol=quote.symbol,
        close=quote.close,
        previous_close=quote.previous_close,
        currency=quote.currency,
        source="yfinance",
        as_of=quote.as_of,
    )
    return {
        "symbol": quote.symbol,
        "close": quote.close,
        "previous_close": quote.previous_close,
        "change_percent": quote.change_percent,
        "as_of": quote.as_of,
        "currency": quote.currency,
    }


@app.put("/api/market/history", response_model=UpdatedCountOut)
def set_market_price_history(payload: MarketPriceHistoryIn, db: Session = Depends(get_db)) -> dict[str, object]:
    points = [
        MarketPriceHistoryPoint(
            symbol=price.symbol,
            price_date=price.price_date,
            open=price.open,
            high=price.high,
            low=price.low,
            close=price.close,
            adjusted_close=price.adjusted_close,
            volume=price.volume,
            currency=price.currency,
            source=price.source,
        )
        for price in payload.prices
    ]
    return {"updated": upsert_market_price_history_many(db, points)}


@app.get("/api/market/history/{ticker}", response_model=list[MarketPriceHistoryPointOut])
def get_market_price_history(
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    return [
        _market_price_history_payload(record)
        for record in list_market_price_history(
            db,
            symbol=ticker,
            start_date=start_date,
            end_date=end_date,
            source=source,
        )
    ]


@app.post("/api/market/history/backfill", response_model=MarketHistoryBackfillOut)
def backfill_market_price_history(
    payload: MarketHistoryBackfillRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Fetch daily market history for requested symbols and store successful rows."""
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date.")
    symbols = _backfill_symbols(payload)
    provider = YFinanceMarketDataProvider()
    points: list[MarketPriceHistoryPoint] = []
    latest_points: dict[str, MarketPriceHistoryPoint] = {}
    failures: list[dict[str, str]] = []

    for symbol in symbols:
        # Symbol failures are reported per item so a single bad ticker does not block the batch.
        try:
            fetched = provider.historical_prices(
                symbol=symbol,
                start_date=payload.start_date,
                end_date=payload.end_date,
                currency=payload.currency,
                source=payload.source,
            )
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
            continue
        for point in fetched:
            history_point = MarketPriceHistoryPoint(
                symbol=point.symbol,
                price_date=point.price_date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                adjusted_close=point.adjusted_close,
                volume=point.volume,
                currency=point.currency,
                source=point.source,
            )
            points.append(history_point)
            current_latest = latest_points.get(history_point.symbol)
            if current_latest is None or history_point.price_date > current_latest.price_date:
                latest_points[history_point.symbol] = history_point

    updated = upsert_market_price_history_many(db, points)
    for point in latest_points.values():
        upsert_market_price(
            db,
            symbol=point.symbol,
            close=point.adjusted_close or point.close,
            currency=point.currency,
            source=point.source,
            as_of=datetime.combine(point.price_date, time.min, tzinfo=timezone.utc),
            write_history=False,
        )

    return {
        "symbols": symbols,
        "source": payload.source,
        "updated": updated,
        "failures": failures,
    }


@app.post("/api/market/intraday/backfill", response_model=IntradayMarketBackfillOut)
def backfill_intraday_market_prices(
    payload: IntradayMarketBackfillRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Fetch intraday market history for requested symbols and store successful rows."""
    start_at = _naive_utc(payload.start_at)
    end_at = _naive_utc(payload.end_at)
    if start_at > end_at:
        raise HTTPException(status_code=400, detail="start_at must be before or equal to end_at.")
    symbols = _backfill_symbols(payload)
    interval = payload.interval.lower()
    provider = YFinanceMarketDataProvider()
    points: list[IntradayMarketPricePoint] = []
    latest_points: dict[str, IntradayMarketPricePoint] = {}
    failures: list[dict[str, str]] = []

    for symbol in symbols:
        # Intraday provider availability varies by symbol and market hours; keep partial success.
        try:
            fetched = provider.intraday_prices(
                symbol=symbol,
                start_at=start_at,
                end_at=end_at,
                interval=interval,
                currency=payload.currency,
                source=payload.source,
            )
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
            continue
        for point in fetched:
            intraday_point = IntradayMarketPricePoint(
                symbol=point.symbol,
                price_at=point.price_at,
                interval=point.interval,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                adjusted_close=point.adjusted_close,
                volume=point.volume,
                currency=point.currency,
                source=point.source,
            )
            points.append(intraday_point)
            current_latest = latest_points.get(intraday_point.symbol)
            if current_latest is None or intraday_point.price_at > current_latest.price_at:
                latest_points[intraday_point.symbol] = intraday_point

    updated = upsert_intraday_market_prices_many(db, points)
    for point in latest_points.values():
        upsert_market_price(
            db,
            symbol=point.symbol,
            close=point.adjusted_close or point.close,
            currency=point.currency,
            source=point.source,
            as_of=point.price_at,
            write_history=False,
        )

    return {
        "symbols": symbols,
        "source": payload.source,
        "interval": interval,
        "updated": updated,
        "failures": failures,
    }


@app.get("/api/portfolio", response_model=PortfolioSummaryOut)
def get_portfolio(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> object:
    """@brief Return the current visible portfolio summary."""
    transactions = _visible_transactions(db, portfolio_id)
    return summarize_portfolio(transactions, get_market_prices(db))


@app.get("/api/portfolio/analytics", response_model=PortfolioAnalyticsOut)
def get_portfolio_analytics(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Return allocation, activity, and benchmark analytics for visible holdings."""
    hidden_symbols = get_hidden_security_symbols(db, portfolio_id=portfolio_id)
    transactions = _visible_transactions(db, portfolio_id)
    summary = summarize_portfolio(transactions, get_market_prices(db))
    history_points = []
    if transactions:
        symbols = sorted({transaction.ticker for transaction in transactions})
        price_history = {
            symbol: _history_map(list_market_price_history(db, symbol=symbol, start_date=start_date, end_date=end_date))
            for symbol in symbols
        }
        benchmark_history = {
            symbol: _history_map(list_market_price_history(db, symbol=symbol, start_date=start_date, end_date=end_date))
            for symbol in DEFAULT_BENCHMARKS
        }
        history_points = build_portfolio_history(
            transactions,
            prices_by_symbol=price_history,
            benchmarks_by_symbol=benchmark_history,
            start_date=start_date,
            end_date=end_date,
        )

    analytics = build_portfolio_analytics(
        transactions,
        summary=summary,
        allocation_targets=[
            AllocationTargetInput(ticker=record.ticker, target_percent=record.target_percent)
            for record in load_allocation_targets(db, portfolio_id=portfolio_id)
            if record.ticker.upper() not in hidden_symbols
        ],
        history_points=history_points,
        benchmark_names=DEFAULT_BENCHMARKS,
        start_date=start_date,
        end_date=end_date,
    )
    return _portfolio_analytics_payload(analytics)


@app.get("/api/portfolio/history", response_model=list[PortfolioHistoryPointOut])
def get_portfolio_history(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """@brief Return daily portfolio history with normalized benchmark series."""
    transactions = _visible_transactions(db, portfolio_id)
    if not transactions:
        return []
    symbols = sorted({transaction.ticker for transaction in transactions})
    price_history = {
        symbol: _history_map(list_market_price_history(db, symbol=symbol, start_date=start_date, end_date=end_date))
        for symbol in symbols
    }
    benchmark_history = {
        symbol: _history_map(list_market_price_history(db, symbol=symbol, start_date=start_date, end_date=end_date))
        for symbol in DEFAULT_BENCHMARKS
    }
    return [
        _portfolio_history_payload(point)
        for point in build_portfolio_history(
            transactions,
            prices_by_symbol=price_history,
            benchmarks_by_symbol=benchmark_history,
            start_date=start_date,
            end_date=end_date,
        )
    ]


@app.get("/api/portfolio/history/intraday", response_model=list[PortfolioIntradayHistoryPointOut])
def get_portfolio_intraday_history(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    interval: str = "30m",
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """@brief Return intraday portfolio history, falling back to daily prices when needed."""
    start_at = _naive_utc(start_at) if start_at is not None else None
    end_at = _naive_utc(end_at) if end_at is not None else None
    transactions = _visible_transactions(db, portfolio_id)
    if not transactions:
        return []
    normalized_interval = interval.lower()
    symbols = sorted({transaction.ticker for transaction in transactions})
    price_history = {
        symbol: _intraday_history_map(
            list_intraday_market_prices(db, symbol=symbol, start_at=start_at, end_at=end_at, interval=normalized_interval)
        )
        for symbol in symbols
    }
    benchmark_history = {
        symbol: _intraday_history_map(
            list_intraday_market_prices(db, symbol=symbol, start_at=start_at, end_at=end_at, interval=normalized_interval)
        )
        for symbol in DEFAULT_BENCHMARKS
    }
    fallback_timestamps = _intraday_fallback_timestamps(start_at, end_at, normalized_interval)
    if fallback_timestamps:
        # Short chart ranges can still render after daily backfills even when intraday data is missing.
        for symbol, history in price_history.items():
            if not history:
                history.update(_daily_history_fallback_map(db, symbol, fallback_timestamps))
        for symbol, history in benchmark_history.items():
            if not history:
                history.update(_daily_history_fallback_map(db, symbol, fallback_timestamps))
    return [
        _portfolio_intraday_history_payload(point)
        for point in build_portfolio_intraday_history(
            transactions,
            prices_by_symbol=price_history,
            benchmarks_by_symbol=benchmark_history,
            start_at=start_at,
            end_at=end_at,
        )
    ]


@app.get("/api/dca/plans", response_model=list[DcaPlanOut])
def list_dca_strategy_plans(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """@brief Return saved DCA strategy plans for one portfolio."""
    return [
        _dca_plan_payload(record, portfolio_id)
        for record in load_dca_plans(db, portfolio_id=portfolio_id)
    ]


@app.post("/api/dca/plans", response_model=DcaPlanOut)
def create_dca_strategy_plan(payload: DcaPlanIn, db: Session = Depends(get_db)) -> dict[str, object]:
    """@brief Create one saved DCA strategy plan."""
    try:
        record = create_dca_plan(db, _dca_plan_value(payload, portfolio_id=payload.portfolio_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _dca_plan_payload(record, payload.portfolio_id)


@app.get("/api/dca/plans/{plan_id}", response_model=DcaPlanOut)
def get_dca_strategy_plan(plan_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    """@brief Return one saved DCA strategy plan."""
    record = load_dca_plan(db, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="DCA plan not found.")
    return _dca_plan_payload(record, portfolio_id_for_record_id(db, record.portfolio_record_id))


@app.put("/api/dca/plans/{plan_id}", response_model=DcaPlanOut)
def update_dca_strategy_plan(
    plan_id: int,
    payload: DcaPlanUpdateIn,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Update one saved DCA strategy plan."""
    current = load_dca_plan(db, plan_id)
    if current is None:
        raise HTTPException(status_code=404, detail="DCA plan not found.")
    portfolio_id = portfolio_id_for_record_id(db, current.portfolio_record_id)
    try:
        record = update_dca_plan(db, plan_id, _dca_plan_value(payload, portfolio_id=portfolio_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="DCA plan not found.")
    return _dca_plan_payload(record, portfolio_id)


@app.delete("/api/dca/plans/{plan_id}", response_model=DeletedCountOut)
def delete_dca_strategy_plan(plan_id: int, db: Session = Depends(get_db)) -> dict[str, int]:
    """@brief Delete one saved DCA strategy plan."""
    return {"deleted": int(delete_dca_plan(db, plan_id))}


@app.post("/api/dca/plans/{plan_id}/recommendation", response_model=DcaRecommendationOut)
def get_dca_plan_recommendation(
    plan_id: int,
    payload: DcaRecommendationRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """@brief Return a total and optional ticker split from one saved DCA plan."""
    plan = load_dca_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="DCA plan not found.")
    portfolio_id = portfolio_id_for_record_id(db, plan.portfolio_record_id)
    if plan.model_type == "normal":
        recommendation = calculate_normal_dca(base_amount=plan.base_amount)
    elif plan.model_type == "enhanced":
        market_change_percent = payload.market_change_percent
        if market_change_percent is None:
            history = list_market_price_history(
                db,
                symbol=plan.preferred_benchmark,
                start_date=payload.start_date,
                end_date=payload.end_date,
            )
            market_change_percent = _market_change_percent(history)
        recommendation = calculate_enhanced_dca(
            base_amount=plan.base_amount,
            market_change_percent=market_change_percent,
            volatility_index=payload.volatility_index,
            min_multiplier=plan.min_multiplier,
            max_multiplier=plan.max_multiplier,
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported DCA model type.")

    allocation_suggestions = _dca_allocation_suggestions(db, portfolio_id, recommendation.adjusted_amount)
    if plan.model_type == "normal":
        recommendation = calculate_normal_dca(
            base_amount=plan.base_amount,
            allocation_suggestions=allocation_suggestions,
        )
    else:
        recommendation = calculate_enhanced_dca(
            base_amount=plan.base_amount,
            market_change_percent=recommendation.market_change_percent,
            volatility_index=payload.volatility_index,
            min_multiplier=plan.min_multiplier,
            max_multiplier=plan.max_multiplier,
            allocation_suggestions=allocation_suggestions,
        )
    return _dca_recommendation_payload(plan, portfolio_id, recommendation)


def _portfolio_payload(record: object) -> dict[str, object]:
    return {
        "id": record.slug,
        "name": record.name,
        "base_currency": record.base_currency,
        "created_at": record.created_at,
    }


def _import_preview_row_payload(row_number: int, status: str, transaction: Transaction) -> dict[str, object]:
    return {
        "row_number": row_number,
        "status": status,
        "transaction_date": transaction.transaction_date,
        "transaction_type": transaction.transaction_type.value,
        "ticker": transaction.ticker,
        "quantity": transaction.quantity,
        "price": transaction.price,
        "fees": transaction.fees,
        "currency": transaction.currency,
        "account": transaction.account,
        "description": transaction.description,
    }


def _search_suggestions(
    security_label: str,
    suggestion_cache: dict[str, tuple[list[dict[str, object]], str | None]],
    search_provider: YFinanceMarketDataProvider,
) -> tuple[list[dict[str, object]], str | None]:
    if security_label in suggestion_cache:
        return suggestion_cache[security_label]

    search_error = None
    suggestions: list[dict[str, object]] = []
    for query in _security_label_search_queries(security_label):
        try:
            suggestions = [_symbol_search_payload(result, query=query) for result in search_provider.search_symbols(query, limit=5)]
        except Exception as exc:
            search_error = str(exc)
            suggestions = []
            break
        if suggestions:
            break

    suggestion_cache[security_label] = (suggestions, search_error)
    return suggestions, search_error


def _security_label_search_queries(security_label: str) -> list[str]:
    raw_query = re.sub(r"\s+", " ", security_label).strip()
    ascii_query = unicodedata.normalize("NFKD", raw_query).encode("ascii", "ignore").decode("ascii")
    ascii_query = re.sub(r"[^a-zA-Z0-9.&+ -]+", " ", ascii_query)
    ascii_query = re.sub(r"\s+", " ", ascii_query).strip()
    noise_words = {
        "ACC",
        "CAP",
        "CAPITALISATION",
        "DIST",
        "DISTRIBUTION",
        "ETF",
        "EUR",
        "EURO",
        "FR",
        "IE",
        "LU",
        "UCITS",
        "USD",
    }
    compact_query = " ".join(token for token in ascii_query.split() if token.upper() not in noise_words)
    compact_query = re.sub(r"\s+", " ", compact_query).strip()

    queries = []
    for query in (raw_query, ascii_query, compact_query):
        if query and query not in queries:
            queries.append(query)
    return queries


def _symbol_search_payload(result: object, query: str | None = None) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "name": result.name,
        "exchange": result.exchange,
        "quote_type": result.quote_type,
        "currency": result.currency,
        "score": result.score,
        "source": result.source,
        "query": query,
    }


def _parse_security_mappings_form(raw_mappings: str | None) -> list[SecurityMapping]:
    """@brief Parse multipart import mapping JSON into repository value objects."""
    if not raw_mappings:
        return []
    try:
        data = json.loads(raw_mappings)
    except json.JSONDecodeError as exc:
        raise ValueError("Import mappings must be valid JSON.") from exc

    if isinstance(data, dict):
        data = [
            {"security_label": security_label, "ticker": ticker}
            for security_label, ticker in data.items()
        ]
    if not isinstance(data, list):
        raise ValueError("Import mappings must be a JSON array or object.")

    parsed: list[SecurityMapping] = []
    try:
        for item in data:
            payload = SecurityMappingIn.model_validate(item)
            parsed.append(
                SecurityMapping(
                    security_label=payload.security_label,
                    ticker=payload.ticker,
                    provider=payload.provider,
                    provider_name=payload.provider_name,
                    provider_exchange=payload.provider_exchange,
                    provider_quote_type=payload.provider_quote_type,
                    provider_currency=payload.provider_currency,
                )
            )
    except ValidationError as exc:
        raise ValueError(f"Import mappings are invalid: {exc}") from exc
    return parsed


def _account_payload(record: object | None) -> dict[str, object]:
    if record is None:
        raise HTTPException(status_code=400, detail="Account name is required.")
    return {
        "id": record.id,
        "name": record.name,
        "institution": record.institution,
        "account_type": record.account_type,
        "currency": record.currency,
        "created_at": record.created_at,
    }


def _security_mapping_payload(record: object, portfolio_id: str) -> dict[str, object]:
    return {
        "id": record.id,
        "portfolio_id": portfolio_id,
        "security_label": record.display_label,
        "normalized_label": record.normalized_label,
        "ticker": record.ticker,
        "provider": record.provider,
        "provider_name": record.provider_name,
        "provider_exchange": record.provider_exchange,
        "provider_quote_type": record.provider_quote_type,
        "provider_currency": record.provider_currency,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _hidden_security_payload(record: object, portfolio_id: str) -> dict[str, object]:
    return {
        "id": record.id,
        "portfolio_id": portfolio_id,
        "ticker": record.ticker,
        "created_at": record.created_at,
    }


def _allocation_target_payload(record: object, portfolio_id: str) -> dict[str, object]:
    """@brief Serialize an allocation target record with its route portfolio id."""
    return {
        "id": record.id,
        "portfolio_id": portfolio_id,
        "ticker": record.ticker,
        "target_percent": record.target_percent,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _market_price_history_payload(record: object) -> dict[str, object]:
    return {
        "symbol": record.symbol,
        "price_date": record.price_date,
        "open": record.open,
        "high": record.high,
        "low": record.low,
        "close": record.close,
        "adjusted_close": record.adjusted_close,
        "volume": record.volume,
        "currency": record.currency,
        "source": record.source,
    }


def _dca_plan_value(payload: object, portfolio_id: str) -> DcaPlan:
    """@brief Convert a DCA plan request schema into a repository value object."""
    return DcaPlan(
        portfolio_id=portfolio_id,
        name=payload.name,
        model_type=payload.model_type,
        base_amount=payload.base_amount,
        preferred_benchmark=payload.preferred_benchmark,
        min_multiplier=payload.min_multiplier,
        max_multiplier=payload.max_multiplier,
        contribution_frequency=payload.contribution_frequency,
        is_default=payload.is_default,
    )


def _dca_plan_payload(record: object, portfolio_id: str) -> dict[str, object]:
    """@brief Serialize a DCA strategy plan with its public portfolio id."""
    return {
        "id": record.id,
        "portfolio_id": portfolio_id,
        "name": record.name,
        "model_type": record.model_type,
        "base_amount": record.base_amount,
        "preferred_benchmark": record.preferred_benchmark,
        "min_multiplier": record.min_multiplier,
        "max_multiplier": record.max_multiplier,
        "contribution_frequency": record.contribution_frequency,
        "is_default": record.is_default,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _dca_recommendation_payload(plan: object, portfolio_id: str, recommendation: object) -> dict[str, object]:
    """@brief Serialize a DCA recommendation with plan metadata and ticker splits."""
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "model_type": recommendation.model_type,
        "portfolio_id": portfolio_id,
        "base_amount": recommendation.base_amount,
        "adjusted_amount": recommendation.adjusted_amount,
        "multiplier": recommendation.multiplier,
        "market_change_percent": recommendation.market_change_percent,
        "volatility_index": recommendation.volatility_index,
        "reason": recommendation.reason,
        "allocation_suggestions": [
            {
                "ticker": suggestion.ticker,
                "suggested_amount": suggestion.suggested_amount,
                "target_percent": suggestion.target_percent,
                "current_percent": suggestion.current_percent,
                "reason": suggestion.reason,
            }
            for suggestion in recommendation.allocation_suggestions
        ],
    }


def _portfolio_history_payload(point: object) -> dict[str, object]:
    return {
        "date": point.price_date,
        "invested_amount": point.invested_amount,
        "market_value": point.market_value,
        "gain": point.gain,
        "gain_percent": point.gain_percent,
        "benchmarks": point.benchmarks,
    }


def _portfolio_intraday_history_payload(point: object) -> dict[str, object]:
    return {
        "timestamp": point.timestamp,
        "invested_amount": point.invested_amount,
        "market_value": point.market_value,
        "gain": point.gain,
        "gain_percent": point.gain_percent,
        "benchmarks": point.benchmarks,
    }


def _portfolio_analytics_payload(analytics: object) -> dict[str, object]:
    return {
        "total_value": analytics.total_value,
        "total_target_percent": analytics.total_target_percent,
        "unassigned_target_percent": analytics.unassigned_target_percent,
        "allocation_drift": [
            {
                "ticker": row.ticker,
                "name": row.name,
                "current_value": row.current_value,
                "current_percent": row.current_percent,
                "target_percent": row.target_percent,
                "target_value": row.target_value,
                "drift_percent": row.drift_percent,
                "drift_value": row.drift_value,
                "buy_value": row.buy_value,
                "trim_value": row.trim_value,
                "action": row.action,
            }
            for row in analytics.allocation_drift
        ],
        "monthly_activity": [
            {
                "month": row.month,
                "buy_contributions": row.buy_contributions,
                "sell_proceeds": row.sell_proceeds,
                "dividends": row.dividends,
                "fees": row.fees,
                "net_cash_flow": row.net_cash_flow,
            }
            for row in analytics.monthly_activity
        ],
        "benchmark_comparison": [
            {
                "symbol": row.symbol,
                "name": row.name,
                "start_date": row.start_date,
                "end_date": row.end_date,
                "portfolio_start_value": row.portfolio_start_value,
                "portfolio_end_value": row.portfolio_end_value,
                "portfolio_return_percent": row.portfolio_return_percent,
                "benchmark_start_value": row.benchmark_start_value,
                "benchmark_end_value": row.benchmark_end_value,
                "benchmark_return_percent": row.benchmark_return_percent,
                "relative_return_percent": row.relative_return_percent,
            }
            for row in analytics.benchmark_comparison
        ],
    }


def _dca_allocation_suggestions(db: Session, portfolio_id: str, total_amount: Decimal) -> list[object]:
    """@brief Build DCA per-ticker suggestions from visible allocation targets."""
    hidden_symbols = get_hidden_security_symbols(db, portfolio_id=portfolio_id)
    target_records = [
        record
        for record in load_allocation_targets(db, portfolio_id=portfolio_id)
        if record.ticker.upper() not in hidden_symbols
    ]
    if not target_records:
        return []

    transactions = _visible_transactions(db, portfolio_id)
    if not transactions:
        target_rows = [
            SimpleNamespace(
                ticker=record.ticker,
                target_percent=record.target_percent,
                current_percent=Decimal("0.00"),
                buy_value=Decimal("0.00"),
            )
            for record in target_records
        ]
        return build_dca_allocation_suggestions(total_amount, target_rows)

    summary = summarize_portfolio(transactions, get_market_prices(db))
    analytics = build_portfolio_analytics(
        transactions,
        summary=summary,
        allocation_targets=[
            AllocationTargetInput(ticker=record.ticker, target_percent=record.target_percent)
            for record in target_records
        ],
        history_points=[],
        benchmark_names={},
    )
    return build_dca_allocation_suggestions(total_amount, analytics.allocation_drift)


def _visible_transactions(db: Session, portfolio_id: str) -> list[Transaction]:
    """@brief Load portfolio transactions after filtering hidden tracking symbols."""
    hidden_symbols = get_hidden_security_symbols(db, portfolio_id=portfolio_id)
    transactions = load_transactions(db, portfolio_id=portfolio_id)
    if not hidden_symbols:
        return transactions
    return [transaction for transaction in transactions if transaction.ticker.upper() not in hidden_symbols]


def _history_map(records: list[object]) -> dict[date, Decimal]:
    return {record.price_date: record.adjusted_close or record.close for record in records}


def _intraday_history_map(records: list[object]) -> dict[datetime, Decimal]:
    return {record.price_at: record.adjusted_close or record.close for record in records}


def _intraday_fallback_timestamps(start_at: datetime | None, end_at: datetime | None, interval: str) -> list[datetime]:
    """@brief Build bounded timestamps for daily-history fallback in short chart ranges."""
    if start_at is None or end_at is None or start_at > end_at:
        return []
    delta = _intraday_interval_delta(interval)
    timestamp = _ceil_to_interval(start_at, delta)
    timestamps: list[datetime] = []
    while timestamp <= end_at and len(timestamps) < 2000:
        timestamps.append(timestamp)
        timestamp += delta
    return timestamps


def _daily_history_fallback_map(db: Session, symbol: str, timestamps: list[datetime]) -> dict[datetime, Decimal]:
    if not timestamps:
        return {}
    records = list_market_price_history(
        db,
        symbol=symbol,
        start_date=timestamps[0].date(),
        end_date=timestamps[-1].date(),
    )
    if not records:
        return {}
    fallback: dict[datetime, Decimal] = {}
    last_price: Decimal | None = None
    record_index = 0
    for timestamp in timestamps:
        while record_index < len(records) and records[record_index].price_date <= timestamp.date():
            last_price = records[record_index].adjusted_close or records[record_index].close
            record_index += 1
        if last_price is not None:
            fallback[timestamp] = last_price
    return fallback


def _intraday_interval_delta(interval: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([mh])", interval.lower())
    if not match:
        raise HTTPException(status_code=400, detail="interval must use minutes or hours, for example 30m or 1h.")
    amount = int(match.group(1))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="interval must be positive.")
    return timedelta(minutes=amount) if match.group(2) == "m" else timedelta(hours=amount)


def _ceil_to_interval(value: datetime, delta: timedelta) -> datetime:
    day_start = datetime.combine(value.date(), time.min, tzinfo=value.tzinfo)
    interval_seconds = int(delta.total_seconds())
    elapsed_seconds = int((value - day_start).total_seconds())
    rounded_seconds = ((elapsed_seconds + interval_seconds - 1) // interval_seconds) * interval_seconds
    return day_start + timedelta(seconds=rounded_seconds)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _market_change_percent(records: list[object]) -> Decimal:
    if len(records) < 2:
        return Decimal("0")
    first = records[0].adjusted_close or records[0].close
    last = records[-1].adjusted_close or records[-1].close
    if first == 0:
        return Decimal("0")
    return ((last - first) / first * Decimal("100")).quantize(Decimal("0.01"))


def _backfill_symbols(payload: MarketHistoryBackfillRequest) -> list[str]:
    symbols = []
    if payload.symbol:
        symbols.append(payload.symbol)
    if payload.symbols:
        symbols.extend(payload.symbols)
    if not symbols:
        symbols = list(DEFAULT_BENCHMARKS)
    return sorted({symbol.upper() for symbol in symbols})
