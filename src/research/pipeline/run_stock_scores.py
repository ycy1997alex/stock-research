"""個股評分管線 + 五日加權（ToDo §9 Day 26 第 5、6 項）。

驗收：15 檔都有分數、SPCX 的中期／長期回傳「資料不足」而不是硬算；五日加權
用 §8.1 的同一組權重（10/15/20/25/30），輸出簡單平均與加權平均兩個數字。

**權重跟 market-barometer 共用同一支 `weighting.py`** —— 三個層級（總經、
大盤、個股）用同一組權重是 §8.1 明寫的，各自複製一份遲早會有一份先改。

逐日回算的規則跟大盤那側一樣：算 D 那天的分數時只餵 D 為止的序列。
"""
from __future__ import annotations

import datetime as dt

from barometer.domain import weighting, windows
from barometer.pipeline.runlog import RunLog
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo
from barometer import config as bconfig

from research.domain import scoring_stock

SCOPE = "stock"
WINDOW = 5


def score_series(
    symbol: str,
    bars: list,
    window: int = WINDOW,
    net_by_date: dict[dt.date, float | None] | None = None,
) -> list[tuple[dt.date, scoring_stock.StockScore]]:
    session_days = windows.last_n_sessions([b.date for b in bars], window)
    out = []
    for day in session_days:
        upto = [b for b in bars if b.date <= day]
        closes = [b.close for b in upto]
        net_series = vol_series = None
        if net_by_date:
            recent = upto[-window:]
            net_series = [net_by_date.get(b.date) for b in recent]
            vol_series = [b.volume_shares for b in recent]
        out.append(
            (day, scoring_stock.score_stock(symbol, closes, net_series, vol_series))
        )
    return out


def summarize_window(scored: list[tuple[dt.date, scoring_stock.StockScore]]) -> dict:
    """§8.1 的五日加權。**五個點，定性觀察，不是統計證據。**

    不滿五天**直接報錯，不降級**（2026-09-08 定案）。管線安靜產出一份少了
    幾檔的結果，比整支失敗糟得多 —— 沒有人會去比對「今天怎麼少了兩檔」。

    這一側特別容易撞到：**SPCX 2026-06-12 才上市**，而 `last_n_sessions`
    的規則是「不足 n 天就給有幾天算幾天 —— 不補、不外推」。

    桌面 Presenter 那一側刻意相反（回 None 並標「資料不足（N/5 天）」），
    差別在「有沒有人正在看著」：畫面不能整頁掛掉，批次可以也應該。

    訊息要講出**是哪一檔、幾天、哪幾天** —— `weighting` 自己的錯誤只說
    「收到 3 個」，15 檔跑到一半炸掉時那句話沒有任何幫助。
    """
    if len(scored) != WINDOW:
        symbol = scored[0][1].symbol if scored else "（空序列）"
        days = "、".join(d.isoformat() for d, _ in scored) or "無"
        raise ValueError(
            f"{symbol}：五日視窗需要恰好 {WINDOW} 個交易日，"
            f"只有 {len(scored)}/{WINDOW} 天（{days}）。"
            "新上市或剛加進清單的標的會這樣 —— 補足交易日，或把它排除在這次評分之外。"
        )

    values = [s.overall for _, s in scored]
    return {
        "dates": [d.isoformat() for d, _ in scored],
        "scores": values,
        "simple_average": weighting.simple_average(values),
        "weighted_average": weighting.weighted_average(values),
        "smoothed": weighting.smooth(values),
        "changes": [
            None if values[i] is None or values[i - 1] is None
            else values[i] - values[i - 1]
            for i in range(len(values))
        ],
        "qualitative_only": True,
    }


def run(
    symbols: list[str],
    task: str = "scores_stock",
    window: int = WINDOW,
    chips_by_symbol: dict[str, dict[dt.date, float | None]] | None = None,
    price_version: str = "v1",
) -> RunLog:
    log = RunLog(task=task)
    bconfig.ensure_dirs()
    repo = SqliteRepo(bconfig.db_path())
    repo.init_schema()

    try:
        for symbol in symbols:
            bars = csv_audit.read_current(symbol)
            if not bars:
                log.count("no_data")
                log.note(f"{symbol}: 本機沒有序列，跳過")
                continue

            scored = score_series(
                symbol, bars, window,
                (chips_by_symbol or {}).get(symbol),
            )
            wrote = 0
            for day, s in scored:
                if s.overall is None:
                    log.note(f"{symbol} {day}: 三期都算不出來，不寫分數")
                    continue
                subs = {
                    k: v["score"]
                    for k, v in s.to_dict().items()
                    if k in ("short", "mid", "long", "chips")
                    and isinstance(v, dict) and v["score"] is not None
                }
                repo.put_score(
                    scope=SCOPE, symbol=symbol, as_of=day, score=s.overall,
                    subscores=subs, price_version=price_version,
                )
                wrote += 1

            latest = scored[-1][1]
            if latest.mid.score is None:
                log.count("mid_insufficient")
                log.note(f"{symbol}: 中期 {latest.mid.reason}")
            if latest.long.score is None:
                log.count("long_insufficient")
                log.note(f"{symbol}: 長期 {latest.long.reason}")
            for c in latest.caveats:
                log.note(f"{symbol}: {c}")

            summary = summarize_window(scored)
            log.set_count(f"scored::{symbol}", wrote)
            if summary["weighted_average"] is not None:
                log.set_count(f"wavg::{symbol}", round(summary["weighted_average"], 1))
            log.count("symbols_ok")

        log.finish("partial" if log.counts.get("no_data") else "ok")
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    except Exception as exc:
        # **記完 runlog 再重拋**（跟 barometer 的 run_scores 同一個處置）。
        # 失敗要大聲（所以重拋），但不能連「跑過、失敗在哪裡」都不留下 ——
        # 沒有紀錄的失敗，事後跟「排程根本沒觸發」長得一模一樣。
        #
        # 已經累積的 counts 與 notes 全部留著，那是「跑到哪裡」的唯一線索。
        log.note(f"中止：{type(exc).__name__}: {exc}")
        log.finish("error")
        try:
            repo.record_run(
                run_id=log.run_id, task=log.task, started_at=log.started_at,
                ended_at=log.ended_at, status=log.status,
                counts=log.counts, quota=log.quota,
            )
        except Exception:  # noqa: BLE001
            # 資料庫也壞掉的時候至少保住 jsonl 那一份。
            # 這裡再拋一次會蓋掉原本的錯誤，那才是真的難查。
            pass
        log.append()
        raise
    finally:
        repo.close()

    log.append()
    return log
