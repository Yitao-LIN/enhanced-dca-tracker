"""@file
@brief Portfolio holding construction and valuation calculations.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.domain import (
    Holding,
    PortfolioSummary,
    PricedHolding,
    Transaction,
    TransactionType,
    quantize_money,
)


def build_holdings(transactions: list[Transaction]) -> list[Holding]:
    """@brief Net buy/sell transactions into open holdings with adjusted cost basis."""
    lots: dict[str, dict[str, Decimal | str]] = defaultdict(
        lambda: {"quantity": Decimal("0"), "cost": Decimal("0"), "currency": "EUR", "name": ""}
    )

    for transaction in sorted(transactions, key=lambda item: item.transaction_date):
        if transaction.transaction_type not in {TransactionType.BUY, TransactionType.SELL}:
            continue

        position = lots[transaction.ticker]
        quantity = Decimal(position["quantity"])
        cost = Decimal(position["cost"])

        if transaction.transaction_type == TransactionType.BUY:
            quantity += transaction.quantity
            cost += transaction.gross_amount + transaction.fees
            position["currency"] = transaction.currency
            if transaction.description and not str(position["name"]).strip():
                position["name"] = transaction.description
        elif transaction.transaction_type == TransactionType.SELL and quantity > 0:
            # Selling reduces the remaining lot cost at average cost, not at sale proceeds.
            average_cost = cost / quantity
            sold_quantity = min(transaction.quantity, quantity)
            quantity -= sold_quantity
            cost -= average_cost * sold_quantity

        position["quantity"] = quantity
        position["cost"] = max(cost, Decimal("0"))

    holdings = []
    for ticker, position in lots.items():
        quantity = Decimal(position["quantity"])
        cost = quantize_money(Decimal(position["cost"]))
        if quantity <= 0:
            continue
        holdings.append(
            Holding(
                ticker=ticker,
                quantity=quantity,
                average_cost=quantize_money(cost / quantity),
                invested_amount=cost,
                name=str(position["name"]).strip() or None,
                currency=str(position["currency"]),
            )
        )
    return sorted(holdings, key=lambda item: item.ticker)


def summarize_portfolio(transactions: list[Transaction], current_prices: dict[str, Decimal]) -> PortfolioSummary:
    """@brief Price open holdings and compute portfolio-level performance metrics."""
    holdings = build_holdings(transactions)
    total_value = sum(
        (
            quantize_money(holding.quantity * current_prices.get(holding.ticker, holding.average_cost))
            for holding in holdings
        ),
        Decimal("0"),
    )
    total_invested = sum(
        (holding.invested_amount for holding in holdings),
        Decimal("0"),
    )

    priced_holdings = []
    for holding in holdings:
        current_price = current_prices.get(holding.ticker, holding.average_cost)
        market_value = quantize_money(holding.quantity * current_price)
        gain = quantize_money(market_value - holding.invested_amount)
        gain_percent = Decimal("0") if holding.invested_amount == 0 else quantize_money((gain / holding.invested_amount) * Decimal("100"))
        allocation = Decimal("0") if total_value == 0 else quantize_money((market_value / total_value) * Decimal("100"))
        priced_holdings.append(
            PricedHolding(
                ticker=holding.ticker,
                name=holding.name,
                quantity=holding.quantity,
                average_cost=holding.average_cost,
                current_price=quantize_money(current_price),
                invested_amount=holding.invested_amount,
                market_value=market_value,
                unrealized_gain=gain,
                unrealized_gain_percent=gain_percent,
                allocation_percent=allocation,
                currency=holding.currency,
            )
        )

    total_gain = quantize_money(total_value - total_invested)
    total_gain_percent = Decimal("0") if total_invested == 0 else quantize_money((total_gain / total_invested) * Decimal("100"))
    cash_flow = sum((transaction.cash_impact for transaction in transactions), Decimal("0"))

    return PortfolioSummary(
        total_value=quantize_money(total_value),
        total_invested=quantize_money(total_invested),
        total_gain=total_gain,
        total_gain_percent=total_gain_percent,
        cash_flow=quantize_money(cash_flow),
        holdings=priced_holdings,
    )
