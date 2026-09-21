"""Persist official Taiwan local observations in the shared SQLite schema."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3


class TwLocalStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    @staticmethod
    def _dump(value: dict) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _load(row: tuple | None) -> dict | None:
        return json.loads(row[0]) if row else None

    def put_stock_daily(self, day: dt.date, symbol: str, dataset: str, value: dict, stamp: dt.datetime) -> None:
        prior = self.get_stock_daily(day, symbol) or {}
        prior[dataset] = value
        self.conn.execute(
            "INSERT INTO tw_stock_daily(date,symbol,payload_json,as_of) VALUES(?,?,?,?) "
            "ON CONFLICT(date,symbol) DO UPDATE SET payload_json=excluded.payload_json,as_of=excluded.as_of",
            (day.isoformat(), symbol, self._dump(prior), stamp.isoformat()),
        )
        self.conn.commit()

    def get_stock_daily(self, day: dt.date, symbol: str) -> dict | None:
        row = self.conn.execute("SELECT payload_json FROM tw_stock_daily WHERE date=? AND symbol=?",
                                (day.isoformat(), symbol)).fetchone()
        return self._load(row)

    def get_stock_daily_asof(self, day: dt.date, symbol: str) -> dict:
        """Latest known observation per source, each retaining its own date."""
        observations: dict = {}
        for row in self.conn.execute(
            "SELECT payload_json FROM tw_stock_daily WHERE date<=? AND symbol=? ORDER BY date DESC",
            (day.isoformat(), symbol),
        ):
            for dataset, value in json.loads(row[0]).items():
                observations.setdefault(dataset, value)
        return observations

    def put_market_daily(self, day: dt.date, dataset: str, value: dict, stamp: dt.datetime) -> None:
        prior = self.get_market_daily(day) or {}
        prior[dataset] = value
        self.conn.execute(
            "INSERT INTO tw_market_daily(date,payload_json,as_of) VALUES(?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET payload_json=excluded.payload_json,as_of=excluded.as_of",
            (day.isoformat(), self._dump(prior), stamp.isoformat()),
        )
        self.conn.commit()

    def get_market_daily(self, day: dt.date) -> dict | None:
        row = self.conn.execute("SELECT payload_json FROM tw_market_daily WHERE date=?", (day.isoformat(),)).fetchone()
        return self._load(row)

    def get_market_daily_asof(self, day: dt.date) -> dict:
        for row in self.conn.execute(
            "SELECT payload_json FROM tw_market_daily WHERE date<=? ORDER BY date DESC LIMIT 1",
            (day.isoformat(),),
        ):
            return json.loads(row[0])
        return {}

    def record_run(self, run_id: str, task: str, started_at: dt.datetime,
                   ended_at: dt.datetime | None, status: str, counts: dict) -> None:
        self.conn.execute(
            "INSERT INTO run_log(run_id,task,started_at,ended_at,status,counts_json,quota_json) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, task, started_at.isoformat(), ended_at.isoformat() if ended_at else None,
             status, self._dump(counts), self._dump({})),
        )
        self.conn.commit()

    def put_stock_weekly(self, day: dt.date, symbol: str, value: dict, stamp: dt.datetime) -> None:
        self.conn.execute(
            "INSERT INTO tw_stock_weekly(date,symbol,payload_json,as_of) VALUES(?,?,?,?) "
            "ON CONFLICT(date,symbol) DO UPDATE SET payload_json=excluded.payload_json,as_of=excluded.as_of",
            (day.isoformat(), symbol, self._dump(value), stamp.isoformat()),
        )
        self.conn.commit()

    def get_stock_weekly(self, day: dt.date, symbol: str) -> dict | None:
        row = self.conn.execute(
            "SELECT payload_json FROM tw_stock_weekly WHERE date<=? AND symbol=? ORDER BY date DESC LIMIT 1",
            (day.isoformat(), symbol),
        ).fetchone()
        return self._load(row)

    def put_stock_monthly(self, period: str, symbol: str, day: dt.date, value: dict, stamp: dt.datetime) -> None:
        self.conn.execute(
            "INSERT INTO tw_stock_monthly(period,symbol,data_date,payload_json,as_of) VALUES(?,?,?,?,?) "
            "ON CONFLICT(period,symbol) DO UPDATE SET data_date=excluded.data_date,payload_json=excluded.payload_json,as_of=excluded.as_of",
            (period, symbol, day.isoformat(), self._dump(value), stamp.isoformat()),
        )
        self.conn.commit()

    def get_stock_monthly(self, day: dt.date, symbol: str) -> dict | None:
        row = self.conn.execute(
            "SELECT payload_json FROM tw_stock_monthly WHERE data_date<=? AND symbol=? "
            "ORDER BY data_date DESC,period DESC LIMIT 1",
            (day.isoformat(), symbol),
        ).fetchone()
        return self._load(row)
