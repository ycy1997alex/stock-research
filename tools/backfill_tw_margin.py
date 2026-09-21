"""Manual first-time TWTA1U history for the inferred margin cost basis.

Daily publishing only fetches its latest session. Use --apply explicitly to
seed a longer estimate history. This does not rewrite any price history.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer import config  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402
from research import config as rc  # noqa: E402
from research.pipeline.tw_local import backfill_margin_history  # noqa: E402
from research.storage.tw_local import TwLocalStore  # noqa: E402


def sessions_with_closes(count: int) -> dict[dt.date, dict[str, float]]:
    if count < 2:
        raise ValueError("at least two sessions are needed to move beyond the seed")
    by_symbol = {}
    for symbol in rc.TW_STOCKS:
        bars = csv_audit.read_current(symbol)
        by_symbol[symbol] = {
            bar.date: float(bar.close)
            for bar in bars
            if bar.date.weekday() < 5 and not bar.stale
            and bar.close is not None and math.isfinite(bar.close) and bar.close > 0
        }
    common = sorted(set.intersection(*(set(rows) for rows in by_symbol.values())))
    if len(common) < count:
        raise ValueError(f"only {len(common)} common price sessions; requested {count}")
    return {day: {symbol: rows[day] for symbol, rows in by_symbol.items()}
            for day in common[-count:]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=60)
    parser.add_argument("--apply", action="store_true", help="backup database, then fetch and store history")
    args = parser.parse_args(argv)
    closes = sessions_with_closes(args.sessions)
    days = list(closes)
    print(f"TWTA1U 歷史推算：{len(days)} 個共同交易日，{days[0]} ～ {days[-1]}，{len(rc.TW_STOCKS)} 檔")
    if not args.apply:
        print("預覽完成；加 --apply 才會備份並寫入資料庫")
        return 0

    config.ensure_dirs()
    with SqliteRepo(config.db_path()) as repo:
        repo.init_schema()
        backup_dir = config.stockdata_root() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"market_pre_tw_margin_{stamp}.db"
        with sqlite3.connect(backup) as target:
            repo.conn.backup(target)
        print(f"資料庫備份：{backup}")
        coverage = backfill_margin_history(TwLocalStore(repo.conn), closes, rc.TW_STOCKS)
    latest = coverage.get(days[-1])
    print(f"有效交易日：{len(coverage)}/{len(days)}")
    print(f"最新日期涵蓋率：{latest.label('融資推算') if latest else '資料不足'}")
    return 0 if latest and latest.available == len(rc.TW_STOCKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
