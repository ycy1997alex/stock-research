"""Stock indicators use derived total-return prices while the displayed source stays current."""
import datetime as dt

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from research.pipeline import run_stock_scores


def test_stock_score_loader_reads_adjusted_prices(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    bars = [PriceBar("2330.TW", dt.date(2026, 9, 14) + dt.timedelta(days=i),
                     42, 43, 41, 42 + i * .1, 1000, "yfinance",
                     dt.datetime(2026, 9, 18, 18)) for i in range(5)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
    monkeypatch.setattr(run_stock_scores.csv_audit, "read_current", lambda _: (_ for _ in ()).throw(AssertionError("current fed to indicator")))
    seen = []
    original = run_stock_scores.score_series
    def score(symbol, prices, window, chips, **kwargs):
        seen.extend(prices)
        return original(symbol, prices, window, chips, **kwargs)
    monkeypatch.setattr(run_stock_scores, "score_series", score)
    run_stock_scores.run(["2330.TW"], run_date=dt.date(2026, 9, 18))
    assert seen == bars


def test_stock_score_marks_the_adjusted_price_version(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    days = [dt.date(2026, 9, 18) - dt.timedelta(days=i) for i in range(320)]
    days = sorted(day for day in days if day.weekday() < 5)
    bars = [PriceBar("2330.TW", day, 100+i, 101+i, 99+i, 100+i,
                     1000, "yfinance", dt.datetime(2026, 9, 18, 18))
            for i, day in enumerate(days)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
    run_stock_scores.run(["2330.TW"], run_date=dt.date(2026, 9, 18))
    with SqliteRepo(tmp_path / "market.db") as repo:
        scores = repo.get_scores("stock", "2330.TW")
    assert scores and all(row.price_version == "adjusted-v1" for row in scores)
