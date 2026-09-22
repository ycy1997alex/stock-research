"""Historical engineering report for directional and native-score calibration."""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from barometer import config as bconfig  # noqa: E402
from barometer.domain.backtest import BacktestParams, run_backtest  # noqa: E402
from barometer.domain.ports import PriceBar  # noqa: E402
from research import config  # noqa: E402
from research.domain import legacy_scoring_stock, local_stock, scoring_stock  # noqa: E402
from research.domain.calibration import calibrate_weight  # noqa: E402
from research.pipeline import tw_local  # noqa: E402
from research.storage.tw_local import TwLocalStore  # noqa: E402
from research.storage.us_local import UsLocalStore  # noqa: E402


def _bars(conn: sqlite3.Connection, symbol: str) -> list[PriceBar]:
    rows = conn.execute("SELECT * FROM price_adjusted WHERE symbol=? AND stale=0 ORDER BY date", (symbol,))
    return [PriceBar(symbol, dt.date.fromisoformat(row["date"]),
                     row["open"], row["high"], row["low"], row["close"],
                     row["volume_shares"], row["source"],
                     dt.datetime.fromisoformat(row["as_of"]), bool(row["stale"])) for row in rows]


def _score(symbol: str, bars: list[PriceBar]) -> scoring_stock.StockScore:
    return scoring_stock.score_stock(
        symbol, [bar.close for bar in bars],
        opens=[bar.open for bar in bars], highs=[bar.high for bar in bars],
        lows=[bar.low for bar in bars], volumes=[bar.volume_shares for bar in bars],
        native_weight=0,
    )


def _first_date(conn: sqlite3.Connection, table: str, symbol: str) -> dt.date | None:
    column = "as_of" if table == "us_stock_local" else "date"
    row = conn.execute(f"SELECT MIN(substr({column},1,10)) FROM {table} WHERE symbol=?", (symbol,)).fetchone()
    return dt.date.fromisoformat(row[0]) if row and row[0] else None


def _samples(conn: sqlite3.Connection, symbol: str, tw: TwLocalStore,
             us: UsLocalStore) -> tuple[list[tuple[float | None, float | None]], int]:
    bars = _bars(conn, symbol)
    is_tw = symbol.endswith((".TW", ".TWO"))
    first = _first_date(conn, "tw_stock_daily" if is_tw else "us_stock_local", symbol)
    if first is None:
        return [], 0
    samples: list[tuple[float | None, float | None]] = []
    stale = 0
    for i, bar in enumerate(bars):
        if bar.date < first or i < 20:
            continue
        technical = _score(symbol, bars[:i+1]).technical
        if is_tw:
            result = local_stock.score_tw_local(tw_local.local_view(tw, symbol, bar.date), bar.date)
        else:
            result = local_stock.score_us_local(us.get_asof(bar.date, symbol), bar.date)
        stale += sum(item.status == "過期" for item in result.items)
        samples.append((technical, result.score))
    return samples, stale


def _distribution(values: list[float]) -> str:
    if not values:
        return "資料不足"
    ordered = sorted(values)
    return f"最小 {ordered[0]:+.1f}；中位 {ordered[len(ordered)//2]:+.1f}；最大 {ordered[-1]:+.1f}"


def build_report(db_path: Path) -> str:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tw, us = TwLocalStore(conn), UsLocalStore(conn)
        configs = (("TW", config.TW_STOCKS, (0, .05, .10, .15, .25, .40)),
                   ("US", config.US_STOCKS + config.ADRS, (0, .05, .10, .15, .20)))
        lines = ["# 第五批雙分數歷史工程報告", "",
                 "此報告只用資料涵蓋、延遲及原始差距分布挑選本地權重；未用未來報酬調參。",
                 "", "## 本地權重候選", "",
                 "| 市場 | 歷史樣本 | 有效本地涵蓋 | 過期項次數 | 候選權重與原始差距 P90 | 選定權重 |",
                 "|---|---:|---:|---:|---|---:|"]
        for market, symbols, candidates in configs:
            samples: list[tuple[float | None, float | None]] = []
            stale = 0
            for symbol in symbols:
                got, count = _samples(conn, symbol, tw, us)
                samples.extend(got)
                stale += count
            result = calibrate_weight(samples, candidates)
            candidate_text = "；".join(f"{item.weight:.0%}→{item.p90_gap:.1f}" if item.p90_gap is not None
                                      else f"{item.weight:.0%}→缺料" for item in result.candidates)
            lines.append(f"| {market} | {result.sessions} | {result.coverage:.0%} | {stale} | {candidate_text} | {result.selected:.0%} |")
        lines.extend(["", "選定規則：至少 30 個市場日樣本、本地涵蓋至少 50%，取原始差距絕對值 P90 不超過 15 分的最大候選權重；不足時為 0。樣本從各標的首筆本地資料可用日開始，公開申報期間不等於資料首次可用日。",
                      "", "## 2330.TW 同段新舊尺對照", "",
                      "| 日期 | 舊尺 0～100 | 新尺可比 −100～100 | 短期 | 中期 | 長期 | 強度 C |",
                      "|---|---:|---:|---:|---:|---:|---:|"])
        bars = _bars(conn, "2330.TW")
        for i in range(max(0, len(bars)-5), len(bars)):
            prefix = bars[:i+1]
            new = _score("2330.TW", prefix)
            old = legacy_scoring_stock.score_stock("2330.TW", [bar.close for bar in prefix])
            def fmt(value):
                return f"{value:+.1f}" if value is not None else "資料不足"
            lines.append(f"| {bars[i].date} | {fmt(old.overall)} | {fmt(new.comparable)} | {fmt(new.short.score)} | {fmt(new.mid.score)} | {fmt(new.long.score)} | {fmt(new.strength)} |")
        lines.extend(["", "舊尺與新尺的零點不同；這張表用於核對計算與缺項處置，不以兩者差額評估準確率。",
                      "", "## 1-5 回測引擎工程檢查", ""])
        if len(bars) >= 42:
            result = run_backtest(bars, BacktestParams(market="tw", warmup_bars=40),
                                  lambda prefix: _score("2330.TW", list(prefix)).comparable)
            compounded = 1.0
            for trade in result.trades:
                compounded *= 1 + trade.ret_pct / 100
            error_pct = abs(result.equity[-1] - compounded) * 100
            scores = [score for score in result.scores if score is not None]
            lines.extend([f"訊號只看當日收盤前綴，交易於下一根開盤執行；共 {len(result.dates)} 個市場日、{len(result.trades)} 筆交易。",
                          "", f"方向分分布：{_distribution(scores)}。",
                          "", f"期末淨值與交易逐筆複利差 {error_pct:.3f} 個百分點（門檻 0.5）。"])
            if error_pct >= .5:
                raise ValueError(f"backtest accounting mismatch: {error_pct:.3f}%")
        else:
            lines.append("2330.TW 歷史不足，無法進行 t+1 開盤回測。")
        lines.extend(["", "本報告不從未來 20 日報酬、績效或勝率反推權重與指標門檻。", ""])
        return "\n".join(lines)
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=bconfig.db_path())
    args = parser.parse_args(argv)
    report = build_report(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
