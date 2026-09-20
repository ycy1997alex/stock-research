"""0-3: T86 is fetched once for a day's batch and reused from storage."""

import datetime as dt

from barometer.storage.memory_repo import InMemoryRepo
from barometer.storage.sqlite_repo import SqliteRepo
from research.datasources import chips_tw


def test_same_day_batch_fetches_t86_only_once(monkeypatch):
    calls = []
    day = dt.date(2026, 9, 18)

    def fake_fetch(requested):
        calls.append(requested)
        return [{"symbol": "2330", "total_net_shares": 1200.0}]

    monkeypatch.setattr(chips_tw.twse_src, "fetch_t86", fake_fetch)
    repo = InMemoryRepo()
    first, _ = chips_tw.net_shares_by_symbol(["2330.TW", "2308.TW"], [day], repo=repo)
    second, _ = chips_tw.net_shares_by_symbol(["2330.TW", "2308.TW"], [day], repo=repo)

    assert calls == [day]
    assert first == second == {"2330.TW": [1200.0], "2308.TW": [None]}


def test_t86_cache_survives_new_process_repository(monkeypatch, tmp_path):
    calls = []
    day = dt.date(2026, 9, 18)

    def fake_fetch(requested):
        calls.append(requested)
        return [{"symbol": "2330", "total_net_shares": 1200.0}]

    monkeypatch.setattr(chips_tw.twse_src, "fetch_t86", fake_fetch)
    path = tmp_path / "chips.db"
    with SqliteRepo(path) as repo:
        repo.init_schema()
        first, _ = chips_tw.net_shares_by_symbol(["2330.TW", "2308.TW"], [day], repo=repo)
    with SqliteRepo(path) as repo:
        second, _ = chips_tw.net_shares_by_symbol(["2330.TW", "2308.TW"], [day], repo=repo)

    assert calls == [day]
    assert first == second == {"2330.TW": [1200.0], "2308.TW": [None]}
