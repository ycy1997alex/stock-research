import datetime as dt

import pandas as pd

from research.datasources import us_local


def test_institutional_top_holder_dates_and_change_are_explicit():
    frame = pd.DataFrame([
        {"Date Reported": "2026-06-30", "Holder": "A", "pctHeld": .10, "pctChange": .10},
        {"Date Reported": "2026-06-30", "Holder": "B", "pctHeld": .05, "pctChange": -.05},
        {"Date Reported": "2026-03-31", "Holder": "C", "pctHeld": .20, "pctChange": 0},
    ])
    got = us_local.parse_institutional(frame)
    assert got.data_date == dt.date(2026, 6, 30)
    assert got.value["held_pct"] == 15.0
    assert got.value["prior_held_pct"] > 0
    assert "top" in got.source.lower()


def test_insider_only_counts_unambiguous_purchase_and_sale():
    frame = pd.DataFrame([
        {"Start Date": "2026-09-15", "Shares": 1000, "Text": "Purchase at price 10"},
        {"Start Date": "2026-09-16", "Shares": 400, "Text": "Sale at price 11"},
        {"Start Date": "2026-09-16", "Shares": 200, "Text": "Award"},
    ])
    got = us_local.parse_insider(frame, dt.date(2026, 9, 21))
    assert got.value["net_acquired_shares"] == 600
    assert got.data_date == dt.date(2026, 9, 16)


def test_analyst_summary_is_crowding_snapshot_without_target_price():
    frame = pd.DataFrame([{"period": "0m", "strongBuy": 2, "buy": 2,
                           "hold": 3, "sell": 2, "strongSell": 1}])
    got = us_local.parse_analyst(frame, dt.date(2026, 9, 21))
    assert got.value["analyst_count"] == 10
    assert got.value["rating_dispersion_pct"] == 70
    assert "target" not in str(got.value).lower()
    assert "快照" in got.source
