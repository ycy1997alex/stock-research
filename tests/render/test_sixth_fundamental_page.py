import datetime as dt
import re

from research import config
from research.domain.fundamentals import FundamentalReport, Metric, QuarterMetrics
from research.render import page


def _row(body: str, symbol: str) -> str:
    return next(chunk for chunk in body.split("<tr")
                if f'class="sym">{symbol}<' in chunk)


def test_four_group_tables_and_rule_theses_show_all_15_symbols_with_coverage():
    day = dt.date(2026, 9, 22)
    report = FundamentalReport("2330.TW", {
        "pe_ratio": Metric(21.0, "TWSE BWIBBU_ALL", day),
        "gross_margin_pct": Metric(67.0, "TWSE t187ap17_L", day, period="2026Q2"),
        "revenue_yoy_pct": Metric(12.0, "TWSE t187ap05_L", day),
    }, (QuarterMetrics("2025Q4", 60, day), QuarterMetrics("2026Q1", 64, day),
        QuarterMetrics("2026Q2", 67, day)))
    reports = {symbol: FundamentalReport(symbol, {}) for symbol in config.ALL_SYMBOLS}
    reports["2330.TW"] = report
    tabs = page.build_tabs({}, fundamentals_by_symbol=reports)
    groups = {tab.key: tab for tab in tabs if tab.key.startswith("fundamental_")}
    assert set(groups) == {"fundamental_valuation", "fundamental_profitability",
                           "fundamental_growth", "fundamental_structure",
                           "fundamental_theses"}
    assert all(len(re.findall(r'<th scope="row">', tab.body)) == 15 for tab in groups.values())
    valuation = groups["fundamental_valuation"]
    tw = _row(valuation.body, "2330.TW")
    spcx = _row(valuation.body, "SPCX")
    assert ">21.00<" in tw
    assert "基本面 3/11 項（27%）" in tw
    assert "資料不足：本益比" in spcx
    assert "基本面 0/11 項（0%）" in spcx
    assert "資料來自公開財報摘要，口徑可能與正式財報不同" in valuation.intro
    assert "2026Q2" in _row(groups["fundamental_profitability"].body, "2330.TW")
    theses = groups["fundamental_theses"].body
    thesis = _row(theses, "2330.TW")
    assert "毛利率連三季上升" in thesis
    assert "營收較去年同期增加" in thesis
    assert "資料不足" in _row(theses, "SPCX")
    assert all(word not in theses for word in ("目標價", "催化劑", "信心水準"))
