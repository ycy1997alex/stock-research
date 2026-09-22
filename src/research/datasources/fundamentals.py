"""Official Taiwan quarterly snapshots and Yahoo issuer summaries.

The observed date is when this application first read a snapshot. A statement's
quarter-end is a reporting period, never an inferred public release date.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import time
from collections.abc import Mapping

import requests

from research.domain.fundamentals import FundamentalReport, Metric, QuarterMetrics

TW_URLS = {
    "ratios": "https://openapi.twse.com.tw/v1/opendata/t187ap17_L",
    "income": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "balance": "https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci",
}
TW_SOURCE = "TWSE 公開財報摘要（取得日快照；出表日非財報首次公開日）"
US_SOURCE = "Yahoo Finance 財報摘要（取得日快照；季末非發布日）"
GROSS_KEY = "毛利率(%)(營業毛利)/(營業收入)"
OPERATING_KEY = "營業利益率(%)(營業利益)/(營業收入)"


def _number(value: object) -> float | None:
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _roc_date(raw: object) -> dt.date | None:
    digits = re.sub(r"\D", "", str(raw or ""))
    try:
        if len(digits) == 7:
            return dt.date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:]))
        if len(digits) == 8:
            return dt.date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    except ValueError:
        pass
    return None


def _period(row: Mapping) -> str | None:
    try:
        year, quarter = int(row.get("年度")) + 1911, int(row.get("季別"))
    except (ValueError, TypeError):
        return None
    return f"{year}Q{quarter}" if 1 <= quarter <= 4 else None


def parse_tw_official(payloads: Mapping[str, list[dict]],
                      stamp: dt.datetime) -> dict[str, FundamentalReport]:
    by_kind: dict[str, dict[tuple[str, str], dict]] = {}
    for kind in TW_URLS:
        rows = payloads.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError(f"TWSE {kind}: response is not a list")
        mapped: dict[tuple[str, str], dict] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("公司代號", "")).strip()
            period = _period(row)
            published = _roc_date(row.get("出表日期"))
            if (len(symbol) == 4 and symbol.isdigit() and period
                    and published is not None and published <= stamp.date()):
                mapped[(f"{symbol}.TW", period)] = row
        by_kind[kind] = mapped
    symbols = {symbol for records in by_kind.values() for symbol, _ in records}
    reports = {}
    for symbol in symbols:
        periods = {period for records in by_kind.values() for sym, period in records if sym == symbol}
        period = max(periods)
        ratios = by_kind["ratios"].get((symbol, period), {})
        balance = by_kind["balance"].get((symbol, period), {})
        liabilities = _number(balance.get("負債總計"))
        equity = _number(balance.get("權益總計"))
        debt_equity = liabilities / equity * 100 if liabilities is not None and equity and equity > 0 else None
        values = {
            "gross_margin_pct": _number(ratios.get(GROSS_KEY)),
            "operating_margin_pct": _number(ratios.get(OPERATING_KEY)),
            "debt_equity_pct": debt_equity,
        }
        metrics = {key: Metric(value, TW_SOURCE, stamp.date(), stamp, period,
                               "財報期別與資料取得日分開；未取得正式首次發布日")
                   for key, value in values.items()}
        quarter = QuarterMetrics(period, values["gross_margin_pct"], stamp.date())
        reports[symbol] = FundamentalReport(symbol, metrics, (quarter,))
    return reports


def fetch_tw_official(stamp: dt.datetime, get=requests.get) -> dict[str, FundamentalReport]:
    payloads = {}
    for index, (kind, url) in enumerate(TW_URLS.items()):
        if index:
            time.sleep(.6)
        response = get(url, timeout=25, headers={"User-Agent": "stock-research/0.1 (personal research)"})
        response.raise_for_status()
        payloads[kind] = response.json()
    return parse_tw_official(payloads, stamp)


def _fraction_pct(info: dict, key: str) -> float | None:
    value = _number(info.get(key))
    return value * 100 if value is not None else None


def _quarter_history(frame, stamp: dt.datetime) -> tuple[QuarterMetrics, ...]:
    if frame is None or frame.empty or "Gross Profit" not in frame.index or "Total Revenue" not in frame.index:
        return ()
    quarters = []
    for col in frame.columns:
        try:
            period_end = dt.date.fromisoformat(str(col)[:10])
        except ValueError:
            continue
        if period_end > stamp.date():
            continue
        gross = _number(frame.loc["Gross Profit", col])
        revenue = _number(frame.loc["Total Revenue", col])
        value = gross / revenue * 100 if gross is not None and revenue is not None and revenue > 0 else None
        quarter = (period_end.month - 1) // 3 + 1
        quarters.append(QuarterMetrics(f"{period_end.year}Q{quarter}", value, stamp.date()))
    return tuple(sorted(quarters, key=lambda q: q.period))


def parse_us_yahoo(symbol: str, ticker, stamp: dt.datetime) -> FundamentalReport:
    info = ticker.info or {}
    debt, cash, ebitda = (_number(info.get(key)) for key in ("totalDebt", "totalCash", "ebitda"))
    net_debt_ebitda = (debt - cash) / ebitda if None not in (debt, cash, ebitda) and ebitda > 0 else None
    values = {
        "pe_ratio": _number(info.get("trailingPE")),
        "pb_ratio": _number(info.get("priceToBook")),
        "ev_ebitda_ratio": _number(info.get("enterpriseToEbitda")),
        "dividend_yield_pct": _number(info.get("dividendYield")),
        "gross_margin_pct": _fraction_pct(info, "grossMargins"),
        "operating_margin_pct": _fraction_pct(info, "operatingMargins"),
        "roe_pct": _fraction_pct(info, "returnOnEquity"),
        "revenue_yoy_pct": _fraction_pct(info, "revenueGrowth"),
        "earnings_yoy_pct": _fraction_pct(info, "earningsGrowth"),
        "net_debt_ebitda_ratio": net_debt_ebitda,
        "debt_equity_pct": _number(info.get("debtToEquity")),
    }
    try:
        quarterly = ticker.quarterly_income_stmt
    except Exception:
        quarterly = None
    quarters = _quarter_history(quarterly, stamp)
    period = quarters[-1].period if quarters else None
    metrics = {key: Metric(value, US_SOURCE, stamp.date(), stamp, period,
                           "Yahoo 摘要欄位；資料首次公開日未提供")
               for key, value in values.items()}
    return FundamentalReport(symbol, metrics, quarters, info.get("industry"))


def fetch_us_yahoo(symbol: str, stamp: dt.datetime) -> FundamentalReport:
    import yfinance as yf
    return parse_us_yahoo(symbol, yf.Ticker(symbol), stamp)
