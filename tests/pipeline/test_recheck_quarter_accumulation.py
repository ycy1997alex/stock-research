"""回補批 R-4（三）：季別要跨快照累積，而且不得讓今天才知道的事回到昨天。

`t187ap17_L` 每次只給一季，儲存層又是一天一列，所以 `quarters` 永遠長度 1，
「連三季」在台股等於永遠不會觸發。這裡把讀取路徑改成把各觀測日存到的季別合併。
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from research.domain.fundamentals import FundamentalReport, Metric, QuarterMetrics
from research.storage.fundamentals import FundamentalStore


def _store() -> FundamentalStore:
    store = FundamentalStore(sqlite3.connect(":memory:"))
    store.init_schema()
    return store


def _report(period: str, margin: float) -> FundamentalReport:
    return FundamentalReport("2330.TW",
                             {"gross_margin_pct": Metric(margin, "TWSE", None, None, period)},
                             (QuarterMetrics(period, margin, None, "累計"),))


def test_quarters_seen_on_different_days_accumulate_into_one_series():
    store = _store()
    store.put(_report("2025Q4", 50.0), dt.datetime(2026, 3, 31, 9))
    store.put(_report("2026Q1", 52.0), dt.datetime(2026, 5, 15, 9))
    store.put(_report("2026Q2", 54.0), dt.datetime(2026, 9, 22, 9))

    got = store.get_asof("2330.TW", dt.date(2026, 9, 22))
    assert [q.period for q in got.quarters] == ["2025Q4", "2026Q1", "2026Q2"]
    assert [q.gross_margin_pct for q in got.quarters] == [50.0, 52.0, 54.0]
    assert {q.basis for q in got.quarters} == {"累計"}
    # 最新一季的欄位還是當天那一份，不受合併影響
    assert got.metric("gross_margin_pct").value == 54.0


def test_a_quarter_learned_today_is_not_visible_as_of_yesterday():
    store = _store()
    store.put(_report("2025Q4", 50.0), dt.datetime(2026, 3, 31, 9))
    store.put(_report("2026Q2", 54.0), dt.datetime(2026, 9, 22, 9))

    got = store.get_asof("2330.TW", dt.date(2026, 9, 21))
    assert [q.period for q in got.quarters] == ["2025Q4"]


def test_a_later_observation_of_the_same_quarter_wins():
    store = _store()
    store.put(_report("2026Q2", 54.0), dt.datetime(2026, 9, 20, 9))
    store.put(_report("2026Q2", 55.5), dt.datetime(2026, 9, 22, 9))

    got = store.get_asof("2330.TW", dt.date(2026, 9, 22))
    assert [(q.period, q.gross_margin_pct) for q in got.quarters] == [("2026Q2", 55.5)]


def test_the_daily_write_does_not_drop_quarters_already_known_that_day():
    """每日管線每次只帶一季。它不得把同一天稍早補進來的季別洗掉。

    回補批 R-4：一次性回補寫的是**今天**這一列，當天稍晚的例行更新如果整列覆蓋，
    補回來的歷史就會在當天晚上安靜消失，而且隔天起再也回不來。
    """
    store = _store()
    day = dt.datetime(2026, 9, 22, 19, 30)
    store.put(FundamentalReport("2330.TW", {}, (
        QuarterMetrics("2025Q4", 50.0, None, "年度累計"),
        QuarterMetrics("2026Q1", 52.0, None, "年度累計"),
        QuarterMetrics("2026Q2", 54.0, None, "年度累計"),
    )), day)

    store.put(_report("2026Q2", 55.5), dt.datetime(2026, 9, 22, 21, 45))  # 當天晚上的例行更新

    got = store.get_asof("2330.TW", dt.date(2026, 9, 22))
    assert [q.period for q in got.quarters] == ["2025Q4", "2026Q1", "2026Q2"]
    assert got.quarters[-1].gross_margin_pct == 55.5   # 同一季以最後一次寫入為準
