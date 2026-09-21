"""Official all-market Taiwan observations for the research local dimension.

One HTTP response is cached per dataset and run date. No missing report, field, or
symbol is represented as a zero. The parsers keep the report date separate from
the retrieval time and preserve the source's units in every numeric field name.
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Any

import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle
from research.domain.margin_tw import SHARES_PER_LOT


class NotPublishedYet(FetchError):
    """The official response contains no published observations."""


@dataclass(frozen=True, slots=True)
class Snapshot:
    source: str
    data_date: dt.date
    retrieved_at: dt.datetime
    values: dict[str, dict[str, Any]]


_UA = "stock-research/0.1 (personal research; contact via GitHub)"
_THROTTLE = Throttle(min_interval=0.6)
_CACHE: dict[tuple[str, dt.date], Snapshot] = {}
_URLS = {
    "valuation": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "breadth": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date:%Y%m%d}&type=ALLBUT0999&response=json",
    "revenue": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "distribution": "https://openapi.tdcc.com.tw/v1/opendata/1-5",
    "foreign": "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date={date:%Y%m%d}&response=json&selectType=ALLBUT0999",
    "day_trade": "https://www.twse.com.tw/exchangeReport/TWTB4U?date={date:%Y%m%d}&response=json&selectType=All",
    "lending": "https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={date:%Y%m%d}&response=json",
    "margin_estimate": "https://www.twse.com.tw/exchangeReport/TWTA1U?response=json&date={date:%Y%m%d}",
}


def _number(raw: Any) -> float | None:
    if raw is None or str(raw).strip() in {"", "-", "--", "N/A"}:
        return None
    try:
        value = float(str(raw).strip().replace(",", ""))
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def _integer(raw: Any) -> int | None:
    value = _number(raw)
    return int(value) if value is not None and value.is_integer() else None


def _date(raw: Any) -> dt.date:
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 7:
        return dt.date(1911 + int(digits[:3]), int(digits[3:5]), int(digits[5:]))
    if len(digits) == 8:
        return dt.date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    raise ValueError(f"invalid official data date: {raw!r}")


def _symbol(raw: Any) -> str | None:
    code = str(raw).strip()
    return f"{code}.TW" if len(code) == 4 and code.isdigit() else None


def _list(payload: Any, name: str) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise NotPublishedYet(f"{name}: no published rows")
    return payload


def _report(payload: Any, name: str) -> tuple[dt.date, dict]:
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        raise NotPublishedYet(f"{name}: no published report")
    return _date(payload.get("date")), payload


def _snapshot(source: str, date: dt.date, stamp: dt.datetime, values: dict) -> Snapshot:
    if not values:
        raise NotPublishedYet(f"{source} {date}: no usable observations")
    return Snapshot(source, date, stamp, values)


def parse_valuation(payload: Any, stamp: dt.datetime) -> Snapshot:
    rows = _list(payload, "BWIBBU_ALL")
    day = _date(rows[0].get("Date"))
    values = {}
    for row in rows:
        symbol = _symbol(row.get("Code"))
        if symbol and _date(row.get("Date")) == day:
            values[symbol] = {
                "pe_ratio": _number(row.get("PEratio")),
                "dividend_yield_pct": _number(row.get("DividendYield")),
                "pb_ratio": _number(row.get("PBratio")),
            }
    return _snapshot("TWSE BWIBBU_ALL", day, stamp, values)


def parse_breadth(payload: Any, stamp: dt.datetime) -> Snapshot:
    day, report = _report(payload, "MI_INDEX")
    table = next((t for t in report.get("tables", []) if "漲跌證券數合計" in t.get("title", "")
                  and "股票" in t.get("fields", [])), None)
    if not table:
        raise NotPublishedYet(f"MI_INDEX {day}: stock breadth table absent")
    stock_col = table["fields"].index("股票")
    counts = {}
    for row in table.get("data", []):
        label = str(row[0])
        key = ("advancers_count" if label.startswith("上漲") else
               "decliners_count" if label.startswith("下跌") else
               "unchanged_count" if label.startswith("持平") else None)
        if key and len(row) > stock_col:
            counts[key] = _integer(str(row[stock_col]).split("(")[0])
    up, down = counts.get("advancers_count"), counts.get("decliners_count")
    if up is None or down is None:
        raise NotPublishedYet(f"MI_INDEX {day}: stock advance/decline counts absent")
    counts["advance_decline_pct"] = up / (up + down) * 100 if up + down else None
    return _snapshot("TWSE MI_INDEX", day, stamp, {"market": counts})


def parse_revenue(payload: Any, stamp: dt.datetime) -> Snapshot:
    rows = _list(payload, "t187ap05_L")
    day = _date(rows[0].get("出表日期"))
    values = {}
    for row in rows:
        symbol = _symbol(row.get("公司代號"))
        period = re.sub(r"\D", "", str(row.get("資料年月", "")))
        if symbol and len(period) == 5 and _date(row.get("出表日期")) == day:
            values[symbol] = {
                "reporting_period": f"{1911 + int(period[:3]):04d}-{period[3:]}",
                # MOPS/TWSE monthly revenue is reported in NT$ thousands.
                "revenue_ktwd": _integer(row.get("營業收入-當月營收")),
                "revenue_yoy_pct": _number(row.get("營業收入-去年同月增減(%)")),
                "revenue_mom_pct": _number(row.get("營業收入-上月比較增減(%)")),
            }
    return _snapshot("TWSE t187ap05_L", day, stamp, values)


def parse_distribution(payload: Any, stamp: dt.datetime) -> Snapshot:
    rows = _list(payload, "TDCC 1-5")
    day = _date(rows[0].get("\ufeff資料日期", rows[0].get("資料日期")))
    values: dict[str, dict] = {}
    for row in rows:
        symbol = _symbol(row.get("證券代號"))
        if not symbol or _date(row.get("\ufeff資料日期", row.get("資料日期"))) != day:
            continue
        grade = str(row.get("持股分級", "")).strip()
        if not grade:
            continue
        values.setdefault(symbol, {"grades": {}})["grades"][grade] = {
            "holder_count": _integer(row.get("人數")),
            "shares": _integer(row.get("股數")),
            "custody_pct": _number(row.get("占集保庫存數比例%")),
        }
    return _snapshot("TDCC 1-5", day, stamp, values)


def parse_foreign_holdings(payload: Any, stamp: dt.datetime) -> Snapshot:
    day, report = _report(payload, "MI_QFIIS")
    fields = report.get("fields", [])
    wanted = ("證券代號", "發行股數", "外資及陸資尚可投資股數", "全體外資及陸資持有股數", "全體外資及陸資持股比率")
    if not all(key in fields for key in wanted):
        raise NotPublishedYet(f"MI_QFIIS {day}: required stock fields absent")
    positions = [fields.index(key) for key in wanted]
    values = {}
    for row in report.get("data", []):
        if len(row) <= max(positions):
            continue
        symbol = _symbol(row[positions[0]])
        if symbol:
            values[symbol] = {
                "issued_shares": _integer(row[positions[1]]),
                "foreign_available_shares": _integer(row[positions[2]]),
                "foreign_held_shares": _integer(row[positions[3]]),
                "foreign_holding_pct": _number(row[positions[4]]),
            }
    return _snapshot("TWSE MI_QFIIS", day, stamp, values)


def parse_day_trade(payload: Any, stamp: dt.datetime) -> Snapshot:
    day, report = _report(payload, "TWTB4U")
    table = next((t for t in report.get("tables", []) if "證券代號" in t.get("fields", [])
                  and "當日沖銷交易成交股數" in t.get("fields", [])), None)
    if not table:
        raise NotPublishedYet(f"TWTB4U {day}: individual volume table absent")
    fields = table["fields"]
    code, shares = fields.index("證券代號"), fields.index("當日沖銷交易成交股數")
    buy = fields.index("當日沖銷交易買進成交金額") if "當日沖銷交易買進成交金額" in fields else None
    values = {}
    for row in table.get("data", []):
        if len(row) <= max(code, shares):
            continue
        symbol = _symbol(row[code])
        if symbol:
            values[symbol] = {
                "day_trade_shares": _integer(row[shares]),
                "day_trade_buy_twd": _integer(row[buy]) if buy is not None and len(row) > buy else None,
            }
    return _snapshot("TWSE TWTB4U", day, stamp, values)


def parse_lending(payload: Any, stamp: dt.datetime) -> Snapshot:
    day, report = _report(payload, "TWT93U")
    fields = report.get("fields", [])
    # The report has two same-named balance columns. Keep their observed indices.
    if len(fields) < 13 or fields[0] != "代號" or fields[6] != "今日餘額" or fields[12] != "當日餘額":
        raise NotPublishedYet(f"TWT93U {day}: loan/borrow columns changed")
    values = {}
    for row in report.get("data", []):
        if len(row) <= 12:
            continue
        symbol = _symbol(row[0])
        if symbol:
            values[symbol] = {
                "short_balance_shares": _integer(row[6]),
                "borrowed_short_balance_shares": _integer(row[12]),
            }
    return _snapshot("TWSE TWT93U", day, stamp, values)


def parse_margin_stock(payload: Any, stamp: dt.datetime) -> Snapshot:
    """TWTA1U first balance group is per-stock financing, reported in lots.

    Convert to shares at the data boundary. Later repeated balance groups are
    short selling or lending and must not overwrite the first group.
    """
    day, report = _report(payload, "TWTA1U")
    fields = report.get("fields", [])
    if (len(fields) < 7 or fields[0] != "代號" or fields[2] != "前日餘額"
            or fields[6] != "今日餘額"):
        raise NotPublishedYet(f"TWTA1U {day}: per-stock financing columns changed")
    market_column = fields.index("市場別") if "市場別" in fields else None
    values = {}
    for row in report.get("data", []):
        if len(row) <= 6:
            continue
        if market_column is not None and len(row) > market_column and row[market_column] != "集中市場":
            continue
        symbol = _symbol(row[0])
        if symbol:
            previous_lots = _integer(row[2])
            balance_lots = _integer(row[6])
            values[symbol] = {
                "margin_prev_shares": previous_lots * SHARES_PER_LOT if previous_lots is not None else None,
                "margin_balance_shares": balance_lots * SHARES_PER_LOT if balance_lots is not None else None,
            }
    return _snapshot("TWSE TWTA1U", day, stamp, values)


PARSERS = {
    "valuation": parse_valuation,
    "breadth": parse_breadth,
    "revenue": parse_revenue,
    "distribution": parse_distribution,
    "foreign": parse_foreign_holdings,
    "day_trade": parse_day_trade,
    "lending": parse_lending,
    "margin_estimate": parse_margin_stock,
}


def fetch(dataset: str, run_date: dt.date) -> Snapshot:
    """One all-market request per dataset/run date, with no per-symbol HTTP."""
    if dataset not in PARSERS:
        raise ValueError(f"unknown TW local dataset: {dataset}")
    key = dataset, run_date
    if key in _CACHE:
        return _CACHE[key]
    url = _URLS[dataset].format(date=run_date)
    _THROTTLE.wait()
    COUNTER.bump("twse" if dataset != "distribution" else "tdcc")
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": _UA})
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FetchError(f"{dataset}: {exc}") from exc
    snapshot = PARSERS[dataset](payload, dt.datetime.now())
    if snapshot.data_date > run_date:
        raise FetchError(f"{dataset}: report date {snapshot.data_date} is after requested {run_date}")
    _CACHE[key] = snapshot
    return snapshot
