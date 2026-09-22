"""Refresh Taiwan display names from the TWSE listed-company directory."""
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
from research import config  # noqa: E402
from research.pipeline import names  # noqa: E402


def main(argv: list[str]) -> int:
    if argv:
        raise ValueError(f"unexpected arguments: {argv}")
    records = names.refresh(bconfig.stockdata_root(), config.TW_STOCKS,
                            dt.datetime.now(ZoneInfo("Asia/Taipei")))
    config.refresh_display_names()
    for symbol in config.TW_STOCKS:
        print(f"{symbol}: {config.NAMES[symbol]}（{config.NAME_SOURCES[symbol]}）")
    print(f"官方名稱 {len(records)}/{len(config.TW_STOCKS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
