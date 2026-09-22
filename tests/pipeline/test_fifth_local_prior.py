import datetime as dt
import sqlite3

from barometer.storage.sqlite_repo import SqliteRepo
from research.pipeline.tw_local import local_view
from research.storage.tw_local import TwLocalStore


def test_local_view_adds_prior_observation_without_changing_stored_value(tmp_path):
    day = dt.date(2026, 9, 21)
    with SqliteRepo(tmp_path / "db.sqlite") as repo:
        repo.init_schema()
        store = TwLocalStore(repo.conn)
        stamp = dt.datetime(2026, 9, 21, 20)
        def record(date, value):
            return {"value": value, "source": "test", "data_date": date.isoformat(),
                    "retrieved_at": stamp.isoformat()}
        store.put_stock_daily(day-dt.timedelta(days=3), "2330.TW", "foreign",
                              record(day-dt.timedelta(days=3), {"foreign_holding_pct": 60}), stamp)
        store.put_stock_daily(day, "2330.TW", "foreign",
                              record(day, {"foreign_holding_pct": 61}), stamp)
        view = local_view(store, "2330.TW", day)
        assert view["local"]["foreign"]["previous_foreign_holding_pct"] == 60
        assert store.get_stock_daily(day, "2330.TW")["foreign"]["value"] == {"foreign_holding_pct": 61}
