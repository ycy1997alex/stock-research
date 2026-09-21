"""Fetch batch-three official Taiwan local observations once per dataset."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer import config  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402
from research import config as rc  # noqa: E402
from research.pipeline import tw_local  # noqa: E402
from research.storage.tw_local import TwLocalStore  # noqa: E402


def main() -> int:
    latest_by_symbol = {}
    for symbol in rc.TW_STOCKS:
        bars = csv_audit.read_current(symbol)
        if bars:
            latest_by_symbol[symbol] = bars[-1]
    if len(latest_by_symbol) != len(rc.TW_STOCKS):
        absent = sorted(set(rc.TW_STOCKS) - latest_by_symbol.keys())
        raise RuntimeError(f"台股價格序列缺少：{', '.join(absent)}")
    dates = {bar.date for bar in latest_by_symbol.values()}
    if len(dates) != 1:
        raise RuntimeError(f"台股最新交易日不一致：{sorted(d.isoformat() for d in dates)}")
    session_date = next(iter(dates))
    volumes = {symbol: bar.volume_shares for symbol, bar in latest_by_symbol.items()}
    closes = {symbol: bar.close for symbol, bar in latest_by_symbol.items()}

    config.ensure_dirs()
    with SqliteRepo(config.db_path()) as repo:
        repo.init_schema()
        result = tw_local.run(
            TwLocalStore(repo.conn), session_date, list(rc.TW_STOCKS),
            volume_shares_by_symbol=volumes, close_twd_by_symbol=closes,
        )
    for dataset in tw_local.FETCH_DATASETS:
        coverage = result.coverage.get(dataset)
        if coverage:
            print(f"{dataset}: {coverage.label('涵蓋率')}")
    for note in result.notes:
        print(f"! {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
