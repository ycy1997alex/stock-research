"""Refresh official Taiwan and Yahoo issuer fundamentals for all 15 stocks."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from barometer import config as bconfig  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402
from research import config  # noqa: E402
from research.pipeline import fundamentals  # noqa: E402
from research.storage.fundamentals import FundamentalStore  # noqa: E402


def main(argv: list[str]) -> int:
    if argv:
        raise ValueError(f"unexpected arguments: {argv}")
    stamp = dt.datetime.now(ZoneInfo("Asia/Taipei"))
    with SqliteRepo(bconfig.db_path()) as repo:
        repo.init_schema()
        store = FundamentalStore(repo.conn)
        store.init_schema()
        result = fundamentals.refresh(store, config.TW_STOCKS,
                                      config.US_STOCKS + config.ADRS, stamp)
    for symbol in config.ALL_SYMBOLS:
        print(f"{symbol}: {result.coverage[symbol].label('基本面原始欄位')}")
    for note in result.notes:
        print(f"資料不足：{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
