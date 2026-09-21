"""Per-stock margin maintenance and average-cost estimates, never official values.

Assumptions:
* ASSUMED_FINANCING_RATIO is the TWSE published maximum (60%), not a claim that
  every stock/account actually receives 60%. A stock can have a lower ratio.
  Source: https://twse-regulation.twse.com.tw/TW/int/DAT01_print.aspx?FLCODE=FE366601
* SEED_COST_METHOD and REDUCTION_COST_METHOD follow the model documented in
  Reference/StockTracker_ChipMargin.md §3.2 (2026-09-05). First observation
  seeds cost at that day's close; additions use current close; reductions leave
  at the prior weighted average. Intraday turnover and investor-level collateral
  are unobservable in TWTA1U, so the result must be labelled 推算值.
"""
from __future__ import annotations

import math


ASSUMED_FINANCING_RATIO = 0.60
SEED_COST_METHOD = "first_observed_close"
ADDITION_COST_METHOD = "current_close"
REDUCTION_COST_METHOD = "previous_weighted_average"
SHARES_PER_LOT = 1000


def estimate_margin(
    previous_balance_shares: int | None,
    balance_shares: int | None,
    close_twd: float | None,
    prior: dict | None,
) -> dict:
    """Estimate outstanding loan and collateral ratio from adjacent day totals.

    Zero balance and missing price yield None for both displayed estimates. A
    revised previous balance resets the cost basis to the observed close; it is
    never silently spliced into an incompatible state.
    """
    if balance_shares is not None and balance_shares < 0:
        raise ValueError("negative margin balance")
    if previous_balance_shares is not None and previous_balance_shares < 0:
        raise ValueError("negative previous margin balance")
    base = {
        "margin_prev_shares": previous_balance_shares,
        "margin_balance_shares": balance_shares,
        "estimated_loan_twd": None,
        "average_cost_twd": None,
        "maintenance_pct": None,
        "assumed_financing_ratio_pct": ASSUMED_FINANCING_RATIO * 100,
        "seeded_from_close": False,
        "days_observed": 0,
    }
    if balance_shares is None:
        return {**base, "reason": "融資餘額缺資料"}
    if balance_shares == 0:
        return {**base, "reason": "融資餘額為 0，維持率與平均成本無定義"}
    if close_twd is None or not math.isfinite(close_twd) or close_twd <= 0:
        return {**base, "reason": "同日收盤價缺資料"}

    previous_loan = (prior or {}).get("estimated_loan_twd")
    continuity = (
        previous_balance_shares is not None and prior is not None
        and prior.get("margin_balance_shares") == previous_balance_shares
        and previous_balance_shares > 0
        and isinstance(previous_loan, (int, float)) and math.isfinite(previous_loan)
        and previous_loan > 0
    )
    if continuity:
        delta = balance_shares - previous_balance_shares
        if delta >= 0:
            loan = previous_loan + delta * close_twd * ASSUMED_FINANCING_RATIO
        else:
            previous_cost = previous_loan / (previous_balance_shares * ASSUMED_FINANCING_RATIO)
            loan = max(0.0, previous_loan + delta * previous_cost * ASSUMED_FINANCING_RATIO)
        days_observed = int(prior.get("days_observed", 0)) + 1
        seeded = False
    else:
        # This initial cost is a model seed, not a disclosed investor cost.
        loan = balance_shares * close_twd * ASSUMED_FINANCING_RATIO
        days_observed = 1
        seeded = True

    if loan <= 0:
        return {**base, "reason": "推算融資金額無有效值"}
    return {
        **base,
        "estimated_loan_twd": loan,
        "average_cost_twd": loan / (balance_shares * ASSUMED_FINANCING_RATIO),
        "maintenance_pct": balance_shares * close_twd / loan * 100,
        "seeded_from_close": seeded,
        "days_observed": days_observed,
        "reason": "首日以收盤價設定推算成本" if seeded else "由逐日餘額變化推算",
    }
