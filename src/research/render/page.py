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
from barometer.domain.coverage import Coverage

from research import config as rc
from research.domain import scoring_stock
from research.domain.fundamentals import (FundamentalReport, GROUPS, LABELS,
                                          PERCENT_FIELDS, rule_theses)

TW_INTRO = (
    "台股追蹤標的。顯示單位「張」，資料層一律存「股」，換算只在顯示層做。"
)


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
    "這是**加了鎖的公開頁面**，不是私密頁面，放進來的東西要能承受萬一被看到。",
    "單次執行的觀察一律標為<strong>定性觀察</strong>，不是統計證據。",
    "五個交易日只有五個點。",
    "每一列各自標自己的資料日期。",
    "<strong>本頁不構成投資建議。</strong>",
)


def _stock_row(
    symbol: str,
    scored: list,
    summary: dict,
    source: str = "",
    fetched_at: str | None = None,
    local_data_date: str | None = None,
    local_age_days: int | None = None,
    fundamental: FundamentalReport | None = None,
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

    notes = ["可比分數只看台美共用的還原 OHLCV；本地分數另加入市場專屬維度，兩者回答不同問題。",
             "／".join(terms)]
    if latest.strength is not None:
        notes.append(f"強度 C {latest.strength:.1f}（不進方向分與星等）")
    else:
        notes.append("強度 C 資料不足")
    for term in (latest.short, latest.mid, latest.long):
        for item in term.items:
            amount = f"{item.score:+.0f}" if item.score is not None else "資料不足"
            notes.append(f"{item.name} {amount}（權重 {item.weight:.0%}）：{item.detail}")
    notes.extend(latest.local_reasons)
    if latest.local_note:
        notes.append(latest.local_note)
    if local_data_date is not None and local_age_days is not None:
        notes.append(f"本地維度資料日：{local_data_date}（延遲 {local_age_days} 天）")
    if latest.overrides:
        notes.append("Override：" + "；".join(latest.overrides))
    notes.extend(latest.caveats)
    if latest.mid.score is None:
        notes.append(latest.mid.reason)
    if latest.long.score is None:
        notes.append(latest.long.reason)

    wavg = summary["weighted_average"]
    if wavg is not None:
        notes.append(f"五日加權 {wavg:.1f}（定性觀察）")
    if latest.comparable is not None:
        value = f"可比 {latest.comparable:+.1f} {scoring_stock.to_stars(latest.comparable)['text']}｜本地 {latest.native:+.1f} {scoring_stock.to_stars(latest.native)['text']}"
    else:
        value = None
    return Row(
        label=f"{symbol} {rc.NAMES.get(symbol, '')}".strip(),
        value=value,
        data_date=latest_date.isoformat(),
        freq="每日",
        series=[(d.isoformat(), s.overall) for d, s in scored],
        change=(f"原始差距 {latest.raw_gap:+.1f}" if latest.raw_gap is not None else None),
        note="｜".join(n for n in notes if n),
        source=source,
        fetched_at=fetched_at,
        coverage=Coverage(
            sum(term.score is not None for term in
                (latest.short, latest.mid, latest.long)), 3),
        coverage_name="技術面",
        fundamental_coverage=fundamental.coverage if fundamental is not None else Coverage(0, 0),
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
    def rows_for(symbols):
        out = []
        for s in symbols:
            got = rows_by_symbol.get(s)
            if got is None:
                out.append(Row(label=f"{s} {rc.NAMES.get(s, '')}".strip(),
                               value=None, data_date=None,
                               note=(missing_reasons or {}).get(s, "本機沒有序列"),
                               fundamental_coverage=(fundamentals_by_symbol or {}).get(s, FundamentalReport(s, {})).coverage
                               if fundamentals_by_symbol is not None else None))
                continue
            provenance = (provenance_by_symbol or {}).get(s, ("", None))
            local_meta = (local_meta_by_symbol or {}).get(s, (None, None))
            out.append(_stock_row(s, *got, *provenance, *local_meta,
                                  fundamental=(fundamentals_by_symbol or {}).get(s)))
        return out

    tabs = [
        Tab(key="tw", title="台股權值股", rows=rows_for(rc.TW_STOCKS), intro=TW_INTRO + "可比分數可跨市場比較；本地分數包含台股專屬維度。"),
        Tab(key="us", title="美股權值股與 ADR",
            rows=rows_for(rc.US_STOCKS + rc.ADRS), intro=_us_intro() + "可比分數可跨市場比較；本地分數只使用有效且有資料日期的美股維度。"),
    ]
    if local_by_symbol is not None:
        tabs.extend(_local_tabs(local_by_symbol, local_coverage or {}))
    if fundamentals_by_symbol is not None:
        tabs.extend(_fundamental_tabs(fundamentals_by_symbol))
    return tabs


_FUNDAMENTAL_KEYS = dict(zip(GROUPS, ("valuation", "profitability", "growth", "structure")))
_FUNDAMENTAL_NOTE = "資料來自公開財報摘要，口徑可能與正式財報不同。季末／所屬月份不是首次公開日；各列另標取得日。"


def _fundamental_tabs(reports: dict[str, FundamentalReport]) -> list[Tab]:
    tabs = []
    for group, fields in GROUPS.items():
        rows = []
        for symbol in rc.ALL_SYMBOLS:
            report = reports.get(symbol, FundamentalReport(symbol, {}))
            valid = [report.metric(key) for key in fields if report.metric(key).status == "OK"]
            values = [f"{LABELS[key]} {report.metric(key).value:.2f}{'%' if key in PERCENT_FIELDS else ''}"
                      for key in fields if report.metric(key).status == "OK"]
            missing = [LABELS[key] for key in fields if report.metric(key).status != "OK"]
            detail = [f"{LABELS[key]}：{report.metric(key).source or '來源未知'}；"
                      f"資料取得日 {report.metric(key).data_date or '未知'}；"
                      f"所屬期間 {report.metric(key).period or '未提供'}"
                      for key in fields if report.metric(key).status == "OK"]
            if missing:
                detail.append("資料不足：" + "、".join(missing))
            if not report.quarters:
                detail.append("自身歷史季報比較：資料不足")
            rows.append(Row(
                label=f"{symbol} {rc.NAMES.get(symbol, '')}".strip(),
                value="｜".join(values) if values else None,
                data_date=max((item.data_date for item in valid if item.data_date), default=None).isoformat()
                if any(item.data_date for item in valid) else None,
                freq="每日／季報" if group == "估值" else "季報／月報" if group == "成長" else "季報",
                note="；".join(detail),
                source="、".join(dict.fromkeys(item.source for item in valid if item.source)),
                fetched_at=max((item.retrieved_at for item in valid if item.retrieved_at), default=None).isoformat()
                if any(item.retrieved_at for item in valid) else None,
                coverage=Coverage(len(valid), len(fields)), coverage_name=group,
                fundamental_coverage=report.coverage,
            ))
        intro = _FUNDAMENTAL_NOTE
        if group == "估值":
            intro += "台股本益比、殖利率與淨值比採 TWSE；ADR 採 Yahoo，兩者 EPS 期間口徑可能不同。"
        tabs.append(Tab(key=f"fundamental_{_FUNDAMENTAL_KEYS[group]}",
                        title=f"基本面：{group}", rows=rows, intro=intro))
    thesis_rows = []
    for symbol in rc.ALL_SYMBOLS:
        report = reports.get(symbol, FundamentalReport(symbol, {}))
        theses = rule_theses(report)
        bulls = sum(thesis.side == "多方" for thesis in theses)
        bears = sum(thesis.side == "空方" for thesis in theses)
        thesis_rows.append(Row(
            label=f"{symbol} {rc.NAMES.get(symbol, '')}".strip(),
            value=f"多方 {bulls} 項｜空方 {bears} 項" if theses else None,
            data_date=max((metric.data_date for metric in report.metrics.values()
                           if metric.data_date), default=None).isoformat()
            if any(metric.data_date for metric in report.metrics.values()) else None,
            freq="季報／月報", note="；".join(f"{thesis.side}：{thesis.text}" for thesis in theses)
            if theses else "資料不足：尚無可比較的成長或連續季報資料",
            fundamental_coverage=report.coverage,
        ))
    tabs.append(Tab(key="fundamental_theses", title="基本面：規則式論點",
                    rows=thesis_rows, intro=_FUNDAMENTAL_NOTE + "論點只描述可核對的變化。"))
    return tabs


_LOCAL_NAMES = {
    "valuation": "官方估值",
    "breadth": "真實漲跌家數",
    "distribution": "集保戶股權分散",
    "foreign": "外資及陸資持股",
    "day_trade": "當沖比",
    "lending": "借券賣出餘額",
    "margin_estimate": "融資維持率與平均成本（推算值）",
}


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return "資料不足"
    if isinstance(value, (float, int)):
        return f"{value:,.2f}{suffix}" if isinstance(value, float) else f"{value:,}{suffix}"
    return str(value)


def _local_value(dataset: str, value: dict) -> str:
    if dataset == "valuation":
        return f"本益比 {_fmt(value.get('pe_ratio'))}｜殖利率 {_fmt(value.get('dividend_yield_pct'), '%')}｜股價淨值比 {_fmt(value.get('pb_ratio'))}"
    if dataset == "breadth":
        return f"上漲 {_fmt(value.get('advancers_count'))} 家｜下跌 {_fmt(value.get('decliners_count'))} 家｜持平 {_fmt(value.get('unchanged_count'))} 家"
    if dataset == "distribution":
        grades = value.get("grades", {})
        selected = [f"第{grade}級 {_fmt(grades[grade].get('custody_pct'), '%')}"
                    for grade in ("1", "15") if grade in grades]
        return f"持股分級 {len(grades)} 級" + ("｜" + "｜".join(selected) if selected else "")
    if dataset == "foreign":
        return f"持股比率 {_fmt(value.get('foreign_holding_pct'), '%')}｜持有 {_fmt(value.get('foreign_held_shares'), ' 股')}"
    if dataset == "day_trade":
        return f"當沖比 {_fmt(value.get('day_trade_ratio_pct'), '%')}｜成交 {_fmt(value.get('day_trade_shares'), ' 股')}"
    if dataset == "lending":
        return f"借券賣出餘額 {_fmt(value.get('borrowed_short_balance_shares'), ' 股')}｜融券餘額 {_fmt(value.get('short_balance_shares'), ' 股')}"
    if dataset == "margin_estimate":
        return (f"維持率 {_fmt(value.get('maintenance_pct'), '%')}｜"
                f"平均成本 {_fmt(value.get('average_cost_twd'), ' 元')}｜"
                f"融資餘額 {_fmt(value.get('margin_balance_shares'), ' 股')}")
    raise ValueError(dataset)


def _local_tabs(local_by_symbol: dict[str, dict], coverage: dict[str, tuple[int, int]]) -> list[Tab]:
    rows: list[Row] = []
    revenue_rows: list[Row] = []
    for symbol in rc.TW_STOCKS:
        view = local_by_symbol.get(symbol, {})
        for dataset, title in _LOCAL_NAMES.items():
            value = (view.get("local") or {}).get(dataset)
            provenance = view.get("provenance", {}).get(dataset, {})
            counts = coverage.get(dataset)
            rows.append(Row(
                label=f"{symbol} {title}", value=_local_value(dataset, value) if value is not None else None,
                data_date=provenance.get("data_date"),
                freq="每週" if dataset == "distribution" else "每日",
                source=provenance.get("source", ""), fetched_at=provenance.get("retrieved_at"),
                coverage=Coverage(*counts) if counts else None,
                coverage_name=title,
                note=("資料不足" if value is None else
                      ("推算值：假設融資成數 60%；新增部位以當日收盤價、減少部位以先前推算平均成本認定。"
                       "非實際帳戶維持率。" + ("此日為收盤價初始假設。" if value.get("seeded_from_close") else "")
                       if dataset == "margin_estimate" else "本地維度資料；是否進數值分數依當日資料完整度與延遲判斷")),
            ))
        revenue = (view.get("fundamentals") or {}).get("revenue")
        provenance = view.get("fundamental_provenance", {}).get("revenue", {})
        counts = coverage.get("revenue")
        revenue_rows.append(Row(
            label=f"{symbol} 月營收", value=(f"{_fmt(revenue.get('revenue_ktwd'))} 仟元" if revenue else None),
            data_date=provenance.get("data_date"), freq="每月", source=provenance.get("source", ""),
            fetched_at=provenance.get("retrieved_at"),
            coverage=Coverage(*counts) if counts else None,
            coverage_name="月營收", note=(f"所屬月份 {revenue['reporting_period']}｜獨立基本面資料，不進任何分數"
                                          if revenue else "獨立基本面資料，不進任何分數"),
        ))
    # ADR counterpart has no TWSE/TDCC observations. Say so explicitly.
    rows.extend(Row(label=f"{symbol} 台股本地資料", value=None, data_date=None,
                    note="無對應資料") for symbol in rc.ADRS)
    return [
        Tab(key="tw_local", title="台股本地維度", rows=rows,
            intro="台股官方與集保資料。各列分別標來源、資料日期、取得時間與涵蓋率；方向分依有效觀測計算。"),
        Tab(key="tw_revenue", title="台股月營收（獨立）", rows=revenue_rows,
            intro="月營收公布時市場可能已反應，不進任何分數。資料日期為出表日，所屬月份另列。"),
    ]
