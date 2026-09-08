"""Day 24 第 11 項（stock-research 獨有）：抓 §7.2 的 15 檔。

驗收：15 檔都有序列，SPCX 的筆數明顯偏少（§10）且被正確標記。

資料層與 market-barometer 共用 —— 這支只是換一組標的餵同一條管線。
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer.pipeline import fetch_prices  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from research import config as rc  # noqa: E402

# 一年約 244（台股）/ 252（美股）根；低於這個就是「資料不足」的候選
FULL_YEAR_MIN = 200


def main() -> int:
    symbols = list(rc.ALL_SYMBOLS)
    print(f"抓取 {len(symbols)} 檔（台股 {len(rc.TW_STOCKS)}、"
          f"美股 {len(rc.US_STOCKS)}、ADR {len(rc.ADRS)}）")
    log = fetch_prices.run(symbols, task="day24_stocks", period="1y")

    print(f"\nrun_id={log.run_id} status={log.status}")
    for n in log.notes:
        print(f"  ! {n}")

    print(f"\n{'標的':<10}{'名稱':<14}{'筆數':>6}{'期末收盤':>12}"
          f"{'近一年':>9}{'最新量':>14}  備註")
    print("-" * 92)
    short: list[str] = []
    missing: list[str] = []
    for sym in symbols:
        bars = csv_audit.read_current(sym)
        name = rc.NAMES.get(sym, "")
        if not bars:
            missing.append(sym)
            print(f"{sym:<10}{name:<14}{'—— 沒有資料 ——':>30}")
            continue

        closes = [b.close for b in bars if b.close is not None]
        ret = (closes[-1] / closes[0] - 1) * 100 if len(closes) > 1 else float("nan")
        vol = bars[-1].volume_shares or 0

        notes = []
        if len(bars) < FULL_YEAR_MIN:
            short.append(sym)
            notes.append(f"資料不足（<{FULL_YEAR_MIN} 根）→ 中/長期評分不得硬算")
        if sym in rc.THIN_LIQUIDITY:
            notes.append("薄流動性，量價與籌碼指標會失真")
        stale_n = sum(1 for b in bars if b.stale)
        if stale_n:
            notes.append(f"{stale_n} 格 stale")

        print(f"{sym:<10}{name:<14}{len(bars):>6}{closes[-1]:>12,.2f}"
              f"{ret:>+8.1f}%{vol:>14,.0f}  {'；'.join(notes)}")

    print(f"\n=== 驗收 ===")
    print(f"有序列的標的：{len(symbols) - len(missing)}/{len(symbols)}")
    print(f"筆數明顯偏少並被標記：{short or '（無）'}")

    ok = not missing and "SPCX" in short
    if not ok:
        if missing:
            print(f"FAIL 缺資料：{missing}")
        if "SPCX" not in short:
            print("FAIL SPCX 沒有被判為資料不足 —— §10 說它 2026-06-12 才上市")
    else:
        print("OK 15 檔都有序列，SPCX 被正確標記為資料不足")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
