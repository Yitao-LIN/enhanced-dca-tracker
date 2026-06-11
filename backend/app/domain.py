"""@file
@brief Pure domain objects and money helpers used by services and API schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


Money = Decimal


def quantize_money(value: Decimal) -> Decimal:
    """@brief Round a decimal to cents using financial half-up rounding."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class TransactionType(str, Enum):
    """@brief Supported transaction categories in the portfolio ledger."""

    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    CASH = "cash"


@dataclass(frozen=True)
class Transaction:
    """@brief Immutable investment ledger entry imported from CSV or created through the API."""

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
        """@brief Quantity times unit price rounded to money precision."""
        return quantize_money(self.quantity * self.price)

    @property
    def cash_impact(self) -> Decimal:
        """@brief Signed cash movement implied by the transaction type."""
        if self.transaction_type == TransactionType.BUY:
            return quantize_money(-(self.gross_amount + self.fees))
        if self.transaction_type == TransactionType.SELL:
            return quantize_money(self.gross_amount - self.fees)
        if self.transaction_type == TransactionType.DIVIDEND:
            return quantize_money(self.gross_amount - self.fees)
        return quantize_money(-self.fees)


@dataclass(frozen=True)
class Holding:
    """@brief Open position after buy/sell transactions are netted."""

    ticker: str
    quantity: Decimal
    average_cost: Decimal
    invested_amount: Decimal
    name: str | None = None
    currency: str = "EUR"


@dataclass(frozen=True)
class PricedHolding:
    """@brief Holding enriched with current market value and allocation metrics."""

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
    """@brief Aggregate valuation for a portfolio and its visible holdings."""

    total_value: Decimal
    total_invested: Decimal
    total_gain: Decimal
    total_gain_percent: Decimal
    cash_flow: Decimal
    holdings: list[PricedHolding]


@dataclass(frozen=True)
class MarketSnapshot:
    """@brief Latest quote plus optional previous close for percentage-change math."""

    symbol: str
    close: Decimal
    previous_close: Decimal | None
    as_of: datetime
    currency: str = "EUR"

    @property
    def change_percent(self) -> Decimal:
        """@brief Percentage move from previous close to current close."""
        if self.previous_close is None or self.previous_close == 0:
            return Decimal("0")
        return quantize_money(((self.close - self.previous_close) / self.previous_close) * Decimal("100"))


@dataclass(frozen=True)
class DcaRecommendation:
    """@brief Enhanced DCA output consumed by the API and frontend."""

    base_amount: Decimal
    adjusted_amount: Decimal
    multiplier: Decimal
    market_change_percent: Decimal
    volatility_index: Decimal | None
    reason: str
