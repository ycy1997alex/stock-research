"""個股籌碼面：從 T86 抽出單一檔的三大法人買賣超（ToDo §9 Day 26 第 5 項）。

T86 一次回全市場一萬多檔，所以**一天只抓一次、抽出要的那幾檔**，不是每檔各
打一次 —— 五檔台股 × 五天要是打二十五次，額度會很難看（§6 規則 5）。

單位是**股**，跟 price_daily 一致，所以買賣超除以成交量是可以直接除的。
這是整條管線裡少數兩個數字單位剛好相同的地方，其他地方都得小心。

美股與 ADR 沒有這種資料 —— 那一維就是不存在，**不是 0**。
"""
from __future__ import annotations

import datetime as dt

from barometer.datasources import twse_src
from barometer.datasources.base import FetchError


def _code(symbol: str) -> str:
    """2330.TW → 2330。T86 的證券代號沒有後綴。"""
    return symbol.split(".")[0]


def net_shares_by_symbol(
    symbols: list[str], dates: list[dt.date]
) -> tuple[dict[str, list[float | None]], list[str]]:
    """回 (每檔的逐日買賣超, 沒抓到的日期說明)。

    抓不到的那一天在序列裡是 **None，不是 0** —— 「還沒公布」與「當天真的
    沒有買賣超」是兩件事（§10）。
    """
    wanted = {_code(s): s for s in symbols}
    out: dict[str, list[float | None]] = {s: [] for s in symbols}
    notes: list[str] = []

    for date in dates:
        try:
            rows = twse_src.fetch_t86(date)
        except FetchError as exc:
            notes.append(f"{date}: {exc}")
            for s in symbols:
                out[s].append(None)
            continue

        got = {
            wanted[r["symbol"]]: r.get("total_net_shares")
            for r in rows
            if r["symbol"] in wanted
        }
        for s in symbols:
            out[s].append(got.get(s))

    return out, notes
