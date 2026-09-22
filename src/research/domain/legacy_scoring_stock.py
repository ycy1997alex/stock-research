"""個股短／中／長三期評分 + 籌碼面第四維度（ToDo §8.3、§9 Day 26 第 5 項）。

純函式、零 I/O。指標本身沿用 market-barometer 的 `domain/indicators.py` ——
兩個 repo 共用同一組計算，個股這邊只換一套組法。重寫一份 RSI 只會多出一個
會跟另一份不一致的地方。

**三期的分界是資料量決定的，不是拍腦袋切的：**

    短期  ≥ 20 根   MA5 對 MA20、RSI(14)、布林通道位置
    中期  ≥ 60 根   收盤對 MA60、季線動能
    長期  ≥ 200 根  收盤對 MA200、距 52 週高點回撤

**算不出來就回 None，附上原因，絕不回 0。** SPCX 2026-06-12 才上市，只有 59
根日 K —— 中期與長期硬算得出來的話會長得跟其他十四檔一模一樣，沒有人會發現
那格是空的。0 分還會被平均進總分裡，把一個「不知道」變成一個「很糟」。

**籌碼面第四維度**用的是三大法人買賣超**相對成交量**的比例，不是絕對股數。
一萬張在台積電與在日月光不是同一件事。

**權重是自己硬定的一把尺**（§8.3）—— 每個門檻旁邊都留了為什麼是這個數字。
不是因為它有依據，是因為半年後要改的時候得知道當初在想什麼。

⚠️ 這個 repo 的內容只有自己看。與 market-barometer 不同，這裡**可以**把分數
翻成動作（§2.1）—— 但那仍然是一條規則的輸出，不是任何人的推薦。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from barometer.domain.indicators import (
    bollinger_position,
    drawdown_from_high,
    moving_average,
    rsi,
)

INSUFFICIENT = "資料不足"

# 三期各自要幾根 —— 分界就是「這個期別的指標需要多少歷史」
MIN_SHORT = 20
MIN_MID = 60
MIN_LONG = 200

# 長期回看視窗：滿 250 根才是完整的 52 週。台股一年只有 243~244 根，
# 所以不足額時降級成「這段序列以來」並掛但書 —— 跟 barometer 那側同一條規則。
LOOKBACK_FULL = 250

RSI_HIGH = 70.0
RSI_LOW = 30.0

# 籌碼面：三大法人買賣超佔成交量的比例，超過這個就算「買賣超集中」
CHIP_CONCENTRATION_PCT = 3.0

# §10：薄流動性標的，量價與籌碼指標會失真（HNHPF 9/4 只成交 8,200 股）
THIN_LIQUIDITY = ("HNHPF",)


@dataclass(frozen=True, slots=True)
class TermScore:
    """一個期別的分數。`score is None` 就是算不出來，`reason` 說為什麼。"""

    score: float | None
    reason: str
    parts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StockScore:
    symbol: str
    short: TermScore
    mid: TermScore
    long: TermScore
    chips: TermScore | None = None
    caveats: list[str] = field(default_factory=list)

    @property
    def overall(self) -> float | None:
        """三期（有籌碼面時四維）的平均。

        **算不出來的期別不進分母** —— 不然「不知道」會被當成 0 拉低整體。
        """
        terms = [self.short, self.mid, self.long]
        if self.chips is not None:
            terms.append(self.chips)
        got = [t.score for t in terms if t.score is not None]
        return sum(got) / len(got) if got else None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "overall": round(self.overall, 1) if self.overall is not None else None,
            "short": _term_dict(self.short),
            "mid": _term_dict(self.mid),
            "long": _term_dict(self.long),
            "chips": _term_dict(self.chips) if self.chips else None,
            "caveats": list(self.caveats),
        }


def _term_dict(t: TermScore) -> dict:
    return {
        "score": round(t.score, 1) if t.score is not None else None,
        "reason": t.reason,
        "parts": dict(t.parts),
    }


def _clean(series: list[float | None]) -> list[float]:
    return [float(x) for x in series if x is not None]


def _pct_of_checks(passed: list[bool]) -> float:
    return 100.0 * sum(passed) / len(passed)


# ---------------- 短期 ----------------

def score_short(closes: list[float | None]) -> TermScore:
    v = _clean(closes)
    if len(v) < MIN_SHORT:
        return TermScore(None, f"{INSUFFICIENT}：短期需要 {MIN_SHORT} 根，只有 {len(v)} 根")

    ma5 = moving_average(v, 5)[-1]
    ma20 = moving_average(v, 20)[-1]
    r = rsi(v, 14)[-1] if len(v) > 14 else None
    pos = bollinger_position(v, 20)

    checks: list[bool] = []
    parts: dict[str, str] = {}

    if ma5 is not None and ma20 is not None:
        checks.append(ma5 > ma20)
        parts["ma5_vs_ma20"] = f"MA5 {ma5:,.2f} / MA20 {ma20:,.2f}"
    if r is not None:
        checks.append(RSI_LOW < r < RSI_HIGH)
        parts["rsi"] = f"RSI(14) {r:.1f}"
    if pos is not None:
        checks.append(0.0 <= pos <= 1.0)
        parts["bollinger"] = f"通道位置 {pos:.2f}"

    if not checks:
        return TermScore(None, f"{INSUFFICIENT}：短期指標都算不出來", parts)
    return TermScore(_pct_of_checks(checks), f"短期 {len(checks)} 項", parts)


# ---------------- 中期 ----------------

def score_mid(closes: list[float | None]) -> TermScore:
    v = _clean(closes)
    if len(v) < MIN_MID:
        return TermScore(None, f"{INSUFFICIENT}：中期需要 {MIN_MID} 根，只有 {len(v)} 根")

    ma60 = moving_average(v, 60)[-1]
    checks: list[bool] = []
    parts: dict[str, str] = {}

    if ma60 is not None:
        checks.append(v[-1] > ma60)
        parts["close_vs_ma60"] = f"收盤 {v[-1]:,.2f} / MA60 {ma60:,.2f}"
        # 季線動能：MA60 自己在往上還是往下
        ma60_prev = moving_average(v[:-20], 60)[-1] if len(v) > 80 else None
        if ma60_prev is not None:
            checks.append(ma60 > ma60_prev)
            parts["ma60_slope"] = f"MA60 二十日前 {ma60_prev:,.2f} → {ma60:,.2f}"

    if not checks:
        return TermScore(None, f"{INSUFFICIENT}：中期指標都算不出來", parts)
    return TermScore(_pct_of_checks(checks), f"中期 {len(checks)} 項", parts)


# ---------------- 長期 ----------------

def score_long(closes: list[float | None]) -> TermScore:
    v = _clean(closes)
    if len(v) < MIN_LONG:
        return TermScore(None, f"{INSUFFICIENT}：長期需要 {MIN_LONG} 根，只有 {len(v)} 根")

    ma200 = moving_average(v, 200)[-1]
    window = v[-LOOKBACK_FULL:]
    dd = drawdown_from_high(window)

    checks: list[bool] = []
    parts: dict[str, str] = {}

    if ma200 is not None:
        checks.append(v[-1] > ma200)
        parts["close_vs_ma200"] = f"收盤 {v[-1]:,.2f} / MA200 {ma200:,.2f}"
    if dd is not None:
        checks.append(dd > -0.20)
        label = "52 週" if len(window) >= LOOKBACK_FULL else f"{len(window)} 個交易日"
        parts["drawdown"] = f"距{label}高點 {dd * 100:.1f}%"

    if not checks:
        return TermScore(None, f"{INSUFFICIENT}：長期指標都算不出來", parts)
    return TermScore(_pct_of_checks(checks), f"長期 {len(checks)} 項", parts)


# ---------------- 籌碼面第四維度 ----------------

def score_chips_term(
    net_shares_series: list[float | None],
    volume_shares_series: list[float | None],
) -> TermScore:
    """三大法人買賣超**相對成交量**的比例。

    用比例不用絕對股數：一萬張在台積電與在日月光不是同一件事。兩條序列都是
    「股」—— T86 的買賣超是股、price_daily 的量也是股，這裡不做任何換算。
    """
    net = _clean(net_shares_series)
    vol = _clean(volume_shares_series)
    n = min(len(net), len(vol))
    if n == 0:
        return TermScore(None, f"{INSUFFICIENT}：沒有買賣超或成交量資料")

    total_net = sum(net[-n:])
    total_vol = sum(vol[-n:])
    if total_vol <= 0:
        return TermScore(None, f"{INSUFFICIENT}：成交量為零，比例算不出來")

    pct = total_net / total_vol * 100.0
    # 淨買超集中算正面、淨賣超集中算負面，中間算中性 —— 一樣只分三檔，
    # 不去編一個連續的「強度」出來（跟 barometer 那側同一個取捨）
    if pct >= CHIP_CONCENTRATION_PCT:
        score = 100.0
    elif pct <= -CHIP_CONCENTRATION_PCT:
        score = 0.0
    else:
        score = 50.0
    return TermScore(
        score,
        f"近 {n} 日三大法人買賣超佔成交量 {pct:+.2f}%",
        {"threshold": f"±{CHIP_CONCENTRATION_PCT}%"},
    )


# ---------------- 組起來 ----------------

def score_stock(
    symbol: str,
    closes: list[float | None],
    net_shares_series: list[float | None] | None = None,
    volume_shares_series: list[float | None] | None = None,
) -> StockScore:
    """一檔個股的三期（有籌碼資料時四維）評分。

    籌碼資料是選配 —— 美股與 ADR 沒有台灣的三大法人資料，那一維就不存在，
    **不是 0 分**。
    """
    v = _clean(closes)
    caveats: list[str] = []

    if symbol in THIN_LIQUIDITY:
        caveats.append(
            "薄流動性：成交量極小，量價與籌碼指標會失真，分數只能當粗略參考（§10）"
        )
    if MIN_LONG <= len(v) < LOOKBACK_FULL:
        caveats.append(
            f"長期視窗已降級：只有 {len(v)} 根，以此代替 52 週"
        )
    if len(v) < MIN_LONG:
        caveats.append(f"歷史只有 {len(v)} 根，長期評分不成立")

    chips = None
    if net_shares_series is not None and volume_shares_series is not None:
        chips = score_chips_term(net_shares_series, volume_shares_series)

    return StockScore(
        symbol=symbol,
        short=score_short(closes),
        mid=score_mid(closes),
        long=score_long(closes),
        chips=chips,
        caveats=caveats,
    )
