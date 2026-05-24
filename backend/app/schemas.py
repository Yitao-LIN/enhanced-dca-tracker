from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PortfolioIn(BaseModel):
    name: str
    slug: str | None = None
    base_currency: str = "EUR"


class AccountIn(BaseModel):
    name: str
    portfolio_id: str = "default"
    institution: str | None = None
    account_type: str | None = None
    currency: str = "EUR"


class TransactionIn(BaseModel):
    portfolio_id: str = "default"
    transaction_date: date
    ticker: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    fees: Decimal = Decimal("0")
    currency: str = "EUR"
    account: str | None = None
    description: str | None = None


class PriceMap(BaseModel):
    prices: dict[str, Decimal]


class MarketPriceHistoryPointIn(BaseModel):
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


class MarketPriceHistoryIn(BaseModel):
    prices: list[MarketPriceHistoryPointIn]


class MarketHistoryBackfillRequest(BaseModel):
    symbol: str | None = None
    symbols: list[str] | None = None
    start_date: date
    end_date: date
    currency: str = "USD"
    source: str = "yfinance"


class PortfolioHistoryRequest(BaseModel):
    portfolio_id: str = "default"
    start_date: date | None = None
    end_date: date | None = None


class DcaSettingsIn(BaseModel):
    portfolio_id: str = "default"
    base_amount: Decimal = Decimal("1000")
    preferred_benchmark: str = "^GSPC"
    min_multiplier: Decimal = Decimal("0.7")
    max_multiplier: Decimal = Decimal("1.5")
    contribution_frequency: str = "monthly"


class DcaRequest(BaseModel):
    base_amount: Decimal | None = None
    market_change_percent: Decimal | None = None
    volatility_index: Decimal | None = None
    portfolio_id: str = "default"
    benchmark_symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
