import datetime as dt

import pandas as pd
import pytest

from research.datasources.fundamentals import fetch_us_yahoo, parse_tw_official, parse_us_yahoo
from research.domain.fundamentals import INSUFFICIENT


STAMP = dt.datetime(2026, 9, 22, 11, 0)


def _tw_payload():
    identity = {"出表日期": "1150922", "年度": "115", "季別": "2", "公司代號": "2330"}
    return {
        "ratios": [{**identity, "毛利率(%)(營業毛利)/(營業收入)": "67.03",
                    "營業利益率(%)(營業利益)/(營業收入)": "59.29"}],
        "balance": [{**identity, "負債總計": "2901183746.00", "權益總計": "6474470981.00"}],
        "income": [{**identity, "營業收入": "2404483690.00",
                   "淨利（淨損）歸屬於母公司業主": "1279041690.00"}],
    }


def test_official_quarter_fields_keep_report_period_separate_from_snapshot_date():
    got = parse_tw_official(_tw_payload(), STAMP)["2330.TW"]
    assert got.metric("gross_margin_pct").value == 67.03
    assert got.metric("operating_margin_pct").value == 59.29
    assert got.metric("debt_equity_pct").value > 0
    assert got.metric("roe_pct").status == INSUFFICIENT
    assert got.metric("gross_margin_pct").period == "2026Q2"
    assert got.metric("gross_margin_pct").data_date == STAMP.date()
    assert got.asof(STAMP.date() - dt.timedelta(days=1)).coverage.available == 0


def test_official_missing_field_is_insufficient_not_zero():
    payload = _tw_payload()
    payload["ratios"][0].pop("毛利率(%)(營業毛利)/(營業收入)")
    got = parse_tw_official(payload, STAMP)["2330.TW"]
    assert got.metric("gross_margin_pct").status == INSUFFICIENT
    assert got.metric("gross_margin_pct").value is None


def test_yahoo_fraction_fields_convert_to_percent_without_filling_missing():
    frame = pd.DataFrame({pd.Timestamp("2026-06-30"): [40.0, 100.0],
                          pd.Timestamp("2026-03-31"): [30.0, 100.0]},
                         index=["Gross Profit", "Total Revenue"])
    class Ticker:
        info = {"trailingPE": None, "priceToBook": 15.7, "grossMargins": .4,
                "operatingMargins": -.018, "revenueGrowth": .919,
                "debtToEquity": 31.211, "dividendYield": None,
                "totalDebt": 40.0, "totalCash": 10.0, "ebitda": 5.0}
        quarterly_income_stmt = frame

    report = parse_us_yahoo("SPCX", Ticker(), STAMP)
    assert report.metric("pe_ratio").status == INSUFFICIENT
    assert report.metric("gross_margin_pct").value == 40.0
    assert report.metric("operating_margin_pct").value == pytest.approx(-1.8)
    assert report.metric("revenue_yoy_pct").value == pytest.approx(91.9)
    assert report.metric("net_debt_ebitda_ratio").value == 6.0
    assert report.metric("dividend_yield_pct").status == INSUFFICIENT
    assert len(report.quarters) == 2


def test_yahoo_quarterly_endpoint_failure_keeps_available_summary(monkeypatch):
    class Ticker:
        info = {"priceToBook": 4.0}

        @property
        def quarterly_income_stmt(self):
            raise RuntimeError("quarterly endpoint unavailable")

    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda symbol: Ticker())
    report = fetch_us_yahoo("AAPL", STAMP)
    assert report.metric("pb_ratio").value == 4.0
    assert report.quarters == ()
