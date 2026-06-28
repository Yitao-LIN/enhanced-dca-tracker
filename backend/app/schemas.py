"""@file
@brief Pydantic request and response schemas for FastAPI route contracts.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """@brief Base response model configured for ORM-compatible serialization."""

    model_config = ConfigDict(from_attributes=True)


class PortfolioIn(BaseModel):
    """@brief Request payload for creating or updating a portfolio."""

    name: str
    slug: str | None = None
    base_currency: str = "EUR"


class AccountIn(BaseModel):
    """@brief Request payload for creating or resolving an account."""

    name: str
    portfolio_id: str = "default"
    institution: str | None = None
    account_type: str | None = None
    currency: str = "EUR"


class TransactionIn(BaseModel):
    """@brief Request payload for manually adding a transaction."""

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
    """@brief Request payload for bulk latest-price updates."""

    prices: dict[str, Decimal]


class MarketPriceHistoryPointIn(BaseModel):
    """@brief One daily market-history price point submitted to the API."""

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
    """@brief Bulk daily market-history update payload."""

    prices: list[MarketPriceHistoryPointIn]


class MarketHistoryBackfillRequest(BaseModel):
    """@brief Daily Yahoo Finance backfill request for one or more symbols."""

    symbol: str | None = None
    symbols: list[str] | None = None
    start_date: date
    end_date: date
    currency: str = "USD"
    source: str = "yfinance"


class IntradayMarketBackfillRequest(BaseModel):
    """@brief Intraday Yahoo Finance backfill request for one or more symbols."""

    symbol: str | None = None
    symbols: list[str] | None = None
    start_at: datetime
    end_at: datetime
    interval: str = "30m"
    currency: str = "USD"
    source: str = "yfinance"


class SecurityMappingIn(BaseModel):
    """@brief Request payload for saving one Fortuneo label-to-ticker mapping."""

    security_label: str
    ticker: str
    provider: str = "manual"
    provider_name: str | None = None
    provider_exchange: str | None = None
    provider_quote_type: str | None = None
    provider_currency: str | None = None


class SecurityMappingOut(ApiModel):
    """@brief Response payload for a saved security mapping."""

    id: int
    portfolio_id: str
    security_label: str
    normalized_label: str
    ticker: str
    provider: str
    provider_name: str | None = None
    provider_exchange: str | None = None
    provider_quote_type: str | None = None
    provider_currency: str | None = None
    created_at: datetime
    updated_at: datetime


class HiddenSecurityIn(BaseModel):
    """@brief Request payload for hiding one ticker from tracking views."""

    ticker: str


class HiddenSecurityOut(ApiModel):
    """@brief Response payload for a hidden ticker."""

    id: int
    portfolio_id: str
    ticker: str
    created_at: datetime


class AllocationTargetIn(BaseModel):
    """@brief Request payload for one target allocation percentage."""

    ticker: str
    target_percent: Decimal


class AllocationTargetOut(ApiModel):
    """@brief Persisted allocation target response."""

    id: int
    portfolio_id: str
    ticker: str
    target_percent: Decimal
    created_at: datetime
    updated_at: datetime


class PortfolioHistoryRequest(BaseModel):
    """@brief Shared portfolio-history request shape for documented clients."""

    portfolio_id: str = "default"
    start_date: date | None = None
    end_date: date | None = None


class DcaPlanIn(BaseModel):
    """@brief Request payload for creating a saved DCA strategy plan."""

    model_config = ConfigDict(protected_namespaces=())

    portfolio_id: str = "default"
    name: str = "Default Enhanced DCA"
    model_type: Literal["normal", "enhanced"] = "enhanced"
    base_amount: Decimal = Decimal("1000")
    preferred_benchmark: str = "^GSPC"
    min_multiplier: Decimal = Decimal("0.7")
    max_multiplier: Decimal = Decimal("1.5")
    contribution_frequency: str = "monthly"
    is_default: bool = False


class DcaPlanUpdateIn(BaseModel):
    """@brief Request payload for updating an existing DCA strategy plan."""

    model_config = ConfigDict(protected_namespaces=())

    name: str = "Default Enhanced DCA"
    model_type: Literal["normal", "enhanced"] = "enhanced"
    base_amount: Decimal = Decimal("1000")
    preferred_benchmark: str = "^GSPC"
    min_multiplier: Decimal = Decimal("0.7")
    max_multiplier: Decimal = Decimal("1.5")
    contribution_frequency: str = "monthly"
    is_default: bool = False


class DcaRecommendationRequest(BaseModel):
    """@brief Request payload for computing a recommendation from a saved plan."""

    market_change_percent: Decimal | None = None
    volatility_index: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None


class HealthOut(ApiModel):
    """@brief Health-check response."""

    status: Literal["ok"]


class PortfolioOut(ApiModel):
    """@brief Portfolio response."""

    id: str
    name: str
    base_currency: str
    created_at: datetime


class AccountOut(ApiModel):
    """@brief Account response."""

    id: int
    name: str
    institution: str | None = None
    account_type: str | None = None
    currency: str
    created_at: datetime


class TransactionOut(ApiModel):
    """@brief Transaction response."""

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
    """@brief Manual transaction creation result."""

    created: bool
    count: int


class ImportSummaryOut(ApiModel):
    """@brief CSV upload import summary."""

    import_session_id: int
    portfolio_id: str
    filename: str | None = None
    file_hash: str
    row_count: int
    imported: int
    duplicates: int
    total: int


class SymbolSearchCandidateOut(ApiModel):
    """@brief Candidate ticker returned by security-label search."""

    symbol: str
    name: str | None = None
    exchange: str | None = None
    quote_type: str | None = None
    currency: str | None = None
    score: float | None = None
    source: str
    query: str | None = None


class ImportPreviewRowOut(ApiModel):
    """@brief One row in a CSV import preview, including status and mapping suggestions."""

    row_number: int
    status: Literal["new", "duplicate_in_file", "duplicate_existing", "invalid", "needs_mapping"]
    transaction_date: date | None = None
    transaction_type: str | None = None
    ticker: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fees: Decimal | None = None
    currency: str | None = None
    account: str | None = None
    description: str | None = None
    error: str | None = None
    security_label: str | None = None
    suggestions: list[SymbolSearchCandidateOut] | None = None
    search_error: str | None = None


class ImportPreviewOut(ApiModel):
    """@brief Full CSV import preview response."""

    row_count: int
    valid_count: int
    duplicate_count: int
    error_count: int
    mapping_count: int | None = None
    rows: list[ImportPreviewRowOut]


class UpdatedCountOut(ApiModel):
    """@brief Generic response for bulk update counts."""

    updated: int


class DeletedCountOut(ApiModel):
    """@brief Generic response for delete counts."""

    deleted: int


class MarketQuoteOut(ApiModel):
    """@brief Live quote response."""

    symbol: str
    close: Decimal
    previous_close: Decimal | None = None
    change_percent: Decimal
    as_of: datetime
    currency: str


class MarketPriceHistoryPointOut(ApiModel):
    """@brief Daily market-history response point."""

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
    """@brief Daily market-history backfill result."""

    symbols: list[str]
    source: str
    updated: int
    failures: list[dict[str, str]] = []


class IntradayMarketBackfillOut(ApiModel):
    """@brief Intraday market-history backfill result."""

    symbols: list[str]
    source: str
    interval: str
    updated: int
    failures: list[dict[str, str]] = []


class PricedHoldingOut(ApiModel):
    """@brief Priced holding response embedded in portfolio summaries."""

    ticker: str
    name: str | None = None
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
    """@brief Portfolio summary response."""

    total_value: Decimal
    total_invested: Decimal
    total_gain: Decimal
    total_gain_percent: Decimal
    cash_flow: Decimal
    holdings: list[PricedHoldingOut]


class PortfolioHistoryPointOut(ApiModel):
    """@brief Daily portfolio-history response point."""

    date: date
    invested_amount: Decimal
    market_value: Decimal
    gain: Decimal
    gain_percent: Decimal
    benchmarks: dict[str, Decimal]


class PortfolioIntradayHistoryPointOut(ApiModel):
    """@brief Intraday portfolio-history response point."""

    timestamp: datetime
    invested_amount: Decimal
    market_value: Decimal
    gain: Decimal
    gain_percent: Decimal
    benchmarks: dict[str, Decimal]


class AllocationDriftOut(ApiModel):
    """@brief Current allocation compared with an optional target."""

    ticker: str
    name: str | None = None
    current_value: Decimal
    current_percent: Decimal
    target_percent: Decimal | None = None
    target_value: Decimal | None = None
    drift_percent: Decimal | None = None
    drift_value: Decimal | None = None
    buy_value: Decimal
    trim_value: Decimal
    action: str


class MonthlyActivityOut(ApiModel):
    """@brief Contribution and cash-flow activity for one calendar month."""

    month: str
    buy_contributions: Decimal
    sell_proceeds: Decimal
    dividends: Decimal
    fees: Decimal
    net_cash_flow: Decimal


class BenchmarkComparisonOut(ApiModel):
    """@brief Portfolio return compared with one normalized benchmark series."""

    symbol: str
    name: str
    start_date: date
    end_date: date
    portfolio_start_value: Decimal
    portfolio_end_value: Decimal
    portfolio_return_percent: Decimal
    benchmark_start_value: Decimal
    benchmark_end_value: Decimal
    benchmark_return_percent: Decimal
    relative_return_percent: Decimal


class PortfolioAnalyticsOut(ApiModel):
    """@brief Rich portfolio analytics response."""

    total_value: Decimal
    total_target_percent: Decimal
    unassigned_target_percent: Decimal
    allocation_drift: list[AllocationDriftOut]
    monthly_activity: list[MonthlyActivityOut]
    benchmark_comparison: list[BenchmarkComparisonOut]


class DcaPlanOut(ApiModel):
    """@brief Persisted DCA strategy plan response."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    portfolio_id: str
    name: str
    model_type: Literal["normal", "enhanced"]
    base_amount: Decimal
    preferred_benchmark: str
    min_multiplier: Decimal
    max_multiplier: Decimal
    contribution_frequency: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class DcaAllocationSuggestionOut(ApiModel):
    """@brief Suggested contribution split for one ticker."""

    ticker: str
    suggested_amount: Decimal
    target_percent: Decimal
    current_percent: Decimal
    reason: str


class DcaRecommendationOut(ApiModel):
    """@brief DCA recommendation response."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    plan_id: int
    plan_name: str
    model_type: Literal["normal", "enhanced"]
    portfolio_id: str
    base_amount: Decimal
    adjusted_amount: Decimal
    multiplier: Decimal
    market_change_percent: Decimal
    volatility_index: Decimal | None = None
    reason: str
    allocation_suggestions: list[DcaAllocationSuggestionOut]
