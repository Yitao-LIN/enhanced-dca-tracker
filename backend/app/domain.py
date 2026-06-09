from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


Money = Decimal


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class TransactionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    CASH = "cash"


@dataclass(frozen=True)
class Transaction:
    transaction_date: date
    ticker: str
    transaction_type: TransactionType
    quantity: Decimal
    price: Decimal
    fees: Decimal = Decimal("0")
    currency: str = "EUR"
    account: str | None = None
    description: str | None = None

    @property
    def gross_amount(self) -> Decimal:
        return quantize_money(self.quantity * self.price)

    @property
    def cash_impact(self) -> Decimal:
        if self.transaction_type == TransactionType.BUY:
            return quantize_money(-(self.gross_amount + self.fees))
        if self.transaction_type == TransactionType.SELL:
            return quantize_money(self.gross_amount - self.fees)
        if self.transaction_type == TransactionType.DIVIDEND:
            return quantize_money(self.gross_amount - self.fees)
        return quantize_money(-self.fees)


@dataclass(frozen=True)
class Holding:
    ticker: str
    quantity: Decimal
    average_cost: Decimal
    invested_amount: Decimal
    name: str | None = None
    currency: str = "EUR"


@dataclass(frozen=True)
class PricedHolding:
    ticker: str
    name: str | None
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal
    invested_amount: Decimal
    market_value: Decimal
    unrealized_gain: Decimal
    unrealized_gain_percent: Decimal
    allocation_percent: Decimal
    currency: str = "EUR"


@dataclass(frozen=True)
class PortfolioSummary:
    total_value: Decimal
    total_invested: Decimal
    total_gain: Decimal
    total_gain_percent: Decimal
    cash_flow: Decimal
    holdings: list[PricedHolding]


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    close: Decimal
    previous_close: Decimal | None
    as_of: datetime
    currency: str = "EUR"

    @property
    def change_percent(self) -> Decimal:
        if self.previous_close is None or self.previous_close == 0:
            return Decimal("0")
        return quantize_money(((self.close - self.previous_close) / self.previous_close) * Decimal("100"))


@dataclass(frozen=True)
class DcaRecommendation:
    base_amount: Decimal
    adjusted_amount: Decimal
    multiplier: Decimal
    market_change_percent: Decimal
    volatility_index: Decimal | None
    reason: str
