"""回補批 R-4（四）：一次性把過去幾季補進來，補完不得動到今天那一份欄位。

⚠️ 補回來的季別**沒有首次公開日**（官方那張表給不出來），所以它們只能標「取得日」，
而且掛在**今天**這個觀測日底下 —— 今天才知道的事不得回到昨天（同 §2.4 的精神）。
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from research.domain.fundamentals import (
    CUMULATIVE, FundamentalReport, Metric, QuarterMetrics)
from research.pipeline.fundamentals import merge_quarter_history
from research.storage.fundamentals import FundamentalStore

TODAY = dt.datetime(2026, 9, 22, 19, 30)


def _store() -> FundamentalStore:
    store = FundamentalStore(sqlite3.connect(":memory:"))
    store.init_schema()
    store.put(FundamentalReport(
        "2330.TW",
        {"gross_margin_pct": Metric(67.03, "TWSE", TODAY.date(), TODAY, "2026Q2")},
        (QuarterMetrics("2026Q2", 67.03, TODAY.date(), CUMULATIVE),)), TODAY)
    return store


def test_backfilled_quarters_join_today_snapshot_without_touching_its_metrics():
    store = _store()
    history = {"2330.TW": (QuarterMetrics("2025Q3", 58.97, TODAY.date(), CUMULATIVE),
                           QuarterMetrics("2025Q4", 59.89, TODAY.date(), CUMULATIVE),
                           QuarterMetrics("2026Q1", 66.25, TODAY.date(), CUMULATIVE))}

    filled = merge_quarter_history(store, ("2330.TW",), history, TODAY)

    assert filled == {"2330.TW": 4}
    got = store.get_asof("2330.TW", TODAY.date())
    assert [q.period for q in got.quarters] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert got.metric("gross_margin_pct").value == 67.03          # 今天那一份沒被動到
    assert all(q.data_date == TODAY.date() for q in got.quarters)  # 取得日，不是公開日
    assert {q.basis for q in got.quarters} == {CUMULATIVE}


def test_running_it_twice_changes_nothing():
    store = _store()
    history = {"2330.TW": (QuarterMetrics("2025Q4", 59.89, TODAY.date(), CUMULATIVE),)}
    first = merge_quarter_history(store, ("2330.TW",), history, TODAY)
    second = merge_quarter_history(store, ("2330.TW",), history, TODAY)
    assert first == second == {"2330.TW": 2}


def test_symbol_without_history_is_reported_not_invented():
    store = _store()
    filled = merge_quarter_history(store, ("2330.TW", "2454.TW"), {}, TODAY)
    assert filled["2454.TW"] == 0
    assert store.get_asof("2454.TW", TODAY.date()) is None
