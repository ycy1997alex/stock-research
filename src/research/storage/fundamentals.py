"""Persist first-seen issuer fundamental snapshots without historical lookahead."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

from research.domain.fundamentals import (
    SINGLE_QUARTER, FundamentalReport, Metric, QuarterMetrics,
)


class FundamentalStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def init_schema(self) -> None:
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS stock_fundamental_snapshot ("
            "observed_date TEXT NOT NULL, symbol TEXT NOT NULL, payload_json TEXT NOT NULL,"
            "as_of TEXT NOT NULL, PRIMARY KEY(observed_date,symbol))"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_fundamental_symbol_date "
            "ON stock_fundamental_snapshot(symbol,observed_date)"
        )
        self.conn.commit()

    def _quarters_already_known(self, symbol: str, observed: str) -> dict[str, dict]:
        """同一個觀測日已經記下的季別。

        每日管線每次只帶一季；一次性回補（R-4）寫的也是同一列。整列覆蓋會讓當天
        稍早補進來的歷史在晚上的例行更新後安靜消失，所以這裡以季別為單位合併。
        """
        row = self.conn.execute(
            "SELECT payload_json FROM stock_fundamental_snapshot "
            "WHERE observed_date=? AND symbol=?", (observed, symbol),
        ).fetchone()
        if row is None:
            return {}
        return {item["period"]: item for item in json.loads(row[0]).get("quarters", [])}

    def put(self, report: FundamentalReport, stamp: dt.datetime) -> None:
        payload = {
            "industry": report.industry,
            "metrics": {key: {"value": metric.value, "source": metric.source,
                              "data_date": metric.data_date.isoformat() if metric.data_date else None,
                              "retrieved_at": metric.retrieved_at.isoformat() if metric.retrieved_at else None,
                              "period": metric.period, "note": metric.note}
                        for key, metric in report.metrics.items()},
            "quarters": [{"period": quarter.period, "gross_margin_pct": quarter.gross_margin_pct,
                          "data_date": quarter.data_date.isoformat() if quarter.data_date else None,
                          "basis": quarter.basis}
                         for quarter in report.quarters],
        }
        known = self._quarters_already_known(report.symbol, stamp.date().isoformat())
        known.update({item["period"]: item for item in payload["quarters"]})
        payload["quarters"] = [known[period] for period in sorted(known)]
        self.conn.execute(
            "INSERT INTO stock_fundamental_snapshot(observed_date,symbol,payload_json,as_of) "
            "VALUES(?,?,?,?) ON CONFLICT(observed_date,symbol) DO UPDATE SET "
            "payload_json=excluded.payload_json,as_of=excluded.as_of",
            (stamp.date().isoformat(), report.symbol,
             json.dumps(payload, ensure_ascii=False, sort_keys=True), stamp.isoformat()),
        )
        self.conn.commit()

    def get_asof(self, symbol: str, day: dt.date) -> FundamentalReport | None:
        rows = self.conn.execute(
            "SELECT payload_json FROM stock_fundamental_snapshot WHERE symbol=? "
            "AND observed_date<=? AND substr(as_of,1,10)<=? ORDER BY observed_date DESC",
            (symbol, day.isoformat(), day.isoformat()),
        ).fetchall()
        if not rows:
            return None
        latest = json.loads(rows[0][0])
        metrics = {key: Metric(value.get("value"), value.get("source", ""),
                               dt.date.fromisoformat(value["data_date"]) if value.get("data_date") else None,
                               dt.datetime.fromisoformat(value["retrieved_at"]) if value.get("retrieved_at") else None,
                               value.get("period"), value.get("note", ""))
                   for key, value in latest.get("metrics", {}).items()}
        quarters: dict[str, QuarterMetrics] = {}
        for row in rows:
            for value in json.loads(row[0]).get("quarters", []):
                quarters.setdefault(value["period"], QuarterMetrics(
                    value["period"], value.get("gross_margin_pct"),
                    dt.date.fromisoformat(value["data_date"]) if value.get("data_date") else None,
                    value.get("basis", SINGLE_QUARTER),
                ))
        return FundamentalReport(symbol, metrics,
                                 tuple(quarters[key] for key in sorted(quarters)),
                                 latest.get("industry"))
