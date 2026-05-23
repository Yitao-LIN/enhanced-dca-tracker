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


class DcaRequest(BaseModel):
    base_amount: Decimal
    market_change_percent: Decimal
    volatility_index: Decimal | None = None


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
