from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from barometer.storage.sqlite_repo import SqliteRepo
from research.datasources.tw_local import Snapshot
from research.storage.tw_local import TwLocalStore
from research.pipeline import tw_local as pipeline
from research.pipeline.tw_local import save_snapshot, local_view


STAMP = dt.datetime(2026, 9, 21, 10, 15)
DAY = dt.date(2026, 9, 18)
SYMBOLS = ("2330.TW", "2317.TW", "8299.TWO")


def test_valuation_local_only_with_provenance_and_coverage(tmp_path):
    db = sqlite3.connect(tmp_path / "test.db")
    SqliteRepo(tmp_path / "test.db").init_schema()
    store = TwLocalStore(db)
    snap = Snapshot("TWSE BWIBBU_ALL", DAY, STAMP, {
        "2330.TW": {"pe_ratio": 28.52, "dividend_yield_pct": 0.89, "pb_ratio": 9.92},
    })
    coverage = save_snapshot(store, "valuation", snap, SYMBOLS)
    assert (coverage.available, coverage.expected) == (1, 3)
    view = local_view(store, "2330.TW", DAY)
    assert view["local"]["valuation"]["pe_ratio"] == 28.52
    assert view["provenance"]["valuation"] == {"source": "TWSE BWIBBU_ALL", "data_date": "2026-09-18", "retrieved_at": STAMP.isoformat()}
    assert view["comparable"] is None
    assert store.get_stock_daily(DAY, "2317.TW") is None
    assert local_view(store, "TSM", DAY)["local"] is None
    assert local_view(store, "TSM", DAY)["note"] == "無對應資料"
    db.close()


def test_revenue_stays_outside_both_scores(tmp_path):
    db = sqlite3.connect(tmp_path / "test.db")
    SqliteRepo(tmp_path / "test.db").init_schema()
    store = TwLocalStore(db)
    snap = Snapshot("TWSE t187ap05_L", dt.date(2026, 9, 17), STAMP, {
        "2330.TW": {"reporting_period": "2026-08", "revenue_ktwd": 514805337},
    })
    save_snapshot(store, "revenue", snap, SYMBOLS)
    view = local_view(store, "2330.TW", DAY)
    assert view["local"] is None or "revenue" not in view["local"]
    assert view["fundamentals"]["revenue"]["revenue_ktwd"] == 514805337
    assert view["comparable"] is None
    assert view["native"] is None
    assert view["fundamental_provenance"]["revenue"]["data_date"] == "2026-09-17"
    db.close()


def test_breadth_weekly_and_foreign_feed_local(tmp_path):
    db = sqlite3.connect(tmp_path / "test.db")
    SqliteRepo(tmp_path / "test.db").init_schema()
    store = TwLocalStore(db)
    save_snapshot(store, "breadth", Snapshot("TWSE MI_INDEX", DAY, STAMP,
                  {"market": {"advancers_count": 748, "decliners_count": 251}}), SYMBOLS)
    save_snapshot(store, "distribution", Snapshot("TDCC 1-5", DAY, STAMP,
                  {"2330.TW": {"grades": {"15": {"holder_count": 3, "shares": 900, "custody_pct": 9.0}}}}), SYMBOLS)
    save_snapshot(store, "foreign", Snapshot("TWSE MI_QFIIS", DAY, STAMP,
                  {"2330.TW": {"foreign_holding_pct": 69.22}}), SYMBOLS)
    view = local_view(store, "2330.TW", DAY)
    assert view["local"]["breadth"]["advancers_count"] == 748
    assert view["local"]["distribution"]["grades"]["15"]["holder_count"] == 3
    assert view["local"]["foreign"]["foreign_holding_pct"] == 69.22
    assert view["comparable"] is None
    db.close()


def test_day_trade_ratio_and_lending_are_local_only(tmp_path):
    db = sqlite3.connect(tmp_path / "test.db")
    SqliteRepo(tmp_path / "test.db").init_schema()
    store = TwLocalStore(db)
    save_snapshot(store, "day_trade", Snapshot("TWSE TWTB4U", DAY, STAMP,
                  {"2330.TW": {"day_trade_shares": 4805000}}), SYMBOLS,
                  volume_shares_by_symbol={"2330.TW": 24025000})
    save_snapshot(store, "lending", Snapshot("TWSE TWT93U", DAY, STAMP,
                  {"2330.TW": {"borrowed_short_balance_shares": 15672514}}), SYMBOLS)
    view = local_view(store, "2330.TW", DAY)
    assert view["local"]["day_trade"]["day_trade_ratio_pct"] == 20
    assert view["local"]["lending"]["borrowed_short_balance_shares"] == 15672514
    assert view["comparable"] is None
    db.close()


def test_all_missing_row_is_not_counted_or_stored(tmp_path):
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)
    coverage = save_snapshot(store, "valuation", Snapshot("TWSE BWIBBU_ALL", DAY, STAMP,
        {"2330.TW": {"pe_ratio": None, "dividend_yield_pct": None, "pb_ratio": None}}), SYMBOLS)
    assert coverage.available == 0
    assert store.get_stock_daily(DAY, "2330.TW") is None
    repo.close()


def test_latest_known_daily_value_retains_its_own_date(tmp_path):
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)
    save_snapshot(store, "valuation", Snapshot("TWSE BWIBBU_ALL", DAY, STAMP,
                  {"2330.TW": {"pe_ratio": 28.52}}), SYMBOLS)
    next_day = dt.date(2026, 9, 21)
    view = local_view(store, "2330.TW", next_day)
    assert view["local"]["valuation"]["pe_ratio"] == 28.52
    assert view["provenance"]["valuation"]["data_date"] == "2026-09-18"
    repo.close()


def test_failed_pipeline_logs_then_reraises(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)

    def fail(*args):
        raise RuntimeError("official source unavailable")

    monkeypatch.setattr(pipeline.source, "fetch", fail)
    with pytest.raises(RuntimeError, match="official source unavailable"):
        pipeline.run(store, DAY, SYMBOLS)
    row = repo.conn.execute("SELECT status FROM run_log WHERE task='tw_local'").fetchone()
    assert row[0] == "error"
    assert list((tmp_path / "runlog").glob("*.jsonl"))
    repo.close()
