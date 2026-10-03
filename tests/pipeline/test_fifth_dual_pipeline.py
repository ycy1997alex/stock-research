"""Adjusted OHLCV and as-of local observations flow into persisted dual scores."""
import datetime as dt

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from research.pipeline import run_stock_scores
from research.storage.tw_local import TwLocalStore


def _bars(symbol, n=300):
    start = dt.date(2025, 1, 1)
    return [PriceBar(symbol, start + dt.timedelta(days=i), 100+i*.2, 101+i*.2,
                     99+i*.2, 100+i*.2, 100_000, "test", dt.datetime(2026, 1, 1))
            for i in range(n)]


def test_ohlcv_and_asof_tw_local_feed_native_only():
    bars = _bars("2330.TW")
    day = bars[-1].date
    view = {"local": {"day_trade": {"day_trade_ratio_pct": 40.0}},
            "provenance": {"day_trade": {"data_date": day.isoformat(), "source": "TWSE"}}}
    tw = run_stock_scores.score_series("2330.TW", bars, local_loader=lambda s, d: view)[-1][1]
    us = run_stock_scores.score_series("AAPL", _bars("AAPL"))[-1][1]
    assert tw.comparable == us.comparable
    assert tw.local is not None and tw.native != tw.comparable
    assert tw.raw_gap == tw.native_raw - tw.comparable_raw
    assert tw.strength is not None


def test_local_items_reach_the_score_with_their_own_dates_and_sources():
    """頁面把本地維度排成欄（名稱／說明／狀態／資料日／延遲／來源）。
    那些欄位不能從 reasons 字串拆回來 —— 結構化的 LocalItem 要一路帶到分數上。"""
    bars = _bars("2330.TW")
    day = bars[-1].date
    view = {"local": {"day_trade": {"day_trade_ratio_pct": 40.0}},
            "provenance": {"day_trade": {"data_date": day.isoformat(), "source": "TWSE"}}}
    tw = run_stock_scores.score_series("2330.TW", bars, local_loader=lambda s, d: view)[-1][1]
    items = {item.name: item for item in tw.local_items}
    assert items["F 當沖比"].status == "有效"
    assert items["F 當沖比"].data_date == day.isoformat()
    assert items["F 當沖比"].age_days == 0
    assert items["F 當沖比"].source == "TWSE"
    assert items["A 官方估值"].status == "資料不足"
    assert len(tw.local_items) == len(tw.local_reasons)


def test_run_persists_both_scores_and_strength(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    bars = _bars("2330.TW")
    day = bars[-1].date
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
        store = TwLocalStore(repo.conn)
        store.put_stock_daily(day, "2330.TW", "day_trade",
                              {"value": {"day_trade_ratio_pct": 40.0}, "data_date": day.isoformat(),
                               "source": "TWSE", "retrieved_at": dt.datetime(2026,1,1).isoformat()},
                              dt.datetime(2026,1,1))
    run_stock_scores.run(["2330.TW"], run_date=day)
    with SqliteRepo(tmp_path / "market.db") as repo:
        row = repo.get_scores("stock", "2330.TW")[-1]
    assert row.comparable is not None and row.native is not None
    assert row.comparable != row.native
    assert row.strength is not None
