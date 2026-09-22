import datetime as dt

from barometer.storage.sqlite_repo import SqliteRepo
from research.domain.fundamentals import FundamentalReport, Metric, QuarterMetrics
from research.domain.local_stock import score_tw_local
from research.pipeline.fundamentals import compose_tw_report, refresh
from research.storage.fundamentals import FundamentalStore


def test_first_seen_snapshot_is_not_visible_to_prior_asof_day(tmp_path):
    day = dt.date(2026, 9, 22)
    stamp = dt.datetime(2026, 9, 22, 10)
    report = FundamentalReport("2330.TW", {
        "gross_margin_pct": Metric(67.03, "TWSE", day, stamp, "2026Q2"),
    }, (QuarterMetrics("2026Q2", 67.03, day),))
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = FundamentalStore(repo.conn)
        store.init_schema()
        store.put(report, stamp)
        assert store.get_asof("2330.TW", day - dt.timedelta(days=1)) is None
        latest = store.get_asof("2330.TW", day)
        assert latest.metric("gross_margin_pct").value == 67.03
        assert latest.quarters[0].period == "2026Q2"


def test_tw_official_valuation_and_monthly_revenue_stay_in_their_own_dimensions():
    day = dt.date(2026, 9, 22)
    view = {
        "local": {"valuation": {"pe_ratio": 21.0, "pb_ratio": 5.0,
                                "dividend_yield_pct": 1.8}},
        "provenance": {"valuation": {"data_date": day.isoformat(), "source": "TWSE BWIBBU_ALL",
                                     "retrieved_at": "2026-09-22T10:00:00"}},
        "fundamentals": {"revenue": {"revenue_yoy_pct": 12.0}},
        "fundamental_provenance": {"revenue": {"data_date": day.isoformat(),
                                               "source": "TWSE t187ap05_L",
                                               "retrieved_at": "2026-09-22T10:00:00"}},
    }
    quarterly = FundamentalReport("2330.TW", {"gross_margin_pct": Metric(67, "TWSE", day)})
    report = compose_tw_report("2330.TW", view, quarterly, day)
    assert report.metric("pe_ratio").value == 21.0
    assert report.metric("revenue_yoy_pct").value == 12.0
    assert report.metric("gross_margin_pct").value == 67
    assert report.coverage.available == 5
    assert "revenue" not in view["local"]
    assert "gross_margin_pct" not in view["local"]
    baseline = score_tw_local(view, day)
    enriched = dict(view)
    enriched["fundamentals"] = {"revenue": {"revenue_yoy_pct": -90.0}}
    enriched["quarterly_financials"] = {"gross_margin_pct": -90.0}
    assert score_tw_local(enriched, day) == baseline
    no_valuation = dict(view)
    no_valuation["local"] = {}
    assert score_tw_local(no_valuation, day).items[0].score is None
    assert baseline.items[0].score is not None


def test_refresh_fetches_official_market_once_and_keeps_missing_us_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    stamp = dt.datetime(2026, 9, 22, 11)
    calls = {"tw": 0, "us": []}

    def fetch_tw(now):
        calls["tw"] += 1
        return {"2330.TW": FundamentalReport("2330.TW", {
            "gross_margin_pct": Metric(67, "TWSE", now.date(), now, "2026Q2")})}

    def fetch_us(symbol, now):
        calls["us"].append(symbol)
        return FundamentalReport(symbol, {} if symbol == "SPCX" else {
            "pe_ratio": Metric(22, "Yahoo", now.date(), now)})

    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = FundamentalStore(repo.conn)
        store.init_schema()
        result = refresh(store, ("2330.TW", "2454.TW"), ("AAPL", "SPCX"), stamp,
                         fetch_tw=fetch_tw, fetch_us=fetch_us)
        assert calls == {"tw": 1, "us": ["AAPL", "SPCX"]}
        assert result.coverage["2330.TW"].available == 1
        assert result.coverage["2454.TW"].available == 0
        assert result.coverage["SPCX"].available == 0
        assert store.get_asof("SPCX", stamp.date()).coverage.available == 0
