"""Batch 3-7: per-stock margin estimates are explicitly inferred values."""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.storage.sqlite_repo import SqliteRepo
from research.datasources import tw_local
from research.domain.margin_tw import estimate_margin
from research.pipeline import tw_local as pipeline
from research.pipeline.tw_local import local_view, save_snapshot
from research.storage.tw_local import TwLocalStore


DAY = dt.date(2026, 9, 18)
NEXT = dt.date(2026, 9, 21)
STAMP = dt.datetime(2026, 9, 21, 13, 30)


def test_twta1u_uses_individual_first_balance_and_converts_lots_to_shares():
    fields = ["代號", "名稱", "前日餘額", "買進", "賣出", "現償", "今日餘額"]
    row = ["2330", "台積電", "29,148", "472", "834", "23", "28,763"]
    got = tw_local.parse_margin_stock({"stat": "OK", "date": "20260918", "fields": fields,
                                       "data": [row]}, STAMP)
    assert got.source == "TWSE TWTA1U"
    assert got.data_date == DAY
    assert got.values["2330.TW"] == {"margin_prev_shares": 29148000,
                                     "margin_balance_shares": 28763000}


def test_unpublished_margin_is_not_a_zero_balance():
    with pytest.raises(tw_local.NotPublishedYet):
        tw_local.parse_margin_stock({"stat": "沒有符合條件的資料", "data": []}, STAMP)


def test_margin_estimate_recurs_on_new_and_closed_positions():
    seed = estimate_margin(1000, 1000, 100.0, None)
    assert seed["margin_balance_shares"] == 1000
    assert seed["estimated_loan_twd"] == pytest.approx(60000)
    assert seed["average_cost_twd"] == pytest.approx(100)
    assert seed["maintenance_pct"] == pytest.approx(100 / 0.6)
    assert seed["seeded_from_close"] is True
    added = estimate_margin(1000, 1500, 120.0, seed)
    assert added["estimated_loan_twd"] == pytest.approx(96000)
    assert added["average_cost_twd"] == pytest.approx(96000 / (1500 * 0.6))
    assert added["maintenance_pct"] == pytest.approx(1500 * 120 / 96000 * 100)
    assert added["seeded_from_close"] is False
    reduced = estimate_margin(1500, 1250, 80.0, added)
    assert reduced["estimated_loan_twd"] == pytest.approx(80000)
    assert reduced["average_cost_twd"] == pytest.approx(80000 / (1250 * 0.6))
    assert reduced["maintenance_pct"] == pytest.approx(125)


def test_zero_balance_or_missing_close_produces_no_ratio_or_cost():
    seed = estimate_margin(1000, 1000, 100.0, None)
    zero = estimate_margin(1000, 0, 90.0, seed)
    assert zero["margin_balance_shares"] == 0
    assert zero["maintenance_pct"] is None
    assert zero["average_cost_twd"] is None
    assert zero["estimated_loan_twd"] is None
    missing = estimate_margin(1000, 1000, None, seed)
    assert missing["maintenance_pct"] is None
    assert missing["average_cost_twd"] is None


def test_zero_balance_is_saved_as_observed_but_not_covered_as_a_ratio(tmp_path):
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)
    snapshot = tw_local.Snapshot("TWSE TWTA1U", DAY, STAMP,
                                 {"2330.TW": {"margin_prev_shares": 1000,
                                              "margin_balance_shares": 0}})
    coverage = save_snapshot(store, "margin_estimate", snapshot, ("2330.TW",),
                             close_twd_by_symbol={"2330.TW": 100.0})
    value = local_view(store, "2330.TW", DAY)["local"]["margin_estimate"]
    assert coverage.available == 0
    assert value["margin_balance_shares"] == 0
    assert value["maintenance_pct"] is None
    assert value["average_cost_twd"] is None
    repo.close()


def test_gap_or_revised_previous_balance_resets_assumption():
    seed = estimate_margin(1000, 1000, 100.0, None)
    reset = estimate_margin(900, 1200, 110.0, seed)
    assert reset["seeded_from_close"] is True
    assert reset["average_cost_twd"] == pytest.approx(110)


def test_estimate_is_local_only_and_keeps_three_provenance_fields(tmp_path):
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)
    first = tw_local.Snapshot("TWSE TWTA1U", DAY, STAMP,
                              {"2330.TW": {"margin_prev_shares": 1000,
                                           "margin_balance_shares": 1000}})
    coverage = save_snapshot(store, "margin_estimate", first, ("2330.TW", "2317.TW"),
                             close_twd_by_symbol={"2330.TW": 100.0})
    assert (coverage.available, coverage.expected) == (1, 2)
    second = tw_local.Snapshot("TWSE TWTA1U", NEXT, STAMP,
                               {"2330.TW": {"margin_prev_shares": 1000,
                                            "margin_balance_shares": 1500}})
    save_snapshot(store, "margin_estimate", second, ("2330.TW",),
                  close_twd_by_symbol={"2330.TW": 120.0})
    view = local_view(store, "2330.TW", NEXT)
    assert view["local"]["margin_estimate"]["maintenance_pct"] == pytest.approx(187.5)
    assert "推算值" in view["provenance"]["margin_estimate"]["source"]
    assert view["provenance"]["margin_estimate"]["data_date"] == "2026-09-21"
    assert view["provenance"]["margin_estimate"]["retrieved_at"] == STAMP.isoformat()
    assert view["comparable"] is None
    assert view["native"] is None
    assert local_view(store, "TSM", NEXT)["note"] == "無對應資料"
    repo.close()


def test_manual_history_fetches_each_all_market_day_once_and_advances_state(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)
    calls = []

    def fake_fetch(dataset, day):
        calls.append((dataset, day))
        previous, balance = (1000, 1000) if day == DAY else (1000, 1500)
        return tw_local.Snapshot("TWSE TWTA1U", day, STAMP, {
            "2330.TW": {"margin_prev_shares": previous, "margin_balance_shares": balance},
        })

    monkeypatch.setattr(pipeline.source, "fetch", fake_fetch)
    coverage = pipeline.backfill_margin_history(
        store, {DAY: {"2330.TW": 100.0}, NEXT: {"2330.TW": 120.0}},
        ("2330.TW", "2317.TW"),
    )
    assert calls == [("margin_estimate", DAY), ("margin_estimate", NEXT)]
    assert [(coverage[d].available, coverage[d].expected) for d in (DAY, NEXT)] == [(1, 2), (1, 2)]
    assert local_view(store, "2330.TW", NEXT)["local"]["margin_estimate"]["days_observed"] == 2
    repo.close()


def test_manual_history_skips_wrong_report_date_without_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    repo = SqliteRepo(tmp_path / "test.db")
    repo.init_schema()
    store = TwLocalStore(repo.conn)
    monkeypatch.setattr(pipeline.source, "fetch", lambda dataset, day:
                        tw_local.Snapshot("TWSE TWTA1U", DAY, STAMP,
                                          {"2330.TW": {"margin_prev_shares": 1000,
                                                       "margin_balance_shares": 1000}}))
    result = pipeline.backfill_margin_history(store, {NEXT: {"2330.TW": 100.0}}, ("2330.TW",))
    assert result == {}
    assert store.get_stock_daily(NEXT, "2330.TW") is None
    repo.close()
