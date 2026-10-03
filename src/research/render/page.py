"""stock-research 的分頁組裝（ToDo §2、§7.2；2026-10-03 改版）。

**頁面骨架沿用 market-barometer 的 render/page.py** —— 標頭、「最後一次抓取」、
兩層導覽、頁尾免責都由那一支產生，兩個站用同一副骨架。分頁裡面放什麼由這一側
決定：個股評分表、本地維度矩陣、基本面矩陣都在 `render/sections.py` 畫好，
交給 `Tab.body`。

與 market-barometer 在內容上的差別仍是 `enforce_lint=False`：
這個 repo **可以**有買賣與短中長線建議（§2.1）。那條線畫在內容本身，
所以由呼叫端決定要不要開 lint，而不是由渲染器自己猜。

⚠️ 這裡的內容只有自己看。「私有 ≠ 可以對外分享」—— 一次「傳給朋友看」，
§2 的全部前提就失效（§12 第 8 條）。
"""
from __future__ import annotations

from barometer.render import page as base_page
from barometer.render.page import Tab

from research import config as rc
from research.domain.fundamentals import FundamentalReport, GROUPS
from research.render import sections

TW_INTRO = (
    "台股追蹤標的。顯示單位「張」，資料層一律存「股」，換算只在顯示層做。"
)
_TW_EXPLAIN = ("可比分數只看台美共用的還原 OHLCV，可跨市場比較；本地分數另加入台股專屬維度。"
               "兩者回答不同問題。")
_US_EXPLAIN = ("可比分數只看台美共用的還原 OHLCV，可跨市場比較；本地分數只使用有效且有資料日期的"
               "美股維度。兩者回答不同問題。")


def _us_intro() -> str:
    pairs = "、".join(f"{tw}/{adr}" for tw, adr in rc.ADR_PAIRS)
    notes = "；".join(rc.PAIR_NOTES)
    intro = "美股追蹤標的與台灣 ADR。顯示單位「股」。"
    if pairs:
        intro += f"同一家公司的台股與 ADR 可以互看：{pairs}。"
    if notes:
        intro += f"對照組資料：{notes}。"
    return intro

FOOTER = (
    "這是<strong>加了鎖的公開頁面</strong>，不是私密頁面，放進來的東西要能承受萬一被看到。",
    "單次執行的觀察一律標為<strong>定性觀察</strong>，不是統計證據。",
    "五個交易日只有五個點。",
    "每一列各自標自己的資料日期。",
    "<strong>本頁不構成投資建議。</strong>",
)


def build_tabs(
    rows_by_symbol: dict[str, tuple[list, dict]],
    provenance_by_symbol: dict[str, tuple[str, str]] | None = None,
    missing_reasons: dict[str, str] | None = None,
    local_by_symbol: dict[str, dict] | None = None,
    local_coverage: dict[str, tuple[int, int]] | None = None,
    local_meta_by_symbol: dict[str, tuple[str, int]] | None = None,
    fundamentals_by_symbol: dict[str, FundamentalReport] | None = None,
) -> list[Tab]:
    """`rows_by_symbol[symbol] = (scored, summary)`，由 pipeline 那側算好餵進來。"""
    def bodies(key: str, symbols) -> list[str]:
        out = []
        for index, symbol in enumerate(symbols):
            got = rows_by_symbol.get(symbol)
            if got is None:
                reason = (missing_reasons or {}).get(symbol, "本機沒有序列")
                out.append(sections.missing_body(index, symbol, reason))
                continue
            source, fetched_at = (provenance_by_symbol or {}).get(symbol, ("", None))
            local_date, local_age = (local_meta_by_symbol or {}).get(symbol, (None, None))
            out.append(sections.stock_body(
                key, index, symbol, *got, source=source, fetched_at=fetched_at,
                local_data_date=local_date, local_age_days=local_age,
                fundamental=(fundamentals_by_symbol or {}).get(symbol)))
        return out

    tabs = [
        Tab(key="tw", title="台股權值股", group="評分", intro=TW_INTRO,
            body=sections.score_table(bodies("tw", rc.TW_STOCKS), chips=True,
                                      explain=_TW_EXPLAIN)),
        Tab(key="us", title="美股權值股與 ADR", group="評分", intro=_us_intro(),
            body=sections.score_table(bodies("us", rc.US_STOCKS + rc.ADRS), chips=False,
                                      explain=_US_EXPLAIN)),
    ]
    if local_by_symbol is not None:
        tabs.extend(_local_tabs(local_by_symbol, local_coverage or {}))
    if fundamentals_by_symbol is not None:
        tabs.extend(_fundamental_tabs(fundamentals_by_symbol))
    return tabs


def render_page(tabs: list[Tab], *, title: str, tagline: str, last_run_at: str | None) -> str:
    """發布與測試共用的同一次 render：不開 lint，掛這一側的頁尾、樣式與互動。"""
    return base_page.render(tabs, title=title, tagline=tagline, footer_notes=FOOTER,
                            enforce_lint=False, last_run_at=last_run_at,
                            extra_style=sections.STYLE, extra_script=sections.SCRIPT)


_FUNDAMENTAL_KEYS = dict(zip(GROUPS, ("valuation", "profitability", "growth", "structure")))
_FUNDAMENTAL_NOTE = "資料來自公開財報摘要，口徑可能與正式財報不同。季末／所屬月份不是首次公開日；各列另標取得日。"


def _fundamental_tabs(reports: dict[str, FundamentalReport]) -> list[Tab]:
    tabs = []
    for group, fields in GROUPS.items():
        intro = _FUNDAMENTAL_NOTE
        if group == "估值":
            intro += "台股本益比、殖利率與淨值比採 TWSE；ADR 採 Yahoo，兩者 EPS 期間口徑可能不同。"
        tabs.append(Tab(key=f"fundamental_{_FUNDAMENTAL_KEYS[group]}", title=group,
                        group="基本面", intro=intro,
                        body=sections.fundamental_matrix(group, fields, reports)))
    tabs.append(Tab(key="fundamental_theses", title="規則式論點", group="基本面",
                    intro=_FUNDAMENTAL_NOTE + "論點只描述可核對的變化。",
                    body=sections.theses_table(reports)))
    return tabs


def _local_tabs(local_by_symbol: dict[str, dict], coverage: dict[str, tuple[int, int]]) -> list[Tab]:
    return [
        Tab(key="tw_local", title="本地維度", group="台股本地",
            intro="台股官方與集保資料。每一欄標來源與涵蓋率，每一格標資料日與取得時間；"
                  "是否進數值分數依當日資料完整度與延遲判斷。",
            body=sections.local_matrix(local_by_symbol, coverage)),
        Tab(key="tw_revenue", title="月營收（獨立）", group="台股本地",
            intro="月營收公布時市場可能已反應，不進任何分數。資料日期為出表日，所屬月份另列。",
            body=sections.revenue_table(local_by_symbol, coverage)),
    ]
