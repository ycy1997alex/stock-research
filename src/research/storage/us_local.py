"""Store US observations by first observed snapshot day, not old report period.

The payload retains the underlying report date. This prevents a 13F period-end
date from making a snapshot first fetched today visible to a historical replay.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3


class UsLocalStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def put(self, symbol: str, dimension: str, data_date: dt.date,
            value: dict, source: str, retrieved_at: dt.datetime) -> None:
        if dimension not in {"institutional", "insider", "analyst"}:
            raise ValueError(dimension)
        payload = {"value": value, "source": source,
                   "data_date": data_date.isoformat(), "retrieved_at": retrieved_at.isoformat()}
        self.conn.execute(
            "INSERT INTO us_stock_local(date,symbol,dimension,payload_json,as_of) VALUES(?,?,?,?,?) "
            "ON CONFLICT(date,symbol,dimension) DO UPDATE SET payload_json=excluded.payload_json,as_of=excluded.as_of",
            (retrieved_at.date().isoformat(), symbol, dimension,
             json.dumps(payload, ensure_ascii=False, sort_keys=True), retrieved_at.isoformat()),
        )
        self.conn.commit()

    def get_asof(self, day: dt.date, symbol: str) -> dict[str, dict]:
        records: dict[str, dict] = {}
        for dimension, payload in self.conn.execute(
            "SELECT dimension,payload_json FROM us_stock_local "
            "WHERE symbol=? AND date<=? AND substr(as_of,1,10)<=? ORDER BY date DESC",
            (symbol, day.isoformat(), day.isoformat()),
        ):
            records.setdefault(dimension, json.loads(payload))
        return records
