import datetime as dt

import pytest

from barometer.storage.sqlite_repo import SqliteRepo
from research.datasources.us_local import Observation
from research.pipeline import us_local
from research.storage.us_local import UsLocalStore


def test_fetch_stores_dated_observations_and_asof_has_no_future_lookahead(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    day = dt.date(2026, 9, 21)
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = UsLocalStore(repo.conn)
        result = us_local.run(store, ["AAPL"], day,
                              retrieved_at=dt.datetime(2026, 9, 21, 12, 0),
                              fetch=lambda symbol, today: {
            "institutional": Observation(dt.date(2026, 6, 30),
                                         {"held_pct": 20, "prior_held_pct": 18}, "Yahoo top holders"),
            "analyst": Observation(today, {"analyst_count": 10,
                                             "rating_dispersion_pct": 70}, "Yahoo snapshot"),
        })
        assert result.coverage["institutional"] == 1
        assert store.get_asof(day-dt.timedelta(days=1), "AAPL") == {}
        assert store.get_asof(day, "AAPL")["institutional"]["data_date"] == "2026-06-30"


def test_old_report_first_seen_today_cannot_be_backdated_into_history(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    day = dt.date(2026, 9, 21)
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = UsLocalStore(repo.conn)
        store.put("AAPL", "institutional", dt.date(2026, 6, 30),
                  {"held_pct": 20, "prior_held_pct": 18}, "Yahoo",
                  dt.datetime(2026, 9, 21, 20))
        assert store.get_asof(dt.date(2026, 9, 18), "AAPL") == {}
        assert "institutional" in store.get_asof(day, "AAPL")


def test_fetch_failure_records_runlog_then_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    day = dt.date(2026, 9, 21)
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        def fail(symbol, today):
            raise RuntimeError("source down")
        with pytest.raises(RuntimeError, match="source down"):
            us_local.run(UsLocalStore(repo.conn), ["AAPL"], day, fetch=fail)
        row = repo.conn.execute("SELECT status FROM run_log WHERE task='us_local'").fetchone()
        assert row[0] == "error"
