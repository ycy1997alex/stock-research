"""Replace legacy stock history with the directional fifth-batch scale.

Back up market.db before running this one-time migration. Index and macro scores
are left intact; all configured stock symbols must have adjusted price history.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer import config as bconfig  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402
from research import config  # noqa: E402
from research.pipeline.rebuild_stock_history import rebuild  # noqa: E402


def main(argv: list[str]) -> int:
    if argv:
        raise ValueError(f"unexpected arguments: {argv}")
    with SqliteRepo(bconfig.db_path()) as repo:
        repo.init_schema()
        count = rebuild(repo, config.ALL_SYMBOLS)
    print(f"Rebuilt {count} stock score rows for {len(config.ALL_SYMBOLS)} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
