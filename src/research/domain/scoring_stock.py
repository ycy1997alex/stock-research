"""Two directional stock scores and an independent activity axis.

All technical inputs are adjusted OHLCV. Local observations are scored outside
this module and can never alter the cross-market comparable score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from barometer.domain import indicators as ind

from research.domain import technical_stock

INSUFFICIENT = "資料不足"
MIN_SHORT = 20
MIN_MID = 60
MIN_LONG = 200
LOOKBACK_FULL = 250
CHIP_CONCENTRATION_PCT = 3.0
THIN_LIQUIDITY = ("HNHPF",)
TERM_WEIGHTS = (.30, .40, .30)


@dataclass(frozen=True, slots=True)
class IndicatorScore:
    name: str
    score: float | None
    weight: float
    detail: str


@dataclass(frozen=True, slots=True)
class TermScore:
    score: float | None
    reason: str
    parts: dict[str, str] = field(default_factory=dict)
    items: tuple[IndicatorScore, ...] = ()


@dataclass(frozen=True, slots=True)
class RiskContext:
    blowoff: bool = False
    below_falling_240: bool = False
    high_volatility: bool = False


@dataclass(frozen=True, slots=True)
class ScorePair:
    comparable_raw: float | None
    native_raw: float | None
    comparable: float | None
    native: float | None
    raw_gap: float | None
    overrides: tuple[str, ...] = ()
    local_note: str = ""


def _override(score: float, risk: RiskContext) -> tuple[float, tuple[str, ...]]:
    notes: list[str] = []
    if risk.blowoff:
        score = min(score, 10.0)
        notes.append("爆量長黑：分數封頂 +10")
    if risk.below_falling_240 and score > 40:
        score = min(score, 40.0)
        notes.append("年線下彎且價格在下：分數封頂 +40")
    if risk.high_volatility:
        score *= .7
        notes.append("年化波動超過 80%：分數乘 0.7")
    return score, tuple(notes)


def combine_scores(technical: float | None, local: float | None, weight: float,
                   risk: RiskContext | None = None) -> ScorePair:
    """Keep the exact raw identity; apply nonlinear risk rules last to both axes."""
    if not 0 <= weight <= 1:
        raise ValueError("native weight must be within [0, 1]")
    if technical is None:
        return ScorePair(None, None, None, None, None, local_note="技術面資料不足")
    risk = risk or RiskContext()
    effective = 0.0 if local is None else weight
    native_raw = (1 - effective) * technical + effective * (local if local is not None else 0)
    comparable, c_notes = _override(technical, risk)
    native, n_notes = _override(native_raw, risk)
    return ScorePair(technical, native_raw, comparable, native,
                     native_raw - technical, tuple(dict.fromkeys(c_notes + n_notes)),
                     "無本地資料" if local is None else "本地權重 0" if weight == 0 else "")


def to_stars(score: float | None) -> dict[str, object]:
    if score is None:
        return {"text": "資料不足", "filled": 0, "hollow": 0, "label": "資料不足"}
    if score >= 80:
        filled, hollow, label = 5, 0, "強力買進"
    elif score >= 60:
        filled, hollow, label = 4, 0, "買進"
    elif score >= 40:
        filled, hollow, label = 3, 0, "偏多"
    elif score >= 20:
        filled, hollow, label = 2, 0, "略偏多"
    elif score <= -80:
        filled, hollow, label = 0, 5, "強力賣出"
    elif score <= -60:
        filled, hollow, label = 0, 4, "賣出"
    elif score <= -40:
        filled, hollow, label = 0, 3, "偏空"
    elif score <= -20:
        filled, hollow, label = 0, 2, "略偏空"
    else:
        filled, hollow, label = 0, 0, "中性觀望"
    return {"text": "★" * filled + "☆" * hollow or "—", "filled": filled,
            "hollow": hollow, "label": label}


def _term(items: list[technical_stock.Item], label: str, n: int, minimum: int) -> TermScore:
    details = tuple(IndicatorScore(*row) for row in items)
    parts = {item.name: item.detail for item in details}
    if n < minimum:
        return TermScore(None, f"{INSUFFICIENT}：{label}需要 {minimum} 根，只有 {n} 根", parts, details)
    valid = [item for item in details if item.score is not None]
    total_weight = sum(item.weight for item in valid)
    if not total_weight:
        return TermScore(None, f"{INSUFFICIENT}：{label}指標全缺", parts, details)
    score = sum(item.score * item.weight for item in valid) / total_weight
    return TermScore(score, f"{label} {len(valid)}/{len(details)} 項", parts, details)


def _technical(short: TermScore, mid: TermScore, long: TermScore) -> float | None:
    present = [(term.score, weight) for term, weight in zip((short, mid, long), TERM_WEIGHTS)
               if term.score is not None]
    total = sum(weight for _, weight in present)
    return sum(score * weight for score, weight in present) / total if total else None


@dataclass(frozen=True, slots=True)
class StockScore:
    symbol: str
    short: TermScore
    mid: TermScore
    long: TermScore
    chips: TermScore | None = None
    caveats: list[str] = field(default_factory=list)
    pair: ScorePair | None = None
    strength: float | None = None
    local: float | None = None
    local_reasons: tuple[str, ...] = ()

    @property
    def technical(self) -> float | None:
        return _technical(self.short, self.mid, self.long)

    @property
    def comparable_raw(self) -> float | None:
        return self.pair.comparable_raw if self.pair else self.technical

    @property
    def native_raw(self) -> float | None:
        return self.pair.native_raw if self.pair else self.technical

    @property
    def comparable(self) -> float | None:
        return self.pair.comparable if self.pair else self.technical

    @property
    def native(self) -> float | None:
        return self.pair.native if self.pair else self.technical

    @property
    def raw_gap(self) -> float | None:
        return self.pair.raw_gap if self.pair else 0.0 if self.technical is not None else None

    @property
    def overrides(self) -> tuple[str, ...]:
        return self.pair.overrides if self.pair else ()

    @property
    def local_note(self) -> str:
        return self.pair.local_note if self.pair else "無本地資料"

    @property
    def overall(self) -> float | None:
        """The legacy single-series view remains the comparable score."""
        return self.comparable

    def to_dict(self) -> dict:
        def rounded(value: float | None) -> float | None:
            return round(value, 1) if value is not None else None
        return {
            "symbol": self.symbol, "overall": rounded(self.overall),
            "technical": rounded(self.technical),
            "comparable_raw": rounded(self.comparable_raw),
            "native_raw": rounded(self.native_raw),
            "comparable": rounded(self.comparable), "native": rounded(self.native),
            "strength": rounded(self.strength), "local": rounded(self.local),
            "raw_gap": rounded(self.raw_gap), "overrides": list(self.overrides),
            "local_note": self.local_note, "local_reasons": list(self.local_reasons),
            "short": _term_dict(self.short), "mid": _term_dict(self.mid),
            "long": _term_dict(self.long),
            "chips": _term_dict(self.chips) if self.chips else None,
            "caveats": list(self.caveats),
        }


def _term_dict(term: TermScore) -> dict:
    return {"score": round(term.score, 1) if term.score is not None else None,
            "reason": term.reason, "parts": dict(term.parts),
            "items": [{"name": item.name, "score": item.score,
                       "weight": item.weight, "detail": item.detail} for item in term.items]}


def score_chips_term(net_shares_series: list[float | None],
                     volume_shares_series: list[float | None]) -> TermScore:
    pairs = [(float(n), float(v)) for n, v in zip(net_shares_series, volume_shares_series)
             if n is not None and v is not None and v > 0]
    if not pairs:
        return TermScore(None, f"{INSUFFICIENT}：沒有買賣超或成交量資料")
    pct = sum(n for n, _ in pairs) / sum(v for _, v in pairs) * 100
    score = 100 if pct >= CHIP_CONCENTRATION_PCT else -100 if pct <= -CHIP_CONCENTRATION_PCT else 0
    return TermScore(score, f"近 {len(pairs)} 日三大法人買賣超佔成交量 {pct:+.2f}%",
                     {"threshold": f"±{CHIP_CONCENTRATION_PCT}%"})


def _risk(closes: list[float], opens: list[float] | None,
          volumes: list[float] | None) -> RiskContext:
    blowoff = False
    if opens is not None and volumes is not None and len(closes) >= 20:
        mean = sum(volumes[-20:]) / 20
        blowoff = (mean > 0 and volumes[-1] > 2.5 * mean
                   and closes[-1] / closes[-2] - 1 < -.04 and closes[-1] < opens[-1])
    ma240s = ind.moving_average(closes, 240)
    ma240 = ma240s[-1] if ma240s else None
    slope = ind.ma_slope(ma240s, 20)
    below = ma240 is not None and slope is not None and closes[-1] < ma240 and slope < 0
    vol = ind.annualised_volatility(closes[-21:]) if len(closes) >= 21 else None
    return RiskContext(blowoff, below, vol is not None and vol > .8)


def score_stock(symbol: str, closes: list[float | None],
                net_shares_series: list[float | None] | None = None,
                volume_shares_series: list[float | None] | None = None,
                *, opens: list[float | None] | None = None,
                highs: list[float | None] | None = None,
                lows: list[float | None] | None = None,
                volumes: list[float | None] | None = None,
                local_score: float | None = None, local_reasons: tuple[str, ...] = (),
                native_weight: float | None = None) -> StockScore:
    from research import config

    n = len(closes)
    if any(series is not None and len(series) != n for series in (opens, highs, lows, volumes)):
        raise ValueError("OHLCV lengths differ")
    if any(value is None for value in closes):
        empty = TermScore(None, f"{INSUFFICIENT}：收盤序列有缺值")
        return StockScore(symbol, empty, empty, empty)
    values = [float(value) for value in closes]
    # An incomplete OHLCV field cannot support that field's indicators. Keep
    # close-only indicators available and let their weights renormalize.
    raw_series = (opens, highs, lows, volumes)
    opens, highs, lows, volumes = (
        [float(value) for value in series] if series is not None
        and all(value is not None for value in series) else None
        for series in raw_series
    )
    thin = symbol in config.THIN_LIQUIDITY or symbol in THIN_LIQUIDITY
    short = _term(technical_stock.short_items(values, highs, lows, volumes, thin=thin), "短期", n, MIN_SHORT)
    mid = _term(technical_stock.mid_items(values, highs, lows, volumes, thin=thin), "中期", n, MIN_MID)
    long = _term(technical_stock.long_items(values, highs, lows), "長期", n, MIN_LONG)
    caveats: list[str] = []
    for field_name, series, cleaned in zip(("開盤", "最高", "最低", "成交量"),
                                          raw_series, (opens, highs, lows, volumes)):
        if series is not None and cleaned is None:
            caveats.append(f"{field_name}序列有缺值；相關指標不適用")
    if thin:
        caveats.append("薄流動性：量價配合與 OBV 不適用")
    if MIN_LONG <= n < LOOKBACK_FULL:
        caveats.append(f"長期視窗已降級：只有 {n} 根，以此代替 52 週")
    if n < MIN_LONG:
        caveats.append(f"歷史只有 {n} 根，長期評分不成立")
    chips = None
    if net_shares_series is not None and volume_shares_series is not None:
        chips = score_chips_term(net_shares_series, volume_shares_series)
    if local_score is None and chips is not None:
        local_score = chips.score
    if native_weight is None:
        native_weight = config.NATIVE_WEIGHT_TW if symbol.endswith((".TW", ".TWO")) else config.NATIVE_WEIGHT_US
    technical = _technical(short, mid, long)
    pair = combine_scores(technical, local_score, native_weight,
                          _risk(values, opens, volumes) if values else None)
    item_scores = [item.score for term in (short, mid, long) for item in term.items]
    strength = technical_stock.strength_axis(values, highs, lows, volumes, item_scores) if values else None
    return StockScore(symbol, short, mid, long, chips, caveats, pair, strength,
                      local_score, local_reasons)
