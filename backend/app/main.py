from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.domain import Transaction, TransactionType
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

TRANSACTIONS: list[Transaction] = []
CURRENT_PRICES: dict[str, Decimal] = {}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/transactions")
def add_transaction(payload: TransactionIn) -> dict[str, object]:
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
    TRANSACTIONS.append(transaction)
    return {"created": True, "count": len(TRANSACTIONS)}


@app.post("/api/transactions/upload")
async def upload_transactions(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        content = await file.read()
        imported = parse_transactions_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    TRANSACTIONS.extend(imported)
    return {"imported": len(imported), "total": len(TRANSACTIONS)}


@app.get("/api/transactions")
def list_transactions() -> list[Transaction]:
    return TRANSACTIONS


@app.put("/api/market/prices")
def set_prices(payload: PriceMap) -> dict[str, object]:
    CURRENT_PRICES.update({ticker.upper(): price for ticker, price in payload.prices.items()})
    return {"updated": len(payload.prices)}


@app.get("/api/market/{ticker}")
def get_market_quote(ticker: str) -> dict[str, object]:
    try:
        quote = YFinanceMarketDataProvider().quote(ticker)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    CURRENT_PRICES[quote.symbol] = quote.close
    return {
        "symbol": quote.symbol,
        "close": quote.close,
        "previous_close": quote.previous_close,
        "change_percent": quote.change_percent,
        "as_of": quote.as_of,
        "currency": quote.currency,
    }


@app.get("/api/portfolio")
def get_portfolio() -> object:
    return summarize_portfolio(TRANSACTIONS, CURRENT_PRICES)


@app.post("/api/dca/recommendation")
def get_dca_recommendation(payload: DcaRequest) -> object:
    return calculate_enhanced_dca(
        base_amount=payload.base_amount,
        market_change_percent=payload.market_change_percent,
        volatility_index=payload.volatility_index,
    )
