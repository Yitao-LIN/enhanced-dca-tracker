from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain import Transaction, quantize_money
from app.services.portfolio import build_holdings


@dataclass(frozen=True)
class PortfolioHistoryPoint:
    price_date: date
    invested_amount: Decimal
    market_value: Decimal
    gain: Decimal
    gain_percent: Decimal
    benchmarks: dict[str, Decimal]


def build_portfolio_history(
    transactions: list[Transaction],
    prices_by_symbol: dict[str, dict[date, Decimal]],
    benchmarks_by_symbol: dict[str, dict[date, Decimal]],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[PortfolioHistoryPoint]:
    if not transactions and not prices_by_symbol and not benchmarks_by_symbol:
        return []

    timeline_dates = _timeline_dates(transactions, prices_by_symbol, benchmarks_by_symbol, start_date, end_date)
    if not timeline_dates:
        return []

    last_prices: dict[str, Decimal] = {}
    last_benchmarks: dict[str, Decimal] = {}
    benchmark_base_prices: dict[str, Decimal] = {}
    benchmark_base_value: Decimal | None = None
    points: list[PortfolioHistoryPoint] = []

    for current_date in timeline_dates:
        _update_last_prices(last_prices, prices_by_symbol, current_date)
        _update_last_prices(last_benchmarks, benchmarks_by_symbol, current_date)

        dated_transactions = [transaction for transaction in transactions if transaction.transaction_date <= current_date]
        holdings = build_holdings(dated_transactions)
        invested_amount = quantize_money(sum((holding.invested_amount for holding in holdings), Decimal("0")))
        market_value = quantize_money(
            sum((holding.quantity * last_prices.get(holding.ticker, holding.average_cost) for holding in holdings), Decimal("0"))
        )
        gain = quantize_money(market_value - invested_amount)
        gain_percent = Decimal("0") if invested_amount == 0 else quantize_money((gain / invested_amount) * Decimal("100"))

        if benchmark_base_value is None and market_value > 0:
            benchmark_base_value = market_value
            benchmark_base_prices = dict(last_benchmarks)

        points.append(
            PortfolioHistoryPoint(
                price_date=current_date,
                invested_amount=invested_amount,
                market_value=market_value,
                gain=gain,
                gain_percent=gain_percent,
                benchmarks=_normalized_benchmarks(last_benchmarks, benchmark_base_prices, benchmark_base_value),
            )
        )

    return points


def _timeline_dates(
    transactions: list[Transaction],
    prices_by_symbol: dict[str, dict[date, Decimal]],
    benchmarks_by_symbol: dict[str, dict[date, Decimal]],
    start_date: date | None,
    end_date: date | None,
) -> list[date]:
    first_transaction_date = min((transaction.transaction_date for transaction in transactions), default=None)
    effective_start_date = start_date
    if first_transaction_date is not None:
        effective_start_date = max(start_date, first_transaction_date) if start_date is not None else first_transaction_date

    dates = {transaction.transaction_date for transaction in transactions}
    for history in list(prices_by_symbol.values()) + list(benchmarks_by_symbol.values()):
        dates.update(history.keys())

    return sorted(
        candidate
        for candidate in dates
        if (effective_start_date is None or candidate >= effective_start_date) and (end_date is None or candidate <= end_date)
    )


def _update_last_prices(
    last_prices: dict[str, Decimal],
    history_by_symbol: dict[str, dict[date, Decimal]],
    current_date: date,
) -> None:
    for symbol, history in history_by_symbol.items():
        if current_date in history:
            last_prices[symbol] = history[current_date]


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
