"""Dated, unscored issuer fundamentals and factual rule-based theses."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from barometer.domain.coverage import Coverage

INSUFFICIENT = "INSUFFICIENT"
# 季別口徑：官方台股那兩張表都是累計至該季，Yahoo 的季報是單季。
# 兩者不可混在同一句話裡（回補批 R-4）。
SINGLE_QUARTER = "單季"
# ⚠️ 官方是「年度累計」：每年 Q1 歸零重算，所以跨年度的兩筆不是同一段期間。
#    句子裡要看得出來這件事，不要只寫「累計」。
CUMULATIVE = "年度累計"
GROUPS = {
    "估值": ("pe_ratio", "pb_ratio", "ev_ebitda_ratio", "dividend_yield_pct"),
    "獲利能力": ("gross_margin_pct", "operating_margin_pct", "roe_pct"),
    "成長": ("revenue_yoy_pct", "earnings_yoy_pct"),
    "財務結構": ("net_debt_ebitda_ratio", "debt_equity_pct"),
}
LABELS = {
    "pe_ratio": "本益比", "pb_ratio": "股價淨值比", "ev_ebitda_ratio": "EV/EBITDA",
    "dividend_yield_pct": "股息殖利率", "gross_margin_pct": "毛利率",
    "operating_margin_pct": "營業利益率", "roe_pct": "ROE",
    "revenue_yoy_pct": "營收年增率", "earnings_yoy_pct": "獲利年增率",
    "net_debt_ebitda_ratio": "淨負債／EBITDA", "debt_equity_pct": "負債權益比",
}
PERCENT_FIELDS = frozenset(key for key in LABELS if key.endswith("_pct"))


@dataclass(frozen=True, slots=True)
class Metric:
    value: float | None
    source: str = ""
    data_date: dt.date | None = None
    retrieved_at: dt.datetime | None = None
    period: str | None = None
    note: str = ""

    @property
    def status(self) -> str:
        return "OK" if self.value is not None and math.isfinite(self.value) else INSUFFICIENT


@dataclass(frozen=True, slots=True)
class QuarterMetrics:
    period: str
    gross_margin_pct: float | None = None
    data_date: dt.date | None = None
    basis: str = SINGLE_QUARTER


@dataclass(frozen=True, slots=True)
class FundamentalReport:
    symbol: str
    metrics: dict[str, Metric]
    quarters: tuple[QuarterMetrics, ...] = ()
    industry: str | None = None

    def metric(self, key: str) -> Metric:
        if key not in LABELS:
            raise KeyError(key)
        return self.metrics.get(key, Metric(None))

    @property
    def coverage(self) -> Coverage:
        return Coverage(sum(self.metric(key).status == "OK" for key in LABELS), len(LABELS))

    def asof(self, day: dt.date) -> FundamentalReport:
        metrics = {key: value for key, value in self.metrics.items()
                   if value.data_date is not None and value.data_date <= day}
        quarters = tuple(q for q in self.quarters if q.data_date is not None and q.data_date <= day)
        return FundamentalReport(self.symbol, metrics, quarters, self.industry)


@dataclass(frozen=True, slots=True)
class Thesis:
    side: str
    text: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


def _quarter_number(period: str) -> int | None:
    if len(period) != 6 or period[4] != "Q" or not period[:4].isdigit() or period[5] not in "1234":
        return None
    return int(period[:4]) * 4 + int(period[5]) - 1


def rule_theses(report: FundamentalReport) -> tuple[Thesis, ...]:
    """Describe observed changes only; missing inputs generate no assertion."""
    theses: list[Thesis] = []
    recent = report.quarters[-3:]
    if len(recent) == 3:
        numbers = [_quarter_number(item.period) for item in recent]
        values = [item.gross_margin_pct for item in recent]
        bases = {item.basis for item in recent}
        if (all(number is not None for number in numbers)
                and numbers[1] == numbers[0] + 1 and numbers[2] == numbers[1] + 1
                and all(value is not None and math.isfinite(value) for value in values)
                and len(bases) == 1):
            # 口徑寫進句子裡：累計毛利率與單季毛利率是兩件事，混著比就是話比資料多
            label = f"{bases.pop()}毛利率"
            if values[0] < values[1] < values[2]:
                theses.append(Thesis("多方", f"{label}連三季上升：{values[0]:.1f}% → {values[1]:.1f}% → {values[2]:.1f}%", ("gross_margin_pct",)))
            elif values[0] > values[1] > values[2]:
                theses.append(Thesis("空方", f"{label}連三季下降：{values[0]:.1f}% → {values[1]:.1f}% → {values[2]:.1f}%", ("gross_margin_pct",)))
    for key, noun in (("revenue_yoy_pct", "營收"), ("earnings_yoy_pct", "獲利")):
        metric = report.metric(key)
        if metric.status != "OK" or metric.value == 0:
            continue
        side = "多方" if metric.value > 0 else "空方"
        verb = "增加" if metric.value > 0 else "減少"
        theses.append(Thesis(side, f"{noun}較去年同期{verb} {abs(metric.value):.1f}%", (key,)))
    return tuple(theses)
