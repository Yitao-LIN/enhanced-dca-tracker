"""@file
@brief Portfolio analytics for allocation targets, activity, and benchmark comparison.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain import PortfolioSummary, Transaction, TransactionType, quantize_money


@dataclass(frozen=True)
class AllocationTargetInput:
    """@brief Target allocation percentage used by analytics calculations."""

    ticker: str
    target_percent: Decimal


@dataclass(frozen=True)
class AllocationDrift:
    """@brief Current allocation compared with an optional saved target."""

    ticker: str
    name: str | None
    current_value: Decimal
    current_percent: Decimal
    target_percent: Decimal | None
    target_value: Decimal | None
    drift_percent: Decimal | None
    drift_value: Decimal | None
    buy_value: Decimal
    trim_value: Decimal
    action: str


@dataclass(frozen=True)
class MonthlyActivity:
    """@brief Monthly contribution and cash-flow activity."""

    month: str
    buy_contributions: Decimal
    sell_proceeds: Decimal
    dividends: Decimal
    fees: Decimal
    net_cash_flow: Decimal


@dataclass(frozen=True)
class BenchmarkComparison:
    """@brief Portfolio return compared with one normalized benchmark."""

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


@dataclass(frozen=True)
class PortfolioAnalytics:
    """@brief Full analytics response object before API serialization."""

    total_value: Decimal
    total_target_percent: Decimal
    unassigned_target_percent: Decimal
    allocation_drift: list[AllocationDrift]
    monthly_activity: list[MonthlyActivity]
    benchmark_comparison: list[BenchmarkComparison]


def build_portfolio_analytics(
    transactions: list[Transaction],
    summary: PortfolioSummary,
    allocation_targets: list[AllocationTargetInput],
    history_points: list[object],
    benchmark_names: dict[str, str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> PortfolioAnalytics:
    """@brief Build allocation, activity, and benchmark analytics for visible transactions."""
    if not transactions:
        return PortfolioAnalytics(
            total_value=Decimal("0.00"),
            total_target_percent=Decimal("0.00"),
            unassigned_target_percent=Decimal("100.00"),
            allocation_drift=[],
            monthly_activity=[],
            benchmark_comparison=[],
        )

    target_map = {target.ticker.upper(): target.target_percent for target in allocation_targets}
    total_target_percent = quantize_money(sum(target_map.values(), Decimal("0")))
    unassigned_target_percent = quantize_money(max(Decimal("100") - total_target_percent, Decimal("0")))
    return PortfolioAnalytics(
        total_value=summary.total_value,
        total_target_percent=total_target_percent,
        unassigned_target_percent=unassigned_target_percent,
        allocation_drift=_allocation_drift(summary, target_map),
        monthly_activity=_monthly_activity(transactions, start_date=start_date, end_date=end_date),
        benchmark_comparison=_benchmark_comparison(history_points, benchmark_names),
    )


def _allocation_drift(summary: PortfolioSummary, target_map: dict[str, Decimal]) -> list[AllocationDrift]:
    holdings_by_ticker = {holding.ticker.upper(): holding for holding in summary.holdings}
    tickers = sorted(set(holdings_by_ticker) | set(target_map))
    rows: list[AllocationDrift] = []

    for ticker in tickers:
        holding = holdings_by_ticker.get(ticker)
        current_value = holding.market_value if holding is not None else Decimal("0.00")
        current_percent = holding.allocation_percent if holding is not None else Decimal("0.00")
        target_percent = target_map.get(ticker)
        target_value = None
        drift_percent = None
        drift_value = None
        buy_value = Decimal("0.00")
        trim_value = Decimal("0.00")
        action = "unassigned"

        if target_percent is not None:
            target_value = quantize_money(summary.total_value * target_percent / Decimal("100"))
            drift_percent = quantize_money(current_percent - target_percent)
            drift_value = quantize_money(current_value - target_value)
            buy_value = quantize_money(max(target_value - current_value, Decimal("0")))
            trim_value = quantize_money(max(current_value - target_value, Decimal("0")))
            if buy_value > 0:
                action = "buy"
            elif trim_value > 0:
                action = "trim"
            else:
                action = "hold"

        rows.append(
            AllocationDrift(
                ticker=ticker,
                name=holding.name if holding is not None else None,
                current_value=quantize_money(current_value),
                current_percent=quantize_money(current_percent),
                target_percent=target_percent,
                target_value=target_value,
                drift_percent=drift_percent,
                drift_value=drift_value,
                buy_value=buy_value,
                trim_value=trim_value,
                action=action,
            )
        )
    return rows


def _monthly_activity(
    transactions: list[Transaction],
    start_date: date | None,
    end_date: date | None,
) -> list[MonthlyActivity]:
    months: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "buy_contributions": Decimal("0"),
            "sell_proceeds": Decimal("0"),
            "dividends": Decimal("0"),
            "fees": Decimal("0"),
            "net_cash_flow": Decimal("0"),
        }
    )

    for transaction in transactions:
        if start_date is not None and transaction.transaction_date < start_date:
            continue
        if end_date is not None and transaction.transaction_date > end_date:
            continue
        bucket = months[transaction.transaction_date.strftime("%Y-%m")]
        if transaction.transaction_type == TransactionType.BUY:
            bucket["buy_contributions"] += transaction.gross_amount + transaction.fees
        elif transaction.transaction_type == TransactionType.SELL:
            bucket["sell_proceeds"] += transaction.gross_amount - transaction.fees
        elif transaction.transaction_type == TransactionType.DIVIDEND:
            bucket["dividends"] += transaction.gross_amount - transaction.fees
        bucket["fees"] += transaction.fees
        bucket["net_cash_flow"] += transaction.cash_impact

    return [
        MonthlyActivity(
            month=month,
            buy_contributions=quantize_money(values["buy_contributions"]),
            sell_proceeds=quantize_money(values["sell_proceeds"]),
            dividends=quantize_money(values["dividends"]),
            fees=quantize_money(values["fees"]),
            net_cash_flow=quantize_money(values["net_cash_flow"]),
        )
        for month, values in sorted(months.items())
    ]


def _benchmark_comparison(history_points: list[object], benchmark_names: dict[str, str]) -> list[BenchmarkComparison]:
    rows: list[BenchmarkComparison] = []
    for symbol, name in benchmark_names.items():
        comparable = [
            point
            for point in history_points
            if point.market_value > 0 and point.benchmarks.get(symbol) is not None
        ]
        if len(comparable) < 2:
            continue
        first = comparable[0]
        last = comparable[-1]
        benchmark_start = first.benchmarks[symbol]
        benchmark_end = last.benchmarks[symbol]
        if first.market_value == 0 or benchmark_start == 0:
            continue
        portfolio_return = quantize_money((last.market_value - first.market_value) / first.market_value * Decimal("100"))
        benchmark_return = quantize_money((benchmark_end - benchmark_start) / benchmark_start * Decimal("100"))
        rows.append(
            BenchmarkComparison(
                symbol=symbol,
                name=name,
                start_date=first.price_date,
                end_date=last.price_date,
                portfolio_start_value=first.market_value,
                portfolio_end_value=last.market_value,
                portfolio_return_percent=portfolio_return,
                benchmark_start_value=benchmark_start,
                benchmark_end_value=benchmark_end,
                benchmark_return_percent=benchmark_return,
                relative_return_percent=quantize_money(portfolio_return - benchmark_return),
            )
        )
    return rows
