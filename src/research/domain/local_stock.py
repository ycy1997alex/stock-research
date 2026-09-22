"""Market-specific observations, each with its own date and missing state."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalItem:
    name: str
    score: float | None
    weight: float
    status: str
    detail: str
    data_date: str | None
    age_days: int | None
    source: str


@dataclass(frozen=True, slots=True)
class LocalScore:
    score: float | None
    items: tuple[LocalItem, ...]

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(
            f"{item.name}：{item.detail}（{item.status}；資料日 {item.data_date or '未知'}；"
            f"延遲 {item.age_days if item.age_days is not None else '未知'} 天；"
            f"來源 {item.source or '未記錄'}）"
            for item in self.items
        )


def _clip(value: float) -> float:
    return max(-100.0, min(100.0, value))


def _item(name: str, value: dict | None, provenance: dict | None,
          day: dt.date, limit: int, score: float | None, detail: str,
          weight: float = 1.0) -> LocalItem:
    provenance = provenance or {}
    date_text = provenance.get("data_date")
    source = provenance.get("source", "")
    try:
        age = (day - dt.date.fromisoformat(date_text)).days if date_text else None
    except ValueError:
        age = None
    if value is None or age is None or age < 0:
        return LocalItem(name, None, weight, "資料不足", detail, date_text, age, source)
    if age > limit:
        return LocalItem(name, None, weight, "過期", f"延遲 {age} 天；超過 {limit} 天門檻", date_text, age, source)
    return LocalItem(name, score, weight, "有效" if score is not None else "資料不足",
                     detail, date_text, age, source)


def _aggregate(items: list[LocalItem]) -> LocalScore:
    present = [item for item in items if item.score is not None]
    weight = sum(item.weight for item in present)
    return LocalScore(sum(item.score * item.weight for item in present) / weight if weight else None,
                      tuple(items))


def score_tw_local(view: dict, day: dt.date,
                   t86_score: float | None = None) -> LocalScore:
    """Published Taiwan observations only; revenue and quarterly reports never enter."""
    local, provenance = view.get("local") or {}, view.get("provenance") or {}
    items: list[LocalItem] = []

    value = local.get("valuation")
    pe = value.get("pe_ratio") if value else None
    yield_pct = value.get("dividend_yield_pct") if value else None
    # Cheapness and yield are heuristics, not expected-return estimates.
    score = _clip((20 - pe) * 4 + (yield_pct - 2) * 10) if isinstance(pe, (float, int)) and pe > 0 and isinstance(yield_pct, (float, int)) else None
    items.append(_item("A 官方估值", value, provenance.get("valuation"), day, 5, score,
                       f"PE {pe}；殖利率 {yield_pct}%（估值相對刻度）" if score is not None else "本益比或殖利率缺值"))

    value = local.get("breadth")
    up = value.get("advancers_count") if value else None
    down = value.get("decliners_count") if value else None
    total = (up or 0) + (down or 0)
    score = _clip((up - down) / total * 100) if isinstance(up, int) and isinstance(down, int) and total > 0 else None
    items.append(_item("B 漲跌家數", value, provenance.get("breadth"), day, 5, score,
                       f"上漲 {up}／下跌 {down}" if score is not None else "漲跌家數缺值"))

    value = local.get("distribution")
    # A level-only concentration snapshot is descriptive; direction needs a
    # comparison with a prior week, so a solitary observation stays missing.
    previous = value.get("previous_top_pct") if value else None
    top = (value.get("grades") or {}).get("15", {}).get("custody_pct") if value else None
    score = _clip((top - previous) * 20) if isinstance(top, (float, int)) and isinstance(previous, (float, int)) else None
    items.append(_item("D 集保分布", value, provenance.get("distribution"), day, 14, score,
                       f"大戶持股變化 {top - previous:+.2f} 個百分點" if score is not None else "需前一期大戶持股比率"))

    value = local.get("foreign")
    current = value.get("foreign_holding_pct") if value else None
    previous = value.get("previous_foreign_holding_pct") if value else None
    score = _clip((current - previous) * 20) if isinstance(current, (float, int)) and isinstance(previous, (float, int)) else None
    items.append(_item("E 外資持股", value, provenance.get("foreign"), day, 5, score,
                       f"持股變化 {current - previous:+.2f} 個百分點" if score is not None else "需前一期外資持股比率"))

    value = local.get("day_trade")
    ratio = value.get("day_trade_ratio_pct") if value else None
    score = _clip(-(ratio - 10) * 4) if isinstance(ratio, (float, int)) else None
    items.append(_item("F 當沖比", value, provenance.get("day_trade"), day, 5, score,
                       f"當沖占成交量 {ratio:.1f}%（過熱風險刻度）" if score is not None else "當沖比缺值"))

    value = local.get("lending")
    current = value.get("borrowed_short_balance_shares") if value else None
    previous = value.get("previous_borrowed_short_balance_shares") if value else None
    score = _clip(-((current / previous - 1) * 100) * 4) if isinstance(current, (float, int)) and isinstance(previous, (float, int)) and previous > 0 else None
    items.append(_item("G 借券餘額", value, provenance.get("lending"), day, 5, score,
                       f"借券餘額變化 {(current / previous - 1) * 100:+.1f}%" if score is not None else "需前一期借券餘額"))

    value = local.get("margin_estimate")
    ratio = value.get("maintenance_pct") if value else None
    score = -100 if isinstance(ratio, (float, int)) and ratio < 130 else -40 if isinstance(ratio, (float, int)) and ratio < 160 else 0 if isinstance(ratio, (float, int)) else None
    items.append(_item("H 融資維持率", value, provenance.get("margin_estimate"), day, 5, score,
                       f"推算維持率 {ratio:.1f}%（非公布值）" if score is not None else "維持率推算缺值"))

    t86_record = {"data_date": day.isoformat(), "source": "TWSE T86"} if t86_score is not None else {}
    items.append(_item("T86 三大法人", {"score": t86_score} if t86_score is not None else None,
                       t86_record, day, 5, t86_score,
                       f"買賣超相對成交量分數 {t86_score:+.0f}" if t86_score is not None else "買賣超資料不足"))
    return _aggregate(items)


def score_us_local(records: dict, day: dt.date) -> LocalScore:
    """13F changes, Form 4 transactions and analyst crowding stay distinct."""
    items: list[LocalItem] = []
    rec = records.get("institutional")
    value = rec.get("value") if rec else None
    now, before = ((value or {}).get(key) for key in ("held_pct", "prior_held_pct"))
    score = _clip((now - before) * 20) if isinstance(now, (float, int)) and isinstance(before, (float, int)) else None
    items.append(_item("13F 機構持股", value, rec, day, 100, score,
                       f"持股變化 {now - before:+.2f} 個百分點" if score is not None else "需兩期可比持股比率"))

    rec = records.get("insider")
    value = rec.get("value") if rec else None
    net = (value or {}).get("net_acquired_shares")
    score = 100 if isinstance(net, (float, int)) and net > 0 else -100 if isinstance(net, (float, int)) and net < 0 else 0 if net == 0 else None
    items.append(_item("Form 4 內部人", value, rec, day, 30, score,
                       f"近一期淨取得 {net:+,.0f} 股" if score is not None else "內部人交易缺值"))

    rec = records.get("analyst")
    value = rec.get("value") if rec else None
    count = (value or {}).get("analyst_count")
    dispersion = (value or {}).get("rating_dispersion_pct")
    # Only a crowding penalty. Never turn a buy consensus into a buy signal.
    score = _clip(-min(count / 20, 1) * max(0, 100 - dispersion)) if isinstance(count, (int, float)) and isinstance(dispersion, (int, float)) else None
    items.append(_item("分析師覆蓋與分歧", value, rec, day, 60, score,
                       f"覆蓋 {count} 家、評等分歧度 {dispersion:.1f}%（擁擠程度）" if score is not None else "覆蓋數或分歧度缺值"))
    return _aggregate(items)
