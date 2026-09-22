"""Dated Yahoo Finance issuer observations; never infer absent publication dates."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Observation:
    data_date: dt.date
    value: dict
    source: str


def _date(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_institutional(frame) -> Observation | None:
    """Compare the same reported top-holder cohort using share-change proxy.

    This is explicitly not total institutional ownership. Yahoo exposes only
    the top reported holders; pctChange approximates their prior share stake.
    """
    if frame is None or frame.empty:
        return None
    dated = [(_date(row.get("Date Reported")), row) for row in frame.to_dict("records")]
    latest = max((day for day, _ in dated if day is not None), default=None)
    if latest is None:
        return None
    current = previous = 0.0
    count = 0
    for day, row in dated:
        if day != latest:
            continue
        pct = _number(row.get("pctHeld"))
        change = _number(row.get("pctChange"))
        if pct is None or change is None or pct < 0 or change <= -1:
            continue
        current += pct * 100
        previous += pct / (1 + change) * 100
        count += 1
    if not count:
        return None
    return Observation(latest, {"held_pct": current, "prior_held_pct": previous,
                                "reported_holders_count": count,
                                "method": "同一組前大持有人持股變動代理值，非全體機構持股比率"},
                       "Yahoo Finance top institutional holders（申報日期；前大持有人代理值）")


def parse_insider(frame, today: dt.date) -> Observation | None:
    if frame is None or frame.empty:
        return None
    net = 0.0
    dates: list[dt.date] = []
    count = 0
    for row in frame.to_dict("records"):
        day = _date(row.get("Start Date"))
        shares = _number(row.get("Shares"))
        if day is None or shares is None or not 0 <= (today - day).days <= 30:
            continue
        text = str(row.get("Text") or "").lower()
        if "purchase" in text or "buy" in text:
            net += shares
        elif "sale" in text or "sell" in text:
            net -= shares
        else:
            continue
        dates.append(day)
        count += 1
    if not count:
        return None
    return Observation(max(dates), {"net_acquired_shares": net,
                                    "classified_transactions_count": count},
                       "Yahoo Finance insider transactions（只計明確買入／賣出）")


def parse_analyst(frame, today: dt.date) -> Observation | None:
    if frame is None or frame.empty:
        return None
    rows = [row for row in frame.to_dict("records") if row.get("period") == "0m"]
    if not rows:
        return None
    counts = [_number(rows[0].get(key)) for key in
              ("strongBuy", "buy", "hold", "sell", "strongSell")]
    if any(value is None or value < 0 for value in counts):
        return None
    total = sum(counts)
    if total <= 0:
        return None
    dispersion = (1 - max(counts) / total) * 100
    return Observation(today, {"analyst_count": int(total),
                               "rating_dispersion_pct": dispersion,
                               "method": "五類評等中最大類以外的占比；只衡量擁擠程度"},
                       "Yahoo Finance recommendations 0m（取得日快照，非評等發布日）")


def fetch_one(symbol: str, today: dt.date, ticker=None) -> dict[str, Observation]:
    if ticker is None:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
    candidates = {
        "institutional": parse_institutional(ticker.institutional_holders),
        "insider": parse_insider(ticker.insider_transactions, today),
        "analyst": parse_analyst(ticker.recommendations, today),
    }
    return {name: value for name, value in candidates.items() if value is not None}
