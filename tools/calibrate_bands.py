"""Empirical distribution of the ±100 star bands (ToDo §7.2, batch 8-12).

The second ruler. The world-layer alert thresholds are calibrated separately in
market-barometer/tools/calibrate_alerts.py — the two scales do not share a
conclusion (§7.2).

Pure read: counts how the stored score history falls into the nine bands. It
changes no cutpoints and never looks at future returns (§8).

Usage: python tools/calibrate_bands.py [--output report.md]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer import config  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402
from research import config as rc  # noqa: E402
from research.domain.scoring_stock import to_stars  # noqa: E402

BANDS = ("強力賣出", "賣出", "偏空", "略偏空", "中性觀望",
         "略偏多", "偏多", "買進", "強力買進")


def collect(repo: SqliteRepo) -> tuple[dict, dict, int]:
    comparable: collections.Counter[str] = collections.Counter()
    native: collections.Counter[str] = collections.Counter()
    total = 0
    for symbol in rc.ALL_SYMBOLS:
        for record in repo.get_scores("stock", symbol):
            total += 1
            if record.comparable is not None:
                comparable[to_stars(record.comparable)["label"]] += 1
            if record.native is not None:
                native[to_stars(record.native)["label"]] += 1
    return comparable, native, total


def build_report(comparable, native, total: int) -> str:
    lines = [
        "# ±100 分數帶的實證分布（8-12，第二把尺）",
        "",
        f"樣本：`score_history` 的 stock 列共 {total:,} 筆（{dt.date.today()}）。",
        "",
        "⚠️ 這是**分布統計不是準確率**：沒有任何一欄跟未來報酬有關（§8）。",
        "⚠️ 與 barometer 的警示比例尺**各算各的**，不共用結論（§7.2）。",
        "",
        "| 分數帶 | 切點 | 可比分數筆數 | 佔比 | 本地分數筆數 | 佔比 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    cuts = {"強力買進": "≥ +80", "買進": "+60 ~ +80", "偏多": "+40 ~ +60",
            "略偏多": "+20 ~ +40", "中性觀望": "−20 ~ +20", "略偏空": "−40 ~ −20",
            "偏空": "−60 ~ −40", "賣出": "−80 ~ −60", "強力賣出": "≤ −80"}
    c_total = sum(comparable.values()) or 1
    n_total = sum(native.values()) or 1
    for band in reversed(BANDS):
        lines.append(
            f"| {band} | {cuts.get(band, '—')} | {comparable.get(band, 0):,} | "
            f"{comparable.get(band, 0) / c_total * 100:.1f}% | {native.get(band, 0):,} | "
            f"{native.get(band, 0) / n_total * 100:.1f}% |")
    lines += [
        "",
        "怎麼讀：切點如果讓某一帶幾乎永遠是空的，那一帶在實務上不存在；",
        "如果中性帶吃掉絕大多數樣本，這把尺在多數時間說不出話。兩種都是切點的問題，",
        "不是分數算錯。**調門檻與調分數帶切點擇一**，不要兩個都做。",
        "",
        "本報告不改任何切點。",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    with SqliteRepo(config.db_path()) as repo:
        repo.init_schema()
        comparable, native, total = collect(repo)
    report = build_report(comparable, native, total)
    print(report, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"\n寫出 {args.output}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
