from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db, initialize_database
from app.domain import Transaction, TransactionType
from app.repositories import (
    DEFAULT_PORTFOLIO_ID,
    DcaSettings,
    add_transaction as save_transaction,
    bootstrap_reference_data,
    count_transactions,
    create_portfolio,
    ensure_account,
    existing_transaction_fingerprints,
    get_dca_settings as load_dca_settings,
    get_market_prices,
    get_security_mapping_symbols,
    import_transactions,
    list_market_price_history,
    list_accounts as load_accounts,
    list_portfolios as load_portfolios,
    list_transactions as load_transactions,
    MarketPriceHistoryPoint,
    SecurityMapping,
    transaction_fingerprint,
    upsert_dca_settings,
    upsert_market_price,
    upsert_market_price_history_many,
    upsert_security_mappings,
)
from app.schemas import (
    AccountIn,
    AccountOut,
    DcaRequest,
    DcaRecommendationOut,
    DcaSettingsIn,
    DcaSettingsOut,
    HealthOut,
    ImportPreviewOut,
    ImportSummaryOut,
    MarketHistoryBackfillOut,
    MarketHistoryBackfillRequest,
    MarketPriceHistoryIn,
    MarketPriceHistoryPointOut,
    MarketQuoteOut,
    PortfolioHistoryPointOut,
    PortfolioIn,
    PortfolioOut,
    PortfolioSummaryOut,
    PriceMap,
    SecurityMappingIn,
    SymbolSearchCandidateOut,
    TransactionCreateOut,
    TransactionIn,
    TransactionOut,
    UpdatedCountOut,
)
from app.services.csv_import import preview_transactions_csv, parse_transactions_csv
from app.services.dca import calculate_enhanced_dca
from app.services.market_data import DEFAULT_BENCHMARKS, YFinanceMarketDataProvider
from app.services.portfolio import summarize_portfolio
from app.services.portfolio_history import build_portfolio_history


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
    return YFinanceMarketDataProvider()


@app.on_event("startup")
def on_startup() -> None:
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
    return {"created": True, "count": count_transactions(db, portfolio_id=payload.portfolio_id)}


@app.post("/api/transactions/upload", response_model=ImportSummaryOut)
async def upload_transactions(
    file: UploadFile = File(...),
    mappings: str | None = Form(default=None),
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
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


@app.get("/api/securities/search", response_model=list[SymbolSearchCandidateOut])
def search_securities(
    query: str,
    limit: int = 5,
    search_provider: YFinanceMarketDataProvider = Depends(get_symbol_search_provider),
) -> list[dict[str, object]]:
    try:
        return [_symbol_search_payload(result) for result in search_provider.search_symbols(query, limit=limit)]
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
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date.")
    symbols = _backfill_symbols(payload)
    provider = YFinanceMarketDataProvider()
    points: list[MarketPriceHistoryPoint] = []

    for symbol in symbols:
        try:
            fetched = provider.historical_prices(
                symbol=symbol,
                start_date=payload.start_date,
                end_date=payload.end_date,
                currency=payload.currency,
                source=payload.source,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Market data backfill failed for {symbol}: {exc}") from exc
        points.extend(
            MarketPriceHistoryPoint(
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
            for point in fetched
        )

    return {
        "symbols": symbols,
        "source": payload.source,
        "updated": upsert_market_price_history_many(db, points),
    }


@app.get("/api/portfolio", response_model=PortfolioSummaryOut)
def get_portfolio(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> object:
    return summarize_portfolio(load_transactions(db, portfolio_id=portfolio_id), get_market_prices(db))


@app.get("/api/portfolio/history", response_model=list[PortfolioHistoryPointOut])
def get_portfolio_history(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    transactions = load_transactions(db, portfolio_id=portfolio_id)
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


@app.get("/api/dca/settings", response_model=DcaSettingsOut)
def get_dca_settings(
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return _dca_settings_payload(load_dca_settings(db, portfolio_id=portfolio_id), portfolio_id)


@app.put("/api/dca/settings", response_model=DcaSettingsOut)
def set_dca_settings(payload: DcaSettingsIn, db: Session = Depends(get_db)) -> dict[str, object]:
    if payload.min_multiplier > payload.max_multiplier:
        raise HTTPException(status_code=400, detail="min_multiplier must be less than or equal to max_multiplier.")
    record = upsert_dca_settings(
        db,
        DcaSettings(
            portfolio_id=payload.portfolio_id,
            base_amount=payload.base_amount,
            preferred_benchmark=payload.preferred_benchmark,
            min_multiplier=payload.min_multiplier,
            max_multiplier=payload.max_multiplier,
            contribution_frequency=payload.contribution_frequency,
        ),
    )
    return _dca_settings_payload(record, payload.portfolio_id)


@app.post("/api/dca/recommendation", response_model=DcaRecommendationOut)
def get_dca_recommendation(payload: DcaRequest, db: Session = Depends(get_db)) -> object:
    settings = load_dca_settings(db, portfolio_id=payload.portfolio_id)
    benchmark_symbol = (payload.benchmark_symbol or settings.preferred_benchmark).upper()
    market_change_percent = payload.market_change_percent
    if market_change_percent is None:
        history = list_market_price_history(
            db,
            symbol=benchmark_symbol,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
        market_change_percent = _market_change_percent(history)

    return calculate_enhanced_dca(
        base_amount=payload.base_amount or settings.base_amount,
        market_change_percent=market_change_percent,
        volatility_index=payload.volatility_index,
        min_multiplier=settings.min_multiplier,
        max_multiplier=settings.max_multiplier,
    )


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
    try:
        suggestions = [_symbol_search_payload(result) for result in search_provider.search_symbols(security_label, limit=5)]
        search_error = None
    except Exception as exc:
        suggestions = []
        search_error = str(exc)
    suggestion_cache[security_label] = (suggestions, search_error)
    return suggestions, search_error


def _symbol_search_payload(result: object) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "name": result.name,
        "exchange": result.exchange,
        "quote_type": result.quote_type,
        "currency": result.currency,
        "score": result.score,
        "source": result.source,
    }


def _parse_security_mappings_form(raw_mappings: str | None) -> list[SecurityMapping]:
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


def _dca_settings_payload(record: object, portfolio_id: str) -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "base_amount": record.base_amount,
        "preferred_benchmark": record.preferred_benchmark,
        "min_multiplier": record.min_multiplier,
        "max_multiplier": record.max_multiplier,
        "contribution_frequency": record.contribution_frequency,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
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


def _history_map(records: list[object]) -> dict[date, Decimal]:
    return {record.price_date: record.adjusted_close or record.close for record in records}


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
