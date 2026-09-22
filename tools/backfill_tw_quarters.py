"""Manual one-off TW quarterly history from the MOPS cumulative summary.

`t187ap17_L` only publishes the newest season, so the daily pipeline can never
accumulate three quarters on its own from a standing start. Run this once with
--apply to seed older periods; afterwards the daily snapshots accumulate.

Backfilled quarters carry the retrieval date, never an inferred first release
date, and they are attached to today's observation so nothing is back-dated.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer import config  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402
from research import config as rc  # noqa: E402
from research.datasources import fundamentals as source  # noqa: E402
from research.pipeline.fundamentals import merge_quarter_history  # noqa: E402
from research.storage.fundamentals import FundamentalStore  # noqa: E402


def previous_periods(period: str, count: int) -> list[str]:
    """`2026Q2` 往回數 count 季，不含自己。"""
    year, quarter = (int(part) for part in period.split("Q"))
    out = []
    for _ in range(count):
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
        out.append(f"{year}Q{quarter}")
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-period", default="2026Q2",
                        help="往回數的起點（這一季本身不抓，日常管線已經有了）")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--apply", action="store_true",
                        help="備份資料庫後寫入；不加這個只預覽")
    args = parser.parse_args(argv)

    periods = previous_periods(args.from_period, args.count)
    stamp = dt.datetime.now()
    print(f"回補季別：{'、'.join(periods)}　標的 {len(rc.TW_STOCKS)} 檔")
    history = source.fetch_tw_quarter_history(periods, stamp)
    for symbol in rc.TW_STOCKS:
        got = history.get(symbol, ())
        print(f"  {symbol:<10}{len(got)}/{len(periods)} 季　"
              + "、".join(f"{q.period} {q.gross_margin_pct:.2f}%" for q in got
                          if q.gross_margin_pct is not None))
    if not args.apply:
        print("預覽完成；加 --apply 才會備份並寫入資料庫")
        return 0

    config.ensure_dirs()
    with SqliteRepo(config.db_path()) as repo:
        repo.init_schema()
        backup_dir = config.stockdata_root() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"market_pre_tw_quarters_{stamp:%Y%m%d_%H%M%S}.db"
        with sqlite3.connect(backup) as target:
            repo.conn.backup(target)
        print(f"資料庫備份：{backup}")
        store = FundamentalStore(repo.conn)
        store.init_schema()
        filled = merge_quarter_history(store, rc.TW_STOCKS, history, stamp)
    for symbol, count in filled.items():
        print(f"  {symbol:<10}併入後 {count} 季")
    return 0 if all(count >= 3 for count in filled.values()) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
