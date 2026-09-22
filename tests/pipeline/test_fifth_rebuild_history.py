import datetime as dt

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from research.pipeline.rebuild_stock_history import rebuild


def test_rebuild_replaces_legacy_scale_without_touching_index_scores(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    day = dt.date(2025, 1, 1)
    bars = [PriceBar("AAPL", day+dt.timedelta(days=i), 100+i*.2, 101+i*.2,
                     99+i*.2, 100+i*.2, 100_000, "test", dt.datetime(2026,9,21))
            for i in range(70)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
        repo.put_score("stock", "AAPL", day, 99, {}, "adjusted-v1")
        repo.put_score("index", "SPY", day, 88, {}, "adjusted-v1")
        count = rebuild(repo, ["AAPL"])
        scores = repo.get_scores("stock", "AAPL")
        assert count > 0
        assert all(row.as_of != day for row in scores)
        assert all(row.comparable is not None and row.native is not None for row in scores)
        assert repo.get_scores("index", "SPY")[0].score == 88


def test_rebuild_does_not_score_stale_forward_filled_price(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    day = dt.date(2025, 1, 1)
    bars = [PriceBar("AAPL", day + dt.timedelta(days=i), 100 + i * .2,
                     101 + i * .2, 99 + i * .2, 100 + i * .2, 100_000,
                     "test", dt.datetime(2026, 9, 21), i == 70)
            for i in range(71)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
        rebuild(repo, ["AAPL"])
        scored_days = {row.as_of for row in repo.get_scores("stock", "AAPL")}
        assert day + dt.timedelta(days=70) not in scored_days
        assert day + dt.timedelta(days=69) in scored_days
