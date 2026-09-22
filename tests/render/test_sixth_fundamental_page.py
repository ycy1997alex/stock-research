import datetime as dt

from research import config
from research.domain.fundamentals import FundamentalReport, Metric, QuarterMetrics
from research.render import page


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
    assert all(len(tab.rows) == 15 for tab in groups.values())
    valuation = groups["fundamental_valuation"]
    tw = next(row for row in valuation.rows if row.label.startswith("2330.TW"))
    spcx = next(row for row in valuation.rows if row.label.startswith("SPCX"))
    assert "本益比 21" in tw.value
    assert tw.fundamental_coverage.available == 3
    assert spcx.value is None
    assert spcx.fundamental_coverage.available == 0
    assert spcx.fundamental_coverage.expected == 11
    assert "資料不足" in spcx.note
    assert "資料來自公開財報摘要，口徑可能與正式財報不同" in valuation.intro
    thesis = next(row for row in groups["fundamental_theses"].rows
                  if row.label.startswith("2330.TW"))
    assert "毛利率連三季上升" in thesis.note
    assert "營收較去年同期增加" in thesis.note
    assert all(word not in thesis.note for word in ("目標價", "催化劑", "信心水準"))
