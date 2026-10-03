"""2026-10-03 改版的驗收句：一檔一列、明細收合、資料不足不是 0、骨架共用。

改版前，台股分頁每一列高 2,678px —— 每檔約 1,270 字的說明全部塞進只分到
101px 的第一欄，分數與日期因為垂直置中，落在離標的名稱一千多 px 的地方。
這一份守的是「摘要列只放摘要」：指標細節只准出現在預設收合的明細列裡。
"""
from __future__ import annotations

import datetime as dt
import re

from research import config as rc
from research.domain import scoring_stock
from research.render import page as rpage

DAY = dt.date(2026, 10, 2)


def _scored(symbol: str, n: int = 300, **kw):
    closes = [100 + i * .2 for i in range(n)]
    score = scoring_stock.score_stock(
        symbol, closes, opens=[c - .1 for c in closes], highs=[c + 1 for c in closes],
        lows=[c - 1 for c in closes], volumes=[100_000] * n, **kw)
    return [(DAY, score)], {"weighted_average": score.overall}


def _tab(tabs, key):
    return next(tab for tab in tabs if tab.key == key)


def _units(body: str) -> list[str]:
    return re.findall(r'<tbody data-unit="\d+".*?</tbody>', body, re.S)


def _summary(unit: str) -> str:
    return re.search(r'<tr class="sum.*?</tr>', unit, re.S).group(0)


def _unit_of(body: str, symbol: str) -> str:
    return next(unit for unit in _units(body) if f'class="sym">{symbol}<' in unit)


def test_one_row_per_stock_in_configured_order_with_details_collapsed():
    body = _tab(rpage.build_tabs({s: _scored(s) for s in rc.TW_STOCKS}), "tw").body
    units = _units(body)
    assert [re.search(r'class="sym">([^<]+)<', u).group(1) for u in units] == list(rc.TW_STOCKS)
    for unit in units:
        button = re.search(r'<button type="button" class="more"[^>]*>', unit).group(0)
        assert 'aria-expanded="false"' in button
        detail = re.search(r'aria-controls="([^"]+)"', button).group(1)
        assert f'<tr class="detail" id="{detail}" hidden>' in unit


def test_summary_row_carries_no_indicator_wall():
    """根本問題：指標細節不得回到摘要列。"""
    unit = _units(_tab(rpage.build_tabs({"2330.TW": _scored("2330.TW")}), "tw").body)[0]
    summary = _summary(unit)
    for detail in ("KD(9,3,3)", "權重", "名稱來源", "強度 C"):
        assert detail not in summary, detail
        assert detail in unit, detail
    assert len(re.sub(r"<[^>]+>", "", summary)) < 200


def test_insufficient_terms_say_so_instead_of_zero():
    """SPCX 這種新上市的：中期、長期是「資料不足」，不是 0 分，也不是空白。"""
    unit = _unit_of(_tab(rpage.build_tabs({"SPCX": _scored("SPCX", n=59)}), "us").body, "SPCX")
    summary = _summary(unit)
    assert summary.count('class="cell na"') == 2
    assert ">+0<" not in summary and ">0<" not in summary
    assert "資料不足：中期需要 60 根，只有 59 根" in unit
    assert "資料不足：長期需要 200 根，只有 59 根" in unit
    assert "低涵蓋・降級" in summary


def test_us_rows_have_no_chips_cell_and_tw_rows_do():
    """美股沒有三大法人：籌碼那一格不存在，不是 0。"""
    tabs = rpage.build_tabs({
        "2330.TW": _scored("2330.TW", net_shares_series=[5_000.0] * 5,
                           volume_shares_series=[100_000.0] * 5),
        "NVDA": _scored("NVDA"),
    })
    tw = _summary(_unit_of(_tab(tabs, "tw").body, "2330.TW"))
    us = _summary(_unit_of(_tab(tabs, "us").body, "NVDA"))
    assert tw.count('class="cell ') == 4 and ">籌碼<" in tw
    assert us.count('class="cell ') == 3 and ">籌碼<" not in us


def test_each_row_keeps_its_own_date_source_and_fetch_time():
    tabs = rpage.build_tabs(
        {"2330.TW": _scored("2330.TW")},
        provenance_by_symbol={"2330.TW": ("價格：yfinance；籌碼：TWSE T86", "2026-10-02 18:10")})
    unit = _units(_tab(tabs, "tw").body)[0]
    assert "2026-10-02" in _summary(unit)
    assert "價格：yfinance；籌碼：TWSE T86" in unit
    assert "2026-10-02 18:10" in unit


def test_missing_series_is_one_explained_row():
    tabs = rpage.build_tabs({}, missing_reasons={"2330.TW": "還原序列資料不足，無法計分"})
    unit = _units(_tab(tabs, "tw").body)[0]
    assert "還原序列資料不足，無法計分" in unit
    assert 'class="more"' not in unit


def test_sorting_is_offered_and_keys_are_numbers():
    body = _tab(rpage.build_tabs({"2330.TW": _scored("2330.TW")}), "tw").body
    assert 'data-sort="comp"' in body and 'data-sort="native"' in body
    unit = _units(body)[0]
    assert re.search(r'data-k-comp="-?\d+(\.\d+)?"', unit)


def test_market_breadth_is_listed_once_not_per_stock():
    """漲跌家數是全市場一筆，改版前每檔各重複一次。"""
    breadth = {"advancers_count": 483, "decliners_count": 506, "unchanged_count": 91}
    provenance = {"source": "TWSE MI_INDEX", "data_date": "2026-10-02",
                  "retrieved_at": "2026-10-02T21:41:00"}
    views = {s: {"local": {"breadth": breadth}, "provenance": {"breadth": provenance}}
             for s in rc.TW_STOCKS}
    body = _tab(rpage.build_tabs({}, local_by_symbol=views), "tw_local").body
    assert body.count(">483<") == 1
    assert "全市場" in body and "TWSE MI_INDEX" in body


def test_page_groups_tabs_and_keeps_the_shared_skeleton():
    tabs = rpage.build_tabs({}, local_by_symbol={}, fundamentals_by_symbol={})
    assert [(t.group, t.key) for t in tabs] == [
        ("評分", "tw"), ("評分", "us"), ("台股本地", "tw_local"), ("台股本地", "tw_revenue"),
        ("基本面", "fundamental_valuation"), ("基本面", "fundamental_profitability"),
        ("基本面", "fundamental_growth"), ("基本面", "fundamental_structure"),
        ("基本面", "fundamental_theses")]
    html = rpage.render_page(tabs, title="stock-research", tagline="私人研究用",
                             last_run_at="2026-10-02 21:45")
    assert '<nav class="grouped"' in html
    assert "最後一次抓取" in html and "2026-10-02 21:45" in html
    assert "**" not in html
    assert "<strong>加了鎖的公開頁面</strong>" in html
    assert "本頁不構成投資建議" in html
    assert "http://" not in html and "https://" not in html and "<img" not in html


def test_names_from_outside_sources_are_escaped(monkeypatch):
    """台股名稱來自 TWSE 的外部資料；Tab.body 會原樣插進頁面，跳脫由這一側負責。"""
    monkeypatch.setitem(rc.NAMES, "2330.TW", "<script>alert(1)</script>")
    body = _tab(rpage.build_tabs({"2330.TW": _scored("2330.TW")}), "tw").body
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
