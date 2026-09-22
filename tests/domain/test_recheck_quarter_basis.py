"""回補批 R-4（二）：季別論點的口徑要跟著資料走。

台股官方給的是**累計至該季**的毛利率，美股 yfinance 給的是**單季**。
同一句「毛利率連三季上升」蓋在兩種口徑上就是話講得比資料多 —— 句子要自己說清楚，
兩種口徑混在一起則什麼都不說。
"""
from __future__ import annotations

from research.domain.fundamentals import FundamentalReport, QuarterMetrics, rule_theses


def _report(values, basis="單季", periods=("2025Q3", "2025Q4", "2026Q1")):
    return FundamentalReport("T", {}, tuple(
        QuarterMetrics(period, value, None, basis)
        for period, value in zip(periods, values)))


def test_cumulative_series_says_so_in_the_sentence():
    theses = rule_theses(_report((50.0, 52.0, 54.0), basis="累計"))
    assert len(theses) == 1
    assert theses[0].side == "多方"
    assert "累計毛利率連三季上升" in theses[0].text


def test_single_quarter_series_keeps_the_plain_wording():
    theses = rule_theses(_report((54.0, 52.0, 50.0), basis="單季"))
    assert len(theses) == 1
    assert theses[0].side == "空方"
    assert theses[0].text.startswith("單季毛利率連三季下降")


def test_mixed_basis_makes_no_claim_at_all():
    report = FundamentalReport("T", {}, (
        QuarterMetrics("2025Q3", 50.0, None, "累計"),
        QuarterMetrics("2025Q4", 52.0, None, "單季"),
        QuarterMetrics("2026Q1", 54.0, None, "累計"),
    ))
    assert rule_theses(report) == ()


def test_two_quarters_still_make_no_claim():
    assert rule_theses(_report((50.0, 52.0), periods=("2025Q4", "2026Q1"))) == ()
