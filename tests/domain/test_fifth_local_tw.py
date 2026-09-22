import datetime as dt

from research.domain.local_stock import score_tw_local


def test_all_tw_local_factors_normalize_only_present_items_and_exclude_revenue():
    day = dt.date(2026, 9, 21)
    local = {
        "valuation": {"pe_ratio": 18, "dividend_yield_pct": 3},
        "breadth": {"advancers_count": 600, "decliners_count": 400},
        "distribution": {"grades": {"15": {"custody_pct": 12}}, "previous_top_pct": 11},
        "foreign": {"foreign_holding_pct": 60, "previous_foreign_holding_pct": 59},
        "day_trade": {"day_trade_ratio_pct": 12},
        "lending": {"borrowed_short_balance_shares": 90, "previous_borrowed_short_balance_shares": 100},
        "margin_estimate": {"maintenance_pct": 175},
    }
    view = {"local": local, "fundamentals": {"revenue": {"revenue_ktwd": 999}},
            "provenance": {k: {"data_date": day.isoformat(), "source": "test"} for k in local}}
    scored = score_tw_local(view, day, t86_score=50)
    assert scored.score is not None
    assert len(scored.items) == 8
    assert all(item.score is not None for item in scored.items)
    assert all("revenue" not in item.name.lower() for item in scored.items)
    missing = score_tw_local({"local": None, "provenance": {}}, day)
    assert missing.score is None
