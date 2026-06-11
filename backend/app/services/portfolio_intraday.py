"""@file
@brief Build intraday portfolio history points from transactions and intraday prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

from app.domain import Transaction, quantize_money
from app.services.portfolio import build_holdings


@dataclass(frozen=True)
class PortfolioIntradayPoint:
    """@brief Portfolio value and normalized benchmark values for one intraday timestamp."""

    timestamp: datetime
    invested_amount: Decimal
    market_value: Decimal
    gain: Decimal
    gain_percent: Decimal
    benchmarks: dict[str, Decimal]


def build_portfolio_intraday_history(
    transactions: list[Transaction],
    prices_by_symbol: dict[str, dict[datetime, Decimal]],
    benchmarks_by_symbol: dict[str, dict[datetime, Decimal]],
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[PortfolioIntradayPoint]:
    """@brief Build timestamped portfolio performance history for intraday chart ranges."""
    if not transactions:
        return []

    timeline = _timeline_timestamps(transactions, prices_by_symbol, benchmarks_by_symbol, start_at, end_at)
    if not timeline:
        return []

    last_prices: dict[str, Decimal] = {}
    last_benchmarks: dict[str, Decimal] = {}
    benchmark_base_prices: dict[str, Decimal] = {}
    benchmark_base_value: Decimal | None = None
    points: list[PortfolioIntradayPoint] = []

    for timestamp in timeline:
        _update_last_prices(last_prices, prices_by_symbol, timestamp)
        _update_last_prices(last_benchmarks, benchmarks_by_symbol, timestamp)

        dated_transactions = [transaction for transaction in transactions if transaction.transaction_date <= timestamp.date()]
        holdings = build_holdings(dated_transactions)
        invested_amount = quantize_money(sum((holding.invested_amount for holding in holdings), Decimal("0")))
        market_value = quantize_money(
            sum((holding.quantity * last_prices.get(holding.ticker, holding.average_cost) for holding in holdings), Decimal("0"))
        )
        gain = quantize_money(market_value - invested_amount)
        gain_percent = Decimal("0") if invested_amount == 0 else quantize_money((gain / invested_amount) * Decimal("100"))

        # Normalize each benchmark to the first visible portfolio value for chart comparability.
        if benchmark_base_value is None and market_value > 0:
            benchmark_base_value = market_value
            benchmark_base_prices = dict(last_benchmarks)

        points.append(
            PortfolioIntradayPoint(
                timestamp=timestamp,
                invested_amount=invested_amount,
                market_value=market_value,
                gain=gain,
                gain_percent=gain_percent,
                benchmarks=_normalized_benchmarks(last_benchmarks, benchmark_base_prices, benchmark_base_value),
            )
        )

    return points


def _timeline_timestamps(
    transactions: list[Transaction],
    prices_by_symbol: dict[str, dict[datetime, Decimal]],
    benchmarks_by_symbol: dict[str, dict[datetime, Decimal]],
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[datetime]:
    """@brief Merge intraday price and benchmark timestamps within the effective range."""
    first_transaction_date = min((transaction.transaction_date for transaction in transactions), default=None)
    effective_start_at = start_at
    if first_transaction_date is not None:
        first_transaction_at = datetime.combine(first_transaction_date, time.min, tzinfo=start_at.tzinfo if start_at else None)
        effective_start_at = max(start_at, first_transaction_at) if start_at is not None else first_transaction_at

    timestamps: set[datetime] = set()
    for history in list(prices_by_symbol.values()) + list(benchmarks_by_symbol.values()):
        timestamps.update(history.keys())

    return sorted(
        candidate
        for candidate in timestamps
        if (effective_start_at is None or candidate >= effective_start_at) and (end_at is None or candidate <= end_at)
    )


def _update_last_prices(
    last_prices: dict[str, Decimal],
    history_by_symbol: dict[str, dict[datetime, Decimal]],
    timestamp: datetime,
) -> None:
    for symbol, history in history_by_symbol.items():
        if timestamp in history:
            last_prices[symbol] = history[timestamp]


def _normalized_benchmarks(
    current_benchmarks: dict[str, Decimal],
    base_prices: dict[str, Decimal],
    base_value: Decimal | None,
) -> dict[str, Decimal]:
    if base_value is None or base_value == 0:
        return {}

    normalized = {}
    for symbol, current_price in current_benchmarks.items():
        base_price = base_prices.get(symbol)
        if base_price is None or base_price == 0:
            continue
        normalized[symbol] = quantize_money(base_value * (current_price / base_price))
    return normalized
