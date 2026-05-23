from __future__ import annotations

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import create_db_and_tables, get_db
from app.domain import Transaction, TransactionType
from app.repositories import (
    add_transaction as save_transaction,
    add_transactions,
    count_transactions,
    get_market_prices,
    list_transactions as load_transactions,
    upsert_market_price,
)
from app.schemas import DcaRequest, PriceMap, TransactionIn
from app.services.csv_import import parse_transactions_csv
from app.services.dca import calculate_enhanced_dca
from app.services.market_data import YFinanceMarketDataProvider
from app.services.portfolio import summarize_portfolio


app = FastAPI(title="Enhanced DCA Investment Tracker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/transactions")
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
    save_transaction(db, transaction)
    return {"created": True, "count": count_transactions(db)}


@app.post("/api/transactions/upload")
async def upload_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        content = await file.read()
        imported = parse_transactions_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    imported_count = add_transactions(db, imported)
    return {"imported": imported_count, "total": count_transactions(db)}


@app.get("/api/transactions")
def list_transactions(db: Session = Depends(get_db)) -> list[Transaction]:
    return load_transactions(db)


@app.put("/api/market/prices")
def set_prices(payload: PriceMap, db: Session = Depends(get_db)) -> dict[str, object]:
    for ticker, price in payload.prices.items():
        upsert_market_price(db, symbol=ticker, close=price, source="manual")
    return {"updated": len(payload.prices)}


@app.get("/api/market/{ticker}")
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


@app.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db)) -> object:
    return summarize_portfolio(load_transactions(db), get_market_prices(db))


@app.post("/api/dca/recommendation")
def get_dca_recommendation(payload: DcaRequest) -> object:
    return calculate_enhanced_dca(
        base_amount=payload.base_amount,
        market_change_percent=payload.market_change_percent,
        volatility_index=payload.volatility_index,
    )
