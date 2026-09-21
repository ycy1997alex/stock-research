"""Stock scoring refuses a frozen local price history."""

import datetime as dt

import pytest

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from research.pipeline import run_stock_scores


def test_frozen_stock_history_is_not_scored(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    first = dt.date(2026, 5, 1)
    bars = [
        PriceBar("2330.TW", first + dt.timedelta(days=day), 100, 101, 99,
                 100 + day * 0.1, 1000, "yfinance", dt.datetime(2026, 7, 1))
        for day in range(60)
    ]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)

    with pytest.raises(ValueError, match="凍結"):
        run_stock_scores.run(["2330.TW"], task="test_stock_freeze")

    with SqliteRepo(tmp_path / "market.db") as repo:
        assert repo.get_scores("stock", "2330.TW") == []
