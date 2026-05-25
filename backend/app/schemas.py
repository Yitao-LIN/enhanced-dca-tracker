from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class HealthOut(ApiModel):
    status: Literal["ok"]


class PortfolioOut(ApiModel):
    id: str
    name: str
    base_currency: str
    created_at: datetime


class AccountOut(ApiModel):
    id: int
    name: str
    institution: str | None = None
    account_type: str | None = None
    currency: str
    created_at: datetime


class TransactionOut(ApiModel):
    transaction_date: date
    ticker: str
    transaction_type: str
    quantity: Decimal
    price: Decimal
    fees: Decimal
    currency: str
    account: str | None = None
    description: str | None = None


class TransactionCreateOut(ApiModel):
    created: bool
    count: int


class ImportSummaryOut(ApiModel):
    import_session_id: int
    portfolio_id: str
    filename: str | None = None
    file_hash: str
    row_count: int
    imported: int
    duplicates: int
    total: int


class UpdatedCountOut(ApiModel):
    updated: int


class MarketQuoteOut(ApiModel):
    symbol: str
    close: Decimal
    previous_close: Decimal | None = None
    change_percent: Decimal
    as_of: datetime
    currency: str


class MarketPriceHistoryPointOut(ApiModel):
    symbol: str
    price_date: date
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    adjusted_close: Decimal | None = None
    volume: int | None = None
    currency: str
    source: str


class MarketHistoryBackfillOut(ApiModel):
    symbols: list[str]
    source: str
    updated: int


class PricedHoldingOut(ApiModel):
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal
    invested_amount: Decimal
    market_value: Decimal
    unrealized_gain: Decimal
    unrealized_gain_percent: Decimal
    allocation_percent: Decimal
    currency: str


class PortfolioSummaryOut(ApiModel):
    total_value: Decimal
    total_invested: Decimal
    total_gain: Decimal
    total_gain_percent: Decimal
    cash_flow: Decimal
    holdings: list[PricedHoldingOut]


class PortfolioHistoryPointOut(ApiModel):
    date: date
    invested_amount: Decimal
    market_value: Decimal
    gain: Decimal
    gain_percent: Decimal
    benchmarks: dict[str, Decimal]


class DcaSettingsOut(ApiModel):
    portfolio_id: str
    base_amount: Decimal
    preferred_benchmark: str
    min_multiplier: Decimal
    max_multiplier: Decimal
    contribution_frequency: str
    created_at: datetime
    updated_at: datetime


class DcaRecommendationOut(ApiModel):
    base_amount: Decimal
    adjusted_amount: Decimal
    multiplier: Decimal
    market_change_percent: Decimal
    volatility_index: Decimal | None = None
    reason: str
