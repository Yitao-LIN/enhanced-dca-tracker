"""@file
@brief DCA recommendation rules and allocation-split helpers.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain import DcaAllocationSuggestion, DcaRecommendation, quantize_money


def calculate_normal_dca(
    base_amount: Decimal,
    allocation_suggestions: list[DcaAllocationSuggestion] | None = None,
) -> DcaRecommendation:
    """@brief Return a fixed-contribution DCA recommendation without market adjustment."""
    return DcaRecommendation(
        base_amount=quantize_money(base_amount),
        adjusted_amount=quantize_money(base_amount),
        multiplier=Decimal("1.0"),
        market_change_percent=Decimal("0"),
        volatility_index=None,
        reason="Keep contribution because this Normal DCA plan uses a fixed amount.",
        model_type="normal",
        allocation_suggestions=allocation_suggestions or [],
    )


def calculate_enhanced_dca(
    base_amount: Decimal,
    market_change_percent: Decimal,
    volatility_index: Decimal | None = None,
    min_multiplier: Decimal | None = None,
    max_multiplier: Decimal | None = None,
    allocation_suggestions: list[DcaAllocationSuggestion] | None = None,
) -> DcaRecommendation:
    """@brief Adjust a base contribution amount from market drawdown/rally and volatility.

    @param base_amount User's normal contribution amount.
    @param market_change_percent Benchmark move over the selected period.
    @param volatility_index Optional volatility signal, such as VIX.
    @param min_multiplier Optional lower bound from saved DCA settings.
    @param max_multiplier Optional upper bound from saved DCA settings.
    @return A rounded DCA recommendation with multiplier and explanation.
    """
    multiplier = Decimal("1.0")
    reason_parts = []

    if market_change_percent <= Decimal("-5"):
        multiplier = Decimal("1.5")
        reason_parts.append("market drawdown is at least 5 percent")
    elif market_change_percent <= Decimal("-3"):
        multiplier = Decimal("1.3")
        reason_parts.append("market is down between 3 and 5 percent")
    elif market_change_percent <= Decimal("-1"):
        multiplier = Decimal("1.2")
        reason_parts.append("market is down between 1 and 3 percent")
    elif market_change_percent >= Decimal("5"):
        multiplier = Decimal("0.7")
        reason_parts.append("market is up at least 5 percent")
    elif market_change_percent >= Decimal("3"):
        multiplier = Decimal("0.8")
        reason_parts.append("market is up between 3 and 5 percent")
    else:
        reason_parts.append("market is roughly stable")

    if volatility_index is not None and volatility_index >= Decimal("30") and multiplier > Decimal("1.0"):
        multiplier += Decimal("0.1")
        reason_parts.append("volatility is elevated")
    elif volatility_index is not None and volatility_index <= Decimal("14") and multiplier > Decimal("1.0"):
        multiplier -= Decimal("0.1")
        reason_parts.append("volatility is low")

    if min_multiplier is not None and multiplier < min_multiplier:
        multiplier = min_multiplier
        reason_parts.append("minimum multiplier applied")
    if max_multiplier is not None and multiplier > max_multiplier:
        multiplier = max_multiplier
        reason_parts.append("maximum multiplier applied")

    adjusted_amount = quantize_money(base_amount * multiplier)
    action = "increase" if multiplier > 1 else "decrease" if multiplier < 1 else "keep"
    reason = f"{action.capitalize()} contribution because " + " and ".join(reason_parts) + "."

    return DcaRecommendation(
        base_amount=quantize_money(base_amount),
        adjusted_amount=adjusted_amount,
        multiplier=multiplier,
        market_change_percent=market_change_percent,
        volatility_index=volatility_index,
        reason=reason,
        model_type="enhanced",
        allocation_suggestions=allocation_suggestions or [],
    )


def build_dca_allocation_suggestions(
    total_amount: Decimal,
    allocation_drift: list[object],
) -> list[DcaAllocationSuggestion]:
    """@brief Split a DCA amount across target tickers using allocation drift rows."""
    target_rows = [row for row in allocation_drift if row.target_percent is not None and row.target_percent > 0]
    if not target_rows:
        return []

    underweight_rows = [row for row in target_rows if row.buy_value > 0]
    if underweight_rows:
        total_weight = sum((row.buy_value for row in underweight_rows), Decimal("0"))
        reason = "underweight target allocation"
        weighted_rows = [(row, row.buy_value) for row in underweight_rows]
    else:
        total_weight = sum((row.target_percent for row in target_rows), Decimal("0"))
        reason = "target allocation percent"
        weighted_rows = [(row, row.target_percent) for row in target_rows]

    if total_weight <= 0:
        return []

    return [
        DcaAllocationSuggestion(
            ticker=row.ticker,
            suggested_amount=quantize_money(total_amount * weight / total_weight),
            target_percent=row.target_percent,
            current_percent=row.current_percent,
            reason=reason,
        )
        for row, weight in weighted_rows
    ]
