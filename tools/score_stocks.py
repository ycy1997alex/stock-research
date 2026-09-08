"""Day 26 第 5、6 項：15 檔個股三期評分 + 五日加權。

驗收：
  1. 15 檔都有分數，**SPCX 的中期／長期回傳「資料不足」而不是硬算出來的數字**
  2. 五日加權用 §8.1 的同一組權重，輸出簡單平均與加權平均兩個數字

**五個交易日只有五個點 —— 定性觀察，不是統計證據。**
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer.domain import windows  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from research import config as rc  # noqa: E402
from research.datasources import chips_tw  # noqa: E402
from research.pipeline import run_stock_scores  # noqa: E402

QUALITATIVE = "五個交易日只有五個點，以下一律是定性觀察，不是統計證據。"


def main() -> int:
    symbols = list(rc.ALL_SYMBOLS)
    print("=== Day 26 第 5、6 項：個股三期評分 + 五日加權 ===")
    print(QUALITATIVE + "\n")

    # 台股才有三大法人資料 —— 一次抓全市場、抽出要的那五檔（§6 規則 5）
    tw_bars = csv_audit.read_current(rc.TW_STOCKS[0])
    tw_days = windows.last_n_sessions([b.date for b in tw_bars], 5)
    print(f"抓 T86（台股五檔，{len(tw_days)} 天，一天一次全市場）…")
    per_symbol, notes = chips_tw.net_shares_by_symbol(list(rc.TW_STOCKS), tw_days)
    for n in notes:
        print(f"  ! {n}")
    chips_by_symbol = {
        s: dict(zip(tw_days, series)) for s, series in per_symbol.items()
    }

    log = run_stock_scores.run(symbols, chips_by_symbol=chips_by_symbol)
    print(f"\nrun_id={log.run_id} status={log.status}")

    print(f"\n{'標的':<10}{'名稱':<14}{'筆數':>6}{'短期':>8}{'中期':>10}"
          f"{'長期':>10}{'籌碼':>8}{'簡單':>8}{'加權':>8}")
    print("-" * 92)

    spcx_ok = False
    scored_count = 0
    for sym in symbols:
        bars = csv_audit.read_current(sym)
        if not bars:
            print(f"{sym:<10}{'—— 沒有序列 ——'}")
            continue
        scored = run_stock_scores.score_series(
            sym, bars, net_by_date=chips_by_symbol.get(sym)
        )
        summary = run_stock_scores.summarize_window(scored)
        latest = scored[-1][1]

        def cell(t):
            return f"{t.score:.0f}" if t and t.score is not None else "不足"

        avg = summary["simple_average"]
        wavg = summary["weighted_average"]
        print(f"{sym:<10}{rc.NAMES.get(sym, ''):<14}{len(bars):>6}"
              f"{cell(latest.short):>8}{cell(latest.mid):>10}{cell(latest.long):>10}"
              f"{cell(latest.chips):>8}"
              f"{(f'{avg:.1f}' if avg is not None else '—'):>8}"
              f"{(f'{wavg:.1f}' if wavg is not None else '—'):>8}")

        if latest.overall is not None:
            scored_count += 1
        if sym == "SPCX":
            spcx_ok = latest.mid.score is None and latest.long.score is None
            print(f"           └ SPCX 中期：{latest.mid.reason}")
            print(f"           └ SPCX 長期：{latest.long.reason}")
        for c in latest.caveats:
            print(f"           └ {c}")

    print("\n--- 五日評分變化與平滑化（§8.1） ---")
    for sym in list(rc.TW_STOCKS) + ["NVDA", "SPCX"]:
        bars = csv_audit.read_current(sym)
        if not bars:
            continue
        scored = run_stock_scores.score_series(
            sym, bars, net_by_date=chips_by_symbol.get(sym)
        )
        s = run_stock_scores.summarize_window(scored)
        fmt = lambda xs: "  ".join(
            f"{x:>6.1f}" if x is not None else "     —" for x in xs
        )
        print(f"\n{sym} {rc.NAMES.get(sym, '')}")
        print(f"  日期    {'  '.join(d[5:] for d in s['dates'])}")
        print(f"  分數  {fmt(s['scores'])}")
        print(f"  變化  {fmt(s['changes'])}")
        print(f"  平滑  {fmt(s['smoothed'])}")

    print("\n=== 驗收 ===")
    print(f"有分數的標的：{scored_count}／{len(symbols)}")
    print("OK SPCX 中期與長期都是資料不足，沒有硬算"
          if spcx_ok else "FAIL SPCX 的中期或長期被硬算出數字了")
    return 0 if spcx_ok and scored_count == len(symbols) else 1


if __name__ == "__main__":
    raise SystemExit(main())
