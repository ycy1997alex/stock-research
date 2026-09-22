import datetime as dt

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from research import config
from research.pipeline import rebuild_stock_history


def test_rebuild_cli_uses_configured_symbols_and_preserves_other_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "ALL_SYMBOLS", ("AAPL",))
    day = dt.date(2025, 1, 1)
    bars = [PriceBar("AAPL", day + dt.timedelta(days=i), 100 + i * .2,
                     101 + i * .2, 99 + i * .2, 100 + i * .2, 100_000,
                     "test", dt.datetime(2026, 9, 21)) for i in range(70)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
        repo.put_score("index", "SPY", day, 88, {}, "adjusted-v1")
    from tools.rebuild_stock_scores import main
    assert main([]) == 0
    with SqliteRepo(tmp_path / "market.db") as repo:
        assert repo.get_scores("stock", "AAPL")
        assert repo.get_scores("index", "SPY")[0].score == 88
