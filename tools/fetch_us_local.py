"""Refresh dated US institutional, insider and analyst observations."""
from __future__ import annotations

import argparse
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
from research.pipeline import us_local  # noqa: E402
from research.storage.us_local import UsLocalStore  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", help="default: configured US stocks and ADRs")
    parser.add_argument("--as-of", type=dt.date.fromisoformat,
                        default=dt.datetime.now(ZoneInfo("Asia/Taipei")).date())
    args = parser.parse_args(argv)
    symbols = args.symbols or list(config.US_STOCKS + config.ADRS)
    with SqliteRepo(bconfig.db_path()) as repo:
        repo.init_schema()
        result = us_local.run(UsLocalStore(repo.conn), symbols, args.as_of)
    for name, count in result.coverage.items():
        print(f"{name}: {count}/{len(symbols)}")
    for note in result.notes:
        print(f"資料不足：{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
