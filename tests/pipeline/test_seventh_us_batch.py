import datetime as dt

import pytest

from barometer.storage.sqlite_repo import SqliteRepo
from research.datasources.us_local import Observation
from research.pipeline.us_local import run
from research.storage.us_local import UsLocalStore


def _fetch(calls):
    def fetch(symbol, day):
        calls.append(symbol)
        return {"analyst": Observation(day, {"analyst_count": 4}, "fixture")}
    return fetch


def test_batch_resumes_across_days_in_configured_order(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    calls = []
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = UsLocalStore(repo.conn)
        first = run(store, ["B", "A", "C"], dt.date(2026, 9, 22),
                    cycle="2026-09-research", batch_size=2, fetch=_fetch(calls))
        assert calls == ["B", "A"]
        assert (first.processed, first.remaining) == (2, 1)
        assert repo.conn.execute("SELECT status FROM run_log WHERE task='us_local' ORDER BY started_at DESC LIMIT 1").fetchone()[0] == "partial"
        second = run(store, ["B", "A", "C"], dt.date(2026, 9, 23),
                     cycle="2026-09-research", batch_size=2, fetch=_fetch(calls),
                     retrieved_at=dt.datetime(2026, 9, 23, 10))
        assert calls == ["B", "A", "C"]
        assert (second.processed, second.remaining) == (1, 0)
        assert second.coverage["analyst"] == 3


def test_failure_keeps_completed_symbols_and_resumes_at_failed_symbol(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    calls = []
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = UsLocalStore(repo.conn)

        def fail_on_b(symbol, day):
            calls.append(symbol)
            if symbol == "B":
                raise RuntimeError("source down")
            return _fetch([])(symbol, day)

        with pytest.raises(RuntimeError, match="source down"):
            run(store, ["A", "B", "C"], dt.date(2026, 9, 22),
                cycle="resume", fetch=fail_on_b)
        resumed = run(store, ["A", "B", "C"], dt.date(2026, 9, 23),
                      cycle="resume", fetch=_fetch(calls),
                      retrieved_at=dt.datetime(2026, 9, 23, 10))
        assert calls == ["A", "B", "B", "C"]
        assert (resumed.processed, resumed.remaining) == (2, 0)
        assert store.get_asof(dt.date(2026, 9, 22), "B") == {}
        assert repo.conn.execute("SELECT COUNT(*) FROM run_log WHERE task='us_local' AND status='error'").fetchone()[0] == 1


def test_missing_dimensions_count_as_attempted_without_zero_values(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = UsLocalStore(repo.conn)
        first = run(store, ["SPCX"], dt.date(2026, 9, 22),
                    cycle="missing", fetch=lambda symbol, day: {})
        assert first.coverage["analyst"] == 0
        assert first.remaining == 0
        assert store.get_asof(dt.date(2026, 9, 22), "SPCX") == {}
        second = run(store, ["SPCX"], dt.date(2026, 9, 23),
                     cycle="missing", fetch=lambda symbol, day: (_ for _ in ()).throw(AssertionError("refetched")),
                     retrieved_at=dt.datetime(2026, 9, 23, 10))
        assert second.processed == 0


def test_automatic_cycle_continues_until_finished_then_starts_next_day(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    calls = []
    symbols = ["A", "B", "C"]
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = UsLocalStore(repo.conn)
        first = run(store, symbols, dt.date(2026, 9, 22), cycle="auto",
                    batch_size=2, fetch=_fetch(calls),
                    retrieved_at=dt.datetime(2026, 9, 22, 10))
        second = run(store, symbols, dt.date(2026, 9, 23), cycle="auto",
                     batch_size=2, fetch=_fetch(calls),
                     retrieved_at=dt.datetime(2026, 9, 23, 10))
        third = run(store, symbols, dt.date(2026, 9, 23), cycle="auto",
                    batch_size=2, fetch=_fetch(calls),
                    retrieved_at=dt.datetime(2026, 9, 23, 12))
        next_cycle = run(store, symbols, dt.date(2026, 9, 24), cycle="auto",
                         batch_size=2, fetch=_fetch(calls),
                         retrieved_at=dt.datetime(2026, 9, 24, 10))
        assert (first.processed, second.processed, third.processed, next_cycle.processed) == (2, 1, 0, 2)
        assert calls == ["A", "B", "C", "A", "B"]
