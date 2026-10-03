"""stock-research 分頁裡的內容（2026-10-03 改版）。

頁面骨架 —— 標頭、「最後一次抓取」、兩層導覽、頁尾免責 —— 仍由 market-barometer
的 render() 產生；這裡只畫每個分頁裡面的東西，交給 `Tab.body`。

改版前的問題寫成了測試（tests/render/test_redesign_page.py）：每檔約 1,270 字的
說明全部塞進只分到 101px 的第一欄，台股分頁每一列高 2,678px。所以這裡的規矩是
**摘要列只放摘要**，指標細節一律進預設收合的明細列。

**跳脫由這一側負責。** `Tab.body` 會原樣插進頁面，任何來自資料的字串都要過
escape() —— 台股名稱就是從 TWSE 抓回來的。

這一層是表現層：不得 import storage／datasources（tests/test_layer_boundary.py 守著）。
"""
from __future__ import annotations

import datetime as dt
import re
from html import escape

from barometer.domain.coverage import Coverage
from barometer.render import svg

from research import config as rc
from research.domain import scoring_stock
from research.domain.fundamentals import (FundamentalReport, LABELS, PERCENT_FIELDS,
                                          rule_theses)

INSUFFICIENT = scoring_stock.INSUFFICIENT

_CHEVRON = ('<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">'
            '<path d="M3 4.5 L6 7.5 L9 4.5" fill="none" stroke="currentColor" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>')

_LEGEND = (
    '<div class="legend">'
    '<span class="lg"><span class="bar" aria-hidden="true"><span class="fill up" '
    'style="left:50%;width:30%"></span></span>分數 −100～+100，中線為 0</span>'
    '<span class="lg"><i class="sw up"></i>紅＝正向<i class="sw down"></i>綠＝負向</span>'
    '<span class="lg">★ 正向強度・☆ 負向強度</span>'
    f'<span class="lg"><span class="na-box">{INSUFFICIENT}</span>不計為 0，也不進平均</span>'
    '</div>'
)

_LOCAL_COLUMNS = (
    ("valuation", "官方估值"),
    ("distribution", "集保股權分散"),
    ("foreign", "外資及陸資持股"),
    ("day_trade", "當沖比"),
    ("lending", "借券賣出餘額"),
    ("margin_estimate", "融資維持率與平均成本"),
)


# ---------------- 小零件 ----------------

def _tone(value: float | None) -> str:
    if value is None:
        return "na"
    return "up" if value > 0 else "down" if value < 0 else "flat"


def _signed(value: float | None, digits: int = 1) -> str:
    """+54.4／-13.4；四捨五入成 0 的寫 0，不寫 +0。沒有值就寫「資料不足」，絕不寫 0。"""
    if value is None:
        return INSUFFICIENT
    text = f"{value:+.{digits}f}"
    return text[1:] if float(text) == 0 else text


def _bar(value: float | None, mini: bool = False) -> str:
    """−100～+100 的雙向條，中線是 0。沒有值就只畫軌道，不畫一截 0。"""
    css = "bar mini" if mini else "bar"
    if value is None:
        return f'<span class="{css}" aria-hidden="true"></span>'
    width = min(abs(value), 100) / 2
    left = 50 if value >= 0 else 50 - width
    return (f'<span class="{css}" aria-hidden="true"><span class="fill {_tone(value)}" '
            f'style="left:{left:.1f}%;width:{width:.1f}%"></span></span>')


def _score(value: float | None) -> str:
    stars = scoring_stock.to_stars(value)["text"] if value is not None else ""
    return (f'<div class="score {_tone(value)}"><span class="num">{_signed(value)}</span>'
            f'<span class="stars">{stars}</span></div>{_bar(value)}')


def _cell(label: str, value: float | None) -> str:
    """三期與籌碼各一格；底色深淺跟著分數的絕對值，每 20 分一階。"""
    if value is None:
        return (f'<span class="cell na"><span class="k">{label}</span>'
                f'<span class="v">{INSUFFICIENT}</span></span>')
    level = min(5, int(abs(value) // 20) + 1)
    return (f'<span class="cell {_tone(value)} l{level}"><span class="k">{label}</span>'
            f'<span class="v">{_signed(value, 0)}</span></span>')


def _tag(text: str, warn: bool = False) -> str:
    return f'<span class="tag{" warn" if warn else ""}">{escape(text)}</span>'


def _name(symbol: str) -> str:
    return (f'<span class="sym">{escape(symbol)}</span>'
            f'<span class="nm">{escape(rc.NAMES.get(symbol, ""))}</span>')


def _pair_of(symbol: str) -> str | None:
    for tw, adr in rc.ADR_PAIRS:
        if symbol == tw:
            return adr
        if symbol == adr:
            return tw
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")


def _stamp(value: object) -> str:
    """取得時間統一寫成「YYYY-MM-DD HH:MM」；ISO 字串與 datetime 都收。"""
    if value is None or value == "":
        return "未記錄"
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value).replace("T", " ")[:16]


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return INSUFFICIENT
    if isinstance(value, (float, int)):
        return f"{value:,.2f}{suffix}" if isinstance(value, float) else f"{value:,}{suffix}"
    return str(value)


def _market_sections() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (("台股權值股", rc.TW_STOCKS), ("美股權值股", rc.US_STOCKS), ("台灣 ADR", rc.ADRS))


# ---------------- 評分分頁：一檔一列＋明細 ----------------

def stock_body(tab: str, index: int, symbol: str, scored: list, summary: dict, *,
               source: str = "", fetched_at: str | None = None,
               local_data_date: str | None = None, local_age_days: int | None = None,
               fundamental: FundamentalReport | None = None) -> str:
    """一檔一個 <tbody>：摘要列＋預設收合的明細列。排序時整個 <tbody> 一起搬。"""
    day, latest = scored[-1]
    terms = (("短期", latest.short), ("中期", latest.mid), ("長期", latest.long))
    technical = Coverage(sum(term.score is not None for _, term in terms), 3)

    tags = []
    if pair := _pair_of(symbol):
        tags.append(_tag(f"對照 {pair}"))
    if any(caveat.startswith("薄流動性") for caveat in latest.caveats):
        tags.append(_tag("薄流動性", warn=True))
    if technical.degraded:
        tags.append(_tag("低涵蓋・降級", warn=True))
    if latest.overrides:
        tags.append(_tag("風險調整", warn=True))
    tag_html = f'<span class="tags">{"".join(tags)}</span>' if tags else ""

    cells = [_cell(name, term.score) for name, term in terms]
    if latest.chips is not None:      # 美股與 ADR 沒有三大法人：那一格不存在，不是 0
        cells.append(_cell("籌碼", latest.chips.score))

    native_notes = [f"原始差距 {_signed(latest.raw_gap)}"]
    if local_data_date is not None and local_age_days is not None:
        native_notes.append(f"本地資料延遲 {local_age_days} 天")
    elif latest.local_note:
        native_notes.append(latest.local_note)
    native_html = "".join(f'<span class="sub">{escape(note)}</span>' for note in native_notes)

    spark = svg.sparkline([(d.isoformat(), s.overall) for d, s in scored], freq="每日",
                          width=96, height=30, label=f"{symbol} 近五個交易日可比分數")
    detail_id = f"d-{_slug(tab)}-{_slug(symbol)}"
    keys = "".join(f' data-k-{key}="{value:.4f}"'
                   for key, value in (("comp", latest.comparable), ("native", latest.native))
                   if value is not None)
    summary_row = (
        f'<tr class="sum"><th scope="row">{_name(symbol)}{tag_html}</th>'
        f'<td class="c-comp"><span class="lbl">可比分數</span>{_score(latest.comparable)}</td>'
        f'<td class="c-native"><span class="lbl">本地分數</span>{_score(latest.native)}'
        f'{native_html}</td>'
        f'<td class="c-terms"><span class="cells">{"".join(cells)}</span></td>'
        f'<td class="c-spark"><span class="trend {_tone(latest.comparable)}">{spark}</span></td>'
        f'<td class="c-date">{day.isoformat()}<span class="sub">每日</span></td>'
        f'<td class="c-act"><button type="button" class="more" aria-expanded="false" '
        f'aria-controls="{detail_id}" aria-label="{escape(symbol)} 明細">'
        f'<span class="label">明細</span>{_CHEVRON}</button></td></tr>'
    )
    panel = _panel(symbol, day, latest, summary, source, fetched_at, technical,
                   local_data_date, local_age_days, fundamental)
    detail_row = f'<tr class="detail" id="{detail_id}" hidden><td colspan="7">{panel}</td></tr>'
    return f'<tbody data-unit="{index}"{keys}>{summary_row}{detail_row}</tbody>'


def missing_body(index: int, symbol: str, reason: str) -> str:
    """算不出來的標的照樣佔一列，寫出原因 —— 不消失，也不變成 0 分。"""
    return (f'<tbody data-unit="{index}"><tr class="sum missing">'
            f'<th scope="row">{_name(symbol)}</th>'
            f'<td colspan="6"><span class="na-box">{escape(reason)}</span>'
            f'<span class="sub">名稱來源：{escape(rc.NAME_SOURCES.get(symbol, "設定檔"))}</span>'
            f'</td></tr></tbody>')


def _panel(symbol, day, latest, summary, source, fetched_at, technical,
           local_data_date, local_age_days, fundamental) -> str:
    wavg = summary.get("weighted_average")
    chips = (
        ("強度 C", f"{latest.strength:.1f}" if latest.strength is not None else INSUFFICIENT,
         "不進方向分與星等"),
        ("原始差距", _signed(latest.raw_gap), "本地原始分 − 可比原始分"),
        ("五日加權", f"{wavg:.1f}" if wavg is not None else INSUFFICIENT, "定性觀察"),
    )
    chip_html = "".join(f'<span class="chip"><span class="k">{k}</span><b>{v}</b>'
                        f'<span class="n">{n}</span></span>' for k, v, n in chips)
    term_html = "".join(_term(name, term) for name, term in
                        (("短期", latest.short), ("中期", latest.mid), ("長期", latest.long)))
    fundamental_coverage = fundamental.coverage if fundamental is not None else Coverage(0, 0)
    provenance = (
        ("名稱來源", rc.NAME_SOURCES.get(symbol, "設定檔")),
        ("來源", source or "未記錄"),
        ("資料日期", f"{day.isoformat()}（每日）"),
        ("取得時間", fetched_at or "未記錄"),
        ("涵蓋", f"{technical.label('技術面')}；{fundamental_coverage.label('基本面')}"),
    )
    provenance_html = "".join(f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>"
                              for k, v in provenance)
    warns = [f"Override：{override}" for override in latest.overrides] + list(latest.caveats)
    warn_html = ('<ul class="warns">' + "".join(f"<li>{escape(w)}</li>" for w in warns)
                 + "</ul>") if warns else ""
    return (f'<div class="panel"><div class="chips">{chip_html}</div>'
            f'<div class="terms">{term_html}</div>'
            f'<div class="lower">{_local_box(symbol, latest, local_data_date, local_age_days)}'
            f'<div class="box prov"><div class="box-head"><span class="t">來源與但書</span></div>'
            f'<dl>{provenance_html}</dl>{warn_html}</div></div></div>')


def _term(name: str, term) -> str:
    """一期一欄。整期算不出來時寫原因；底下的指標照列但淡掉 —— 它們沒有進分數。"""
    valid = sum(item.score is not None for item in term.items)
    reason = f'<p class="reason">{escape(term.reason)}</p>' if term.score is None else ""
    dim = ' class="dim"' if term.score is None else ""
    items = "".join(
        f'<li{dim}><span class="n">{escape(item.name)}</span>'
        f'<span class="w">權重 {item.weight:.0%}</span>{_bar(item.score, mini=True)}'
        f'<span class="v {_tone(item.score)}">{_signed(item.score, 0)}</span>'
        f'<span class="d">{escape(item.detail)}</span></li>'
        for item in term.items)
    return (f'<div class="term"><div class="term-head"><span class="t">{name}</span>'
            f'<span class="c">{valid}/{len(term.items)} 項</span>'
            f'<span class="v {_tone(term.score)}">{_signed(term.score, 0)}</span></div>'
            f'{reason}<ul class="items">{items}</ul></div>')


def _local_box(symbol, latest, local_data_date, local_age_days) -> str:
    tw = symbol.endswith((".TW", ".TWO"))
    title = "本地維度（台股官方、集保與三大法人）" if tw else "本地維度（美股）"
    rows = []
    for item in latest.local_items:
        status = "ok" if item.status == "有效" else "stale" if item.status == "過期" else "na"
        age = "延遲未知" if item.age_days is None else f"延遲 {item.age_days} 天"
        rows.append(
            f'<li><span class="n">{escape(item.name)}</span>'
            f'<span class="d">{escape(item.detail)}'
            f'<span class="src">{escape(item.source or "來源未記錄")}</span></span>'
            f'<span class="s"><span class="st {status}">{escape(item.status)}</span></span>'
            f'<span class="dt">{escape(item.data_date or "資料日未知")}'
            f'<span class="sub">{age}</span></span></li>')
    if not rows:
        # 只拿到 reasons 字串、沒有結構化觀測時照列，不吞掉
        rows = [f'<li class="plain">{escape(reason)}</li>' for reason in latest.local_reasons]
    notes = []
    if local_data_date is not None and local_age_days is not None:
        notes.append(f"本地維度資料日：{local_data_date}（延遲 {local_age_days} 天）")
    if latest.local_note:
        notes.append(latest.local_note)
    note_html = "".join(f'<p class="meta">{escape(note)}</p>' for note in notes)
    empty = '<p class="reason">沒有本地維度觀測</p>' if not rows else ""
    return (f'<div class="box local"><div class="box-head"><span class="t">{title}</span>'
            f'<span class="c">本地分數 <b class="{_tone(latest.native)}">'
            f'{_signed(latest.native)}</b></span></div>'
            f'{note_html}{empty}<ul class="local-list">{"".join(rows)}</ul></div>')


def score_table(bodies: list[str], *, chips: bool, explain: str) -> str:
    terms = "短期・中期・長期・籌碼" if chips else "短期・中期・長期（美股沒有籌碼面）"
    head = (
        '<thead><tr><th scope="col">標的</th>'
        '<th scope="col" aria-sort="none"><button type="button" class="sort" data-sort="comp">'
        '可比分數<span class="arrow" aria-hidden="true"></span></button></th>'
        '<th scope="col" aria-sort="none"><button type="button" class="sort" data-sort="native">'
        '本地分數<span class="arrow" aria-hidden="true"></span></button></th>'
        f'<th scope="col">{terms}</th><th scope="col">五日走勢</th>'
        '<th scope="col">資料日期</th><th scope="col"><span class="sr-only">明細</span></th>'
        '</tr></thead>'
    )
    return (f'{_LEGEND}<p class="explain">{escape(explain)}</p>'
            f'<div class="board"><table class="stocks" data-units>{head}{"".join(bodies)}'
            f'</table></div>')


# ---------------- 台股本地：個股 × 維度 ----------------

def _local_lines(dataset: str, value: dict) -> list[tuple[str, str]]:
    if dataset == "valuation":
        return [("本益比", _fmt(value.get("pe_ratio"))),
                ("殖利率", _fmt(value.get("dividend_yield_pct"), "%")),
                ("股價淨值比", _fmt(value.get("pb_ratio")))]
    if dataset == "distribution":
        grades = value.get("grades", {})
        return [("持股分級", f"{len(grades)} 級")] + [
            (f"第{grade}級", _fmt(grades[grade].get("custody_pct"), "%"))
            for grade in ("1", "15") if grade in grades]
    if dataset == "foreign":
        return [("持股比率", _fmt(value.get("foreign_holding_pct"), "%")),
                ("持有", _fmt(value.get("foreign_held_shares"), " 股"))]
    if dataset == "day_trade":
        return [("當沖比", _fmt(value.get("day_trade_ratio_pct"), "%")),
                ("成交", _fmt(value.get("day_trade_shares"), " 股"))]
    if dataset == "lending":
        return [("借券賣出", _fmt(value.get("borrowed_short_balance_shares"), " 股")),
                ("融券", _fmt(value.get("short_balance_shares"), " 股"))]
    if dataset == "margin_estimate":
        return [("維持率", _fmt(value.get("maintenance_pct"), "%")),
                ("平均成本", _fmt(value.get("average_cost_twd"), " 元")),
                ("融資餘額", _fmt(value.get("margin_balance_shares"), " 股"))]
    raise ValueError(dataset)


def _breadth_strip(local_by_symbol: dict, coverage: dict) -> str:
    """漲跌家數是全市場一筆（資料層只存一份），五檔共用 —— 只列一次。"""
    value, provenance = None, {}
    for symbol in rc.TW_STOCKS:
        view = local_by_symbol.get(symbol) or {}
        if (view.get("local") or {}).get("breadth"):
            value = view["local"]["breadth"]
            provenance = (view.get("provenance") or {}).get("breadth", {})
            break
    if value is None:
        figures = f'<span class="na-box">{INSUFFICIENT}</span>'
    else:
        figures = "".join(
            f'<span>{label} <b>{escape(_fmt(value.get(key)))}</b> 家</span>'
            for label, key in (("上漲", "advancers_count"), ("下跌", "decliners_count"),
                               ("持平", "unchanged_count")))
    meta = [f"資料日 {provenance.get('data_date') or '未知'}", "每日",
            provenance.get("source") or "來源未記錄", f"取得 {_stamp(provenance.get('retrieved_at'))}"]
    if counts := coverage.get("breadth"):
        meta.append(Coverage(*counts).label("涵蓋率"))
    return (f'<div class="strip"><div class="strip-t"><b>真實漲跌家數</b>'
            f'<span class="sub">全市場一筆，五檔共用，只列一次</span></div>'
            f'<div class="figs">{figures}</div>'
            f'<div class="meta">{escape("・".join(meta))}</div></div>')


def _first_source(local_by_symbol: dict, dataset: str) -> str:
    for symbol in rc.TW_STOCKS:
        view = local_by_symbol.get(symbol) or {}
        source = ((view.get("provenance") or {}).get(dataset) or {}).get("source")
        if source:
            return source
    return "來源未記錄"


def local_matrix(local_by_symbol: dict, coverage: dict) -> str:
    heads = []
    for dataset, title in _LOCAL_COLUMNS:
        counts = coverage.get(dataset)
        freq = "每週" if dataset == "distribution" else "每日"
        cov = (f'<span class="sub">{escape(Coverage(*counts).label("涵蓋率"))}</span>'
               if counts else "")
        heads.append(f'<th scope="col"><span class="h">{title}</span><span class="sub">'
                     f'{escape(_first_source(local_by_symbol, dataset))}・{freq}</span>{cov}</th>')
    rows = []
    for symbol in rc.TW_STOCKS:
        view = local_by_symbol.get(symbol) or {}
        values = view.get("local") or {}
        provenance = view.get("provenance") or {}
        cells = []
        for dataset, _ in _LOCAL_COLUMNS:
            value = values.get(dataset)
            if value is None:
                cells.append(f'<td><span class="na-box">{INSUFFICIENT}</span></td>')
                continue
            meta = provenance.get(dataset) or {}
            lines = "".join(f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>"
                            for k, v in _local_lines(dataset, value))
            extra = ""
            if dataset == "margin_estimate":
                extra = _tag("推算值", warn=True) + (
                    '<span class="sub">此日為收盤價初始假設</span>'
                    if value.get("seeded_from_close") else "")
            cells.append(f'<td><dl class="kv">{lines}</dl>{extra}<span class="when">'
                         f'資料日 {escape(meta.get("data_date") or "未知")}<br>'
                         f'取得 {escape(_stamp(meta.get("retrieved_at")))}</span></td>')
        rows.append(f'<tr><th scope="row">{_name(symbol)}</th>{"".join(cells)}</tr>')
    adr = (f'<p class="foot-note">{escape("、".join(rc.ADRS))} 是 ADR，沒有對應的台股本地資料'
           f'（無對應資料）。</p>' if rc.ADRS else "")
    return (f'{_breadth_strip(local_by_symbol, coverage)}'
            f'<div class="board"><table class="matrix local"><thead><tr>'
            f'<th scope="col">標的</th>{"".join(heads)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>{adr}'
            '<p class="foot-note">融資維持率與平均成本是推算值：假設融資成數 60%；新增部位以'
            '當日收盤價、減少部位以先前推算平均成本認定。非實際帳戶維持率。</p>')


def revenue_table(local_by_symbol: dict, coverage: dict) -> str:
    rows = []
    for symbol in rc.TW_STOCKS:
        view = local_by_symbol.get(symbol) or {}
        revenue = (view.get("fundamentals") or {}).get("revenue")
        meta = (view.get("fundamental_provenance") or {}).get("revenue") or {}
        if revenue:
            cells = (f'<td class="num">{escape(_fmt(revenue.get("revenue_ktwd")))} 仟元</td>'
                     f'<td>{escape(str(revenue.get("reporting_period") or "未提供"))}</td>'
                     f'<td class="dt">{escape(meta.get("data_date") or "未知")}'
                     f'<span class="sub">取得 {escape(_stamp(meta.get("retrieved_at")))}</span></td>'
                     f'<td class="src">{escape(meta.get("source") or "來源未記錄")}</td>')
        else:
            cells = f'<td colspan="4"><span class="na-box">{INSUFFICIENT}</span></td>'
        rows.append(f'<tr><th scope="row">{_name(symbol)}</th>{cells}</tr>')
    counts = coverage.get("revenue")
    note = (f"{Coverage(*counts).label('涵蓋率')}・" if counts else "") + "獨立基本面資料，不進任何分數。"
    return ('<div class="board"><table class="matrix revenue"><thead><tr>'
            '<th scope="col">標的</th><th scope="col" class="num">月營收</th>'
            '<th scope="col">所屬月份</th><th scope="col">資料日期（出表日）</th>'
            f'<th scope="col">來源</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="foot-note">{escape(note)}</p>')


# ---------------- 基本面：標的 × 指標 ----------------

def fundamental_matrix(group: str, fields: tuple[str, ...],
                       reports: dict[str, FundamentalReport]) -> str:
    heads = "".join(
        f'<th scope="col" class="num" aria-sort="none"><button type="button" class="sort" '
        f'data-sort="{key}">{escape(LABELS[key])}<span class="arrow" aria-hidden="true"></span>'
        f'</button></th>' for key in fields)
    span = len(fields) + 4
    bodies, unit = [], 0
    for title, symbols in _market_sections():
        if not symbols:
            continue
        rows = []
        for symbol in symbols:
            report = reports.get(symbol, FundamentalReport(symbol, {}))
            valid = {key: report.metric(key) for key in fields if report.metric(key).status == "OK"}
            notes = []
            if missing := [LABELS[key] for key in fields if key not in valid]:
                notes.append("資料不足：" + "、".join(missing))
            if not report.quarters:
                notes.append("自身歷史季報比較：資料不足")
            cells = "".join(
                f'<td class="num">{valid[key].value:.2f}{"%" if key in PERCENT_FIELDS else ""}'
                + (f'<span class="sub">{escape(valid[key].period)}</span>' if valid[key].period else "")
                + "</td>" if key in valid else '<td class="num na-v">—</td>'
                for key in fields)
            dates = [metric.data_date for metric in valid.values() if metric.data_date]
            stamps = [metric.retrieved_at for metric in valid.values() if metric.retrieved_at]
            sources = "、".join(dict.fromkeys(m.source for m in valid.values() if m.source)) or "—"
            when = (max(dates).isoformat() if dates else "—") + (
                f'<span class="sub">取得 {escape(_stamp(max(stamps)))}</span>' if stamps else "")
            keys = "".join(f' data-k-{key}="{metric.value:.6g}"' for key, metric in valid.items())
            rows.append(
                f'<tr data-unit="{unit}"{keys}><th scope="row">{_name(symbol)}'
                + "".join(f'<span class="sub">{escape(note)}</span>' for note in notes)
                + f'</th>{cells}<td class="cov">{escape(Coverage(len(valid), len(fields)).label(group))}'
                f'<span class="sub">{escape(report.coverage.label("基本面"))}</span></td>'
                f'<td class="dt">{when}</td><td class="src">{escape(sources)}</td></tr>')
            unit += 1
        bodies.append(f'<tbody><tr class="group"><th scope="colgroup" colspan="{span}">'
                      f'{title}・{len(symbols)} 檔</th></tr>{"".join(rows)}</tbody>')
    return ('<div class="board"><table class="matrix fundamentals" data-units><thead><tr>'
            f'<th scope="col">標的</th>{heads}<th scope="col">涵蓋</th>'
            f'<th scope="col">資料日期</th><th scope="col">來源</th></tr></thead>'
            f'{"".join(bodies)}</table></div>')


def theses_table(reports: dict[str, FundamentalReport]) -> str:
    def listing(texts: list[str]) -> str:
        if not texts:
            return '<span class="na-v">—</span>'
        return '<ul class="plain-list">' + "".join(f"<li>{escape(t)}</li>" for t in texts) + "</ul>"

    bodies = []
    for title, symbols in _market_sections():
        if not symbols:
            continue
        rows = []
        for symbol in symbols:
            report = reports.get(symbol, FundamentalReport(symbol, {}))
            theses = rule_theses(report)
            dates = [metric.data_date for metric in report.metrics.values() if metric.data_date]
            if theses:
                cells = (f'<td>{listing([t.text for t in theses if t.side == "多方"])}</td>'
                         f'<td>{listing([t.text for t in theses if t.side == "空方"])}</td>')
            else:
                cells = ('<td colspan="2"><span class="na-box">'
                         '資料不足：尚無可比較的成長或連續季報資料</span></td>')
            rows.append(f'<tr><th scope="row">{_name(symbol)}</th>{cells}'
                        f'<td class="dt">{max(dates).isoformat() if dates else "—"}</td></tr>')
        bodies.append(f'<tbody><tr class="group"><th scope="colgroup" colspan="4">'
                      f'{title}・{len(symbols)} 檔</th></tr>{"".join(rows)}</tbody>')
    return ('<div class="board"><table class="matrix theses"><thead><tr>'
            '<th scope="col">標的</th><th scope="col">多方論點</th><th scope="col">空方論點</th>'
            f'<th scope="col">資料日期</th></tr></thead>{"".join(bodies)}</table></div>')


# ---------------- 樣式與互動（接在 market-barometer 的共用樣式之後） ----------------

STYLE = """
:root{--up:#f2645f;--down:#3cc489;--text-2:#c9cfdb;--raised:#141821;--sunk:#10141b;
      --hair:#1d222c;--warn2:#d9b44a}
.wrap{max-width:1240px;padding:28px 24px 64px;display:grid;
      grid-template-columns:minmax(0,1fr) auto;column-gap:32px}
.wrap>*{grid-column:1/-1;min-width:0}
.wrap>h1{grid-column:1;font-size:22px;margin:0;letter-spacing:.2px}
.wrap>.tagline{grid-column:1;margin:4px 0 0;font-size:13px}
.wrap>.fetched{grid-column:2;grid-row:1/span 2;align-self:end;text-align:right;margin:0;
               font-size:12.5px}
.fetched .note{display:block;margin:2px 0 0}
nav.grouped{margin:18px 0 0}
nav.grouped .subtabs button{background:transparent;border-color:#2a313e;color:#aab2c2;
                            min-height:36px;padding:6px 14px}
nav.grouped .subtabs button[aria-selected=true]{background:#222a38;border-color:#566074;
                                                color:var(--fg)}
button:focus-visible{outline:2px solid #8fb0ff;outline-offset:2px}
.intro{color:var(--text-2);font-size:13px;margin:20px 0 10px;max-width:920px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
         white-space:nowrap}
.sub{display:block;font-size:11.5px;line-height:1.5;color:var(--muted);font-weight:400}
.lbl{display:none;margin-bottom:2px;font-size:11px;color:var(--muted)}
.up{color:var(--up)}.down{color:var(--down)}.flat,.na{color:var(--muted)}
.legend{display:flex;flex-wrap:wrap;align-items:center;gap:6px 22px;margin:0 0 6px;
        font-size:12px;color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:8px}
.legend .bar{width:64px;margin:0}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px}
.sw.up{background:var(--up)}.sw.down{background:var(--down);margin-left:8px}
.explain{margin:0 0 14px;font-size:12px;color:var(--muted)}
.board{border:1px solid var(--line);border-radius:12px;background:var(--raised);overflow-x:auto}
.board table{min-width:1080px}
.board th,.board td{border-bottom:0}
.stocks thead th{padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
.stocks tbody+tbody{border-top:1px solid var(--hair)}
.stocks .sum>*{padding:12px;vertical-align:top}
.stocks .sum th{font-size:14px;color:var(--fg)}
.stocks tbody:has(.more[aria-expanded=true]) .sum{background:#171c26}
.sym{font-weight:700;font-size:14.5px;letter-spacing:.2px;color:var(--fg)}
.nm{margin-left:8px;color:var(--text-2);font-weight:400}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.tag{display:inline-block;padding:0 7px;border:1px solid #323a49;border-radius:999px;
     font-size:11px;line-height:1.6;font-weight:400;color:#aab2c2;white-space:nowrap}
.tag.warn{border-color:#6b5a2c;color:var(--warn2)}
.score{display:flex;align-items:baseline;gap:8px;white-space:nowrap}
.score .num{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.score.na .num{font-size:13px;font-weight:400}
.score .stars{font-size:12px;letter-spacing:1px}
.bar{position:relative;display:block;width:132px;height:6px;margin-top:6px;border-radius:3px;
     background:#232a37}
.bar::after{content:"";position:absolute;left:50%;top:-3px;width:1px;height:12px;
            background:#5a6376}
.bar .fill{position:absolute;top:0;height:100%;border-radius:3px}
.fill.up{background:var(--up)}.fill.down{background:var(--down)}
.bar.mini{width:64px;height:4px;margin:0}
.bar.mini::after{height:10px;background:#4a5263}
.cells{display:flex;gap:6px}
.cell{display:inline-flex;flex-direction:column;width:64px;padding:4px 8px 5px;border-radius:8px;
      border:1px solid transparent;background:#1a1f29}
.cell .k{font-size:11px;line-height:1.4;color:#9aa3b6}
.cell .v{font-size:14px;line-height:1.5;font-weight:600;color:var(--fg);
         font-variant-numeric:tabular-nums;white-space:nowrap}
.cell.na{background:transparent;border:1px dashed #4a5263}
.cell.na .v{font-size:11.5px;font-weight:400;color:var(--muted)}
.cell.up.l1{background:rgba(242,100,95,.10)}.cell.up.l2{background:rgba(242,100,95,.16)}
.cell.up.l3{background:rgba(242,100,95,.22)}.cell.up.l4{background:rgba(242,100,95,.28)}
.cell.up.l5{background:rgba(242,100,95,.34)}
.cell.down.l1{background:rgba(60,196,137,.10)}.cell.down.l2{background:rgba(60,196,137,.16)}
.cell.down.l3{background:rgba(60,196,137,.22)}.cell.down.l4{background:rgba(60,196,137,.28)}
.cell.down.l5{background:rgba(60,196,137,.34)}
.trend .spark{display:block}
.trend .spark .line{stroke:var(--muted);stroke-width:1.6}
.trend.up .spark .line{stroke:var(--up)}.trend.down .spark .line{stroke:var(--down)}
.c-date{white-space:nowrap;font-size:12.5px;color:var(--text-2);font-variant-numeric:tabular-nums}
.c-act{text-align:right}
.more{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:6px 12px;
      border:1px solid #2f3746;border-radius:8px;background:transparent;color:var(--text-2);
      font:inherit;font-size:12.5px;white-space:nowrap;cursor:pointer}
.more:hover{background:#1d2330}
.more[aria-expanded=true]{background:#232a38}
.more svg{transition:transform .15s}
.more[aria-expanded=true] svg{transform:rotate(180deg)}
.na-box{display:inline-block;padding:1px 8px;border:1px dashed #4a5263;border-radius:6px;
        font-size:12px;line-height:1.6;color:var(--muted)}
.missing .na-box+.sub{margin-top:4px}
.sort{display:inline-flex;align-items:center;gap:4px;min-height:28px;padding:0;border:0;
      background:none;color:inherit;font:inherit;cursor:pointer}
.sort .arrow::after{content:"↕"}
th[aria-sort=descending] .sort,th[aria-sort=ascending] .sort{color:var(--fg)}
th[aria-sort=descending] .arrow::after{content:"↓"}
th[aria-sort=ascending] .arrow::after{content:"↑"}
.detail>td{padding:0}
.panel{display:flex;flex-direction:column;gap:16px;padding:18px 18px 22px;
       border-top:1px solid var(--line);background:var(--sunk)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:baseline;gap:6px;padding:4px 10px;border-radius:8px;
      border:1px solid var(--line);background:#171c26;font-size:12.5px}
.chip .k,.chip .n{color:var(--muted)}.chip .n{font-size:11.5px}
.chip b{font-weight:600;font-variant-numeric:tabular-nums}
.terms{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.lower{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:14px}
.term,.box{min-width:0;padding:12px 14px 6px;border:1px solid var(--line);border-radius:10px;
           background:var(--raised)}
.term-head,.box-head{display:flex;align-items:baseline;gap:8px;padding-bottom:8px;
                     border-bottom:1px solid #222834}
.term-head .t,.box-head .t{font-weight:600}
.term-head .c{margin-left:auto;font-size:11.5px;color:var(--muted)}
.term-head .v{font-weight:700;font-variant-numeric:tabular-nums}
.box-head .c{margin-left:auto;font-size:12px;color:var(--muted)}
.reason{margin:10px 0 8px;padding:10px 12px;border:1px dashed #4a5263;border-radius:8px;
        font-size:12.5px;color:#aab2c2}
.meta{margin:8px 0 0;font-size:12px;color:var(--muted)}
.items,.local-list,.warns,.plain-list{list-style:none;margin:0;padding:0}
.items li{display:grid;grid-template-columns:minmax(0,1fr) auto 64px auto;gap:4px 8px;
          align-items:center;padding:8px 0;border-bottom:1px solid #1b2029}
.items li:last-child,.local-list li:last-child{border-bottom:0}
.items li.dim{opacity:.55}
.items .n{font-size:13px;color:#dfe3eb}
.items .w{font-size:11.5px;color:var(--muted);white-space:nowrap}
.items .v{min-width:36px;text-align:right;font-size:13px;font-weight:600;
          font-variant-numeric:tabular-nums}
.items .d{grid-column:1/-1;font-size:12px;color:var(--muted)}
.local-list li{display:grid;grid-template-columns:118px minmax(0,1fr) auto 104px;gap:4px 12px;
               align-items:baseline;padding:8px 0;border-bottom:1px solid #1b2029}
.local-list li.plain{display:block;font-size:12.5px;color:var(--text-2)}
.local-list .n{font-size:13px;color:#dfe3eb}
.local-list .d{font-size:13px;color:var(--text-2)}
.local-list .src{display:block;font-size:11.5px;color:var(--muted)}
.st{display:inline-block;padding:0 7px;border:1px solid #323a49;border-radius:999px;
    font-size:11px;line-height:1.6;color:#b9c0cf;white-space:nowrap}
.st.stale{border-color:#6b5a2c;color:var(--warn2)}
.st.na{border-style:dashed;border-color:#4a5263;color:var(--muted)}
.dt{font-size:12.5px;color:var(--text-2);font-variant-numeric:tabular-nums;white-space:nowrap}
.prov dl{display:flex;flex-direction:column;gap:6px;margin:10px 0 0}
.prov dl div{display:grid;grid-template-columns:64px minmax(0,1fr);gap:10px;font-size:12.5px}
.prov dt{color:var(--muted)}.prov dd{margin:0;color:#dfe3eb;overflow-wrap:anywhere}
.warns{display:flex;flex-direction:column;gap:6px;margin-top:12px;padding-top:10px;
       border-top:1px solid #222834}
.warns li{position:relative;padding-left:18px;font-size:12.5px;color:#e6d39c}
.warns li::before{content:"";position:absolute;left:2px;top:7px;width:7px;height:7px;
                  border:1.5px solid var(--warn2);transform:rotate(45deg)}
.strip{display:flex;flex-wrap:wrap;align-items:center;gap:8px 24px;margin:0 0 14px;
       padding:12px 16px;border:1px solid var(--line);border-radius:12px;background:var(--raised)}
.strip-t b{display:block}
.figs{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--muted)}
.figs b{font-size:17px;color:var(--fg);font-variant-numeric:tabular-nums}
.strip .meta{margin:0 0 0 auto}
.matrix th,.matrix td{padding:10px 12px;border-bottom:1px solid var(--hair);vertical-align:top}
.matrix thead th{vertical-align:bottom;border-bottom:1px solid var(--line)}
.matrix thead .h{display:block;font-size:13px;font-weight:600;color:#dfe3eb}
.matrix tbody th[scope=row]{position:sticky;left:0;z-index:1;background:var(--raised);
                            font-size:14px;color:var(--fg)}
.matrix tbody th .sub{max-width:240px}
.matrix .nm{display:block;margin-left:0}
.matrix .group th{padding:8px 12px;background:#11151c;color:var(--text-2);font-size:12px;
                  font-weight:600}
.matrix .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.matrix td.num{font-size:14.5px;font-weight:600}
.matrix .na-v{color:#6f778a;font-weight:400}
.matrix .cov,.matrix .src{font-size:12px;color:var(--text-2)}
.kv{display:flex;flex-direction:column;gap:2px;min-width:150px;margin:0}
.kv div{display:flex;justify-content:space-between;gap:12px;font-size:12.5px}
.kv dt{color:var(--muted);white-space:nowrap}
.kv dd{margin:0;color:#dfe3eb;font-variant-numeric:tabular-nums;white-space:nowrap}
.kv div:first-child dd{font-weight:600;color:var(--fg)}
.when{display:block;margin-top:6px;font-size:11px;line-height:1.5;color:var(--muted);
      font-variant-numeric:tabular-nums}
.local .tag{margin-top:6px}
.plain-list li{font-size:13px;color:#dfe3eb}
.plain-list li+li{margin-top:4px}
.foot-note{margin:10px 0 0;font-size:12px;color:var(--muted)}
footer div:last-child{margin-top:6px;color:var(--fg)}
@media (max-width:900px){.terms,.lower{grid-template-columns:minmax(0,1fr)}}
@media (max-width:720px){
  .wrap{display:block;padding:20px 16px 48px}
  .wrap>.fetched{margin-top:8px;text-align:left}
  .board:has(.stocks){overflow:visible;border:0;border-radius:0;background:none}
  .stocks,.stocks tbody{display:block;min-width:0}
  .board table.stocks{min-width:0}
  .stocks thead{display:none}
  .stocks tbody{margin-bottom:10px;overflow:hidden;border:1px solid var(--line);
                border-radius:12px;background:var(--raised)}
  .stocks tbody+tbody{border-top:1px solid var(--line)}
  .stocks .sum{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 14px;
               padding:12px 14px}
  .stocks .sum>*{padding:0}
  .stocks .sum th{grid-column:1;grid-row:1}
  .stocks .c-act{grid-column:2;grid-row:1;align-self:start}
  .stocks .lbl{display:block}
  .stocks .c-terms,.stocks .missing td{grid-column:1/-1}
  .stocks .c-date{text-align:right}
  .stocks .bar{width:100%}
  .stocks .cells .cell{flex:1 1 0;width:auto;min-width:0}
  .stocks .detail:not([hidden]),.stocks .detail>td{display:block}
  .panel{padding:14px}
  .local-list li{grid-template-columns:minmax(0,1fr) auto}
  .local-list .d,.local-list .dt{grid-column:1/-1}
}
"""

SCRIPT = """
document.querySelectorAll('button.more').forEach(button=>{
  button.addEventListener('click',()=>{
    const open=button.getAttribute('aria-expanded')!=='true';
    button.setAttribute('aria-expanded',String(open));
    document.getElementById(button.getAttribute('aria-controls')).hidden=!open;
    button.querySelector('.label').textContent=open?'收合':'明細';
  });
});
document.querySelectorAll('table[data-units]').forEach(table=>{
  const heads=[...table.querySelectorAll('thead th[aria-sort]')];
  const order=unit=>Number(unit.dataset.unit);
  heads.forEach(head=>{
    const button=head.querySelector('button.sort');
    button.addEventListener('click',()=>{
      const state=head.getAttribute('aria-sort');
      const next=state==='descending'?'ascending':state==='ascending'?'none':'descending';
      heads.forEach(h=>h.setAttribute('aria-sort','none'));
      head.setAttribute('aria-sort',next);
      const direction=next==='descending'?-1:next==='ascending'?1:0;
      const value=unit=>{const raw=unit.getAttribute('data-k-'+button.dataset.sort);
                         return raw===null?null:Number(raw)};
      const parents=new Set([...table.querySelectorAll('[data-unit]')].map(u=>u.parentElement));
      parents.forEach(parent=>{
        const units=[...parent.children].filter(u=>u.hasAttribute('data-unit'));
        units.sort((a,b)=>{
          if(!direction)return order(a)-order(b);
          const x=value(a),y=value(b);
          if(x===null||y===null)return x===null&&y===null?order(a)-order(b):x===null?1:-1;
          return (x-y)*direction||order(a)-order(b);
        });
        units.forEach(u=>parent.appendChild(u));
      });
    });
  });
});
"""
