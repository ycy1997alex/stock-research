import datetime as dt

from research.domain.fundamentals import (
    GROUPS, INSUFFICIENT, FundamentalReport, Metric, QuarterMetrics, rule_theses,
)


def test_missing_fields_stay_insufficient_and_coverage_is_per_symbol():
    day = dt.date(2026, 9, 22)
    report = FundamentalReport("SPCX", {
        "pe_ratio": Metric(None, "Yahoo snapshot", day),
        "operating_margin_pct": Metric(-1.8, "Yahoo snapshot", day),
    })
    assert sum(len(fields) for fields in GROUPS.values()) == 11
    assert report.metric("pe_ratio").status == INSUFFICIENT
    assert report.metric("gross_margin_pct").status == INSUFFICIENT
    assert report.coverage.available == 1
    assert report.coverage.expected == 11
    assert report.metric("operating_margin_pct").value == -1.8


def test_actual_zero_is_present_and_dated_field_cannot_be_used_early():
    day = dt.date(2026, 9, 22)
    report = FundamentalReport("AAPL", {
        "dividend_yield_pct": Metric(0.0, "Yahoo", day),
        "revenue_yoy_pct": Metric(12.0, "Yahoo", day + dt.timedelta(days=1)),
    })
    asof = report.asof(day)
    assert asof.metric("dividend_yield_pct").value == 0.0
    assert asof.metric("revenue_yoy_pct").status == INSUFFICIENT
    assert asof.coverage.available == 1


def test_rule_theses_use_observed_changes_and_return_none_when_missing():
    day = dt.date(2026, 9, 22)
    report = FundamentalReport("AAPL", {
        "revenue_yoy_pct": Metric(16.4, "Yahoo", day),
        "earnings_yoy_pct": Metric(-8.0, "Yahoo", day),
    }, quarters=(
        QuarterMetrics("2025Q4", gross_margin_pct=42.0),
        QuarterMetrics("2026Q1", gross_margin_pct=44.0),
        QuarterMetrics("2026Q2", gross_margin_pct=46.0),
    ))
    theses = rule_theses(report)
    assert any(t.side == "多方" and "毛利率" in t.text for t in theses)
    assert any(t.side == "多方" and "營收" in t.text for t in theses)
    assert any(t.side == "空方" and "獲利" in t.text for t in theses)
    assert rule_theses(FundamentalReport("SPCX", {})) == ()
    assert all(word not in t.text for t in theses
               for word in ("目標價", "催化劑", "信心水準"))
