"""stock-research 的兩個分頁：台股權值股 / 美股權值股（ToDo §2、§7.2）。

**沿用 market-barometer 的 render/page.py**，只換一組 view model 的內容 ——
兩個站刻意用同一支渲染器，Day 27 才講得清楚「同一套機制、兩種鎖」。

與 market-barometer 唯一的差別是 `enforce_lint=False`：
這個 repo **可以**有買賣與短中長線建議（§2.1）。那條線畫在內容本身，
所以由呼叫端決定要不要開 lint，而不是由渲染器自己猜。

⚠️ 這裡的內容只有自己看。「私有 ≠ 可以對外分享」—— 一次「傳給朋友看」，
§2 的全部前提就失效（§12 第 8 條）。
"""
from __future__ import annotations

from barometer.render.page import Row, Tab

from research import config as rc
from research.domain import scoring_stock

TW_INTRO = (
    "台股五大權值股。顯示單位「張」，資料層一律存「股」，換算只在顯示層做。"
)
US_INTRO = (
    "美股七檔權值股 + 三檔台灣 ADR。顯示單位「股」。"
    "同一家公司的台股與 ADR 可以互看：2330/TSM、2317/HNHPF、3711/ASX。"
)

FOOTER = (
    "這是**加了鎖的公開頁面**，不是私密頁面 —— 放進來的東西要能承受萬一被看到。",
    "單次執行的觀察一律標為<strong>定性觀察</strong>，不是統計證據。",
    "五個交易日只有五個點。",
    "每一列各自標自己的資料日期。",
    "<strong>本頁不構成投資建議。</strong>",
)


def _stock_row(
    symbol: str,
    scored: list,
    summary: dict,
) -> Row:
    latest_date, latest = scored[-1]
    terms = []
    for name, t in (("短期", latest.short), ("中期", latest.mid), ("長期", latest.long)):
        terms.append(
            f"{name} {t.score:.0f}" if t.score is not None
            else f"{name} {scoring_stock.INSUFFICIENT}"
        )
    if latest.chips is not None:
        terms.append(
            f"籌碼 {latest.chips.score:.0f}" if latest.chips.score is not None
            else f"籌碼 {scoring_stock.INSUFFICIENT}"
        )

    notes = ["／".join(terms)]
    notes.extend(latest.caveats)
    if latest.mid.score is None:
        notes.append(latest.mid.reason)
    if latest.long.score is None:
        notes.append(latest.long.reason)

    wavg = summary["weighted_average"]
    return Row(
        label=f"{symbol} {rc.NAMES.get(symbol, '')}".strip(),
        value=(f"{latest.overall:.1f}" if latest.overall is not None else None),
        data_date=latest_date.isoformat(),
        freq="每日",
        series=[(d.isoformat(), s.overall) for d, s in scored],
        change=(f"五日加權 {wavg:.1f}" if wavg is not None else None),
        note="｜".join(n for n in notes if n),
    )


def build_tabs(rows_by_symbol: dict[str, tuple[list, dict]]) -> list[Tab]:
    """`rows_by_symbol[symbol] = (scored, summary)`，由 pipeline 那側算好餵進來。"""
    def rows_for(symbols):
        out = []
        for s in symbols:
            got = rows_by_symbol.get(s)
            if got is None:
                out.append(Row(label=f"{s} {rc.NAMES.get(s, '')}".strip(),
                               value=None, data_date=None, note="本機沒有序列"))
                continue
            out.append(_stock_row(s, *got))
        return out

    return [
        Tab(key="tw", title="台股權值股", rows=rows_for(rc.TW_STOCKS), intro=TW_INTRO),
        Tab(key="us", title="美股權值股與 ADR",
            rows=rows_for(rc.US_STOCKS + rc.ADRS), intro=US_INTRO),
    ]
