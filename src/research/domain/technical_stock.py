"""Directional stock indicator rules. All inputs are adjusted OHLCV lists."""
from __future__ import annotations

from barometer.domain import indicators as ind

Item = tuple[str, float | None, float, str]


def _clip(value: float) -> float:
    return max(-100.0, min(100.0, value))


def _last(values: list[float | None]) -> float | None:
    return values[-1] if values else None


def _item(name: str, score: float | None, weight: float, reason: str) -> Item:
    return name, score, weight, reason


def short_items(closes: list[float], highs: list[float] | None,
                lows: list[float] | None, volumes: list[float] | None,
                *, thin: bool = False) -> list[Item]:
    items: list[Item] = []
    k = d = None
    if highs is not None and lows is not None:
        ks, ds = ind.stochastic_kd(highs, lows, closes)
        k, d = _last(ks), _last(ds)
    if k is None or d is None:
        items.append(_item("KD(9,3,3)", None, .25, "資料不足：需要高低價及 9 根日 K"))
    else:
        gc = ind.crossed_within(ks, ds, 3, "up")
        dc = ind.crossed_within(ks, ds, 3, "down")
        if gc and k < 30:
            score, detail = 100, "低檔黃金交叉"
        elif gc and k < 50:
            score, detail = 70, "中低檔黃金交叉"
        elif dc and k > 70:
            score, detail = -100, "高檔死亡交叉"
        elif dc:
            score, detail = -70, "死亡交叉"
        elif k > d and k >= 80:
            score, detail = 40, "高檔鈍化，多方但慎追"
        elif k > d:
            score, detail = 50, "K 在 D 上方"
        elif k < d and k <= 20:
            score, detail = -40, "低檔鈍化"
        elif k < d:
            score, detail = -50, "K 在 D 下方"
        else:
            score, detail = 0, "K 與 D 相等"
        items.append(_item("KD(9,3,3)", score, .25, f"{detail}；K={k:.1f}、D={d:.1f}"))

    r = _last(ind.rsi(closes, 14))
    if r is None:
        items.append(_item("RSI(14)", None, .20, "資料不足：需要 15 根日 K"))
    else:
        score = (r - 50) * 3 if 30 <= r <= 70 else max(60 - (r - 70) * 4, 0) if r > 70 else min(-60 + (30 - r) * 4, 0)
        items.append(_item("RSI(14)", _clip(score), .20, f"RSI={r:.1f}"))

    _, _, hist = ind.macd(closes)
    h = _last(hist)
    if h is None:
        items.append(_item("MACD 柱動能", None, .20, "資料不足：需要 MACD 形成期"))
    elif ind.crossed_within(hist, [0.0] * len(hist), 3, "up"):
        items.append(_item("MACD 柱動能", 100, .20, "柱狀圖近三日翻正"))
    elif ind.crossed_within(hist, [0.0] * len(hist), 3, "down"):
        items.append(_item("MACD 柱動能", -100, .20, "柱狀圖近三日翻負"))
    else:
        base = 50 if h > 0 else -50 if h < 0 else 0
        recent = hist[-3:]
        if len(recent) == 3 and all(x is not None for x in recent):
            magnitude = list(map(abs, recent))
            if magnitude[0] > magnitude[1] > magnitude[2]:
                base *= .4
                detail = "柱體連續收縮"
            elif magnitude[0] < magnitude[1] < magnitude[2]:
                base = _clip(base * 1.6)
                detail = "柱體連續擴張"
            else:
                detail = "柱體維持方向"
        else:
            detail = "柱體維持方向"
        items.append(_item("MACD 柱動能", base, .20, f"{detail}；柱值 {h:+.3f}"))

    pb = ind.bollinger_position(closes)
    if pb is None:
        items.append(_item("布林 %B", None, .15, "資料不足：需要 20 根日 K"))
    else:
        score = 30 if pb > 1 else 60 if pb >= .8 else (pb - .5) * 200 if pb >= .2 else -60 if pb >= 0 else -30
        items.append(_item("布林 %B", score, .15, f"%B={pb:.2f}"))

    ma5 = _last(ind.moving_average(closes, 5))
    ma10 = _last(ind.moving_average(closes, 10))
    if ma5 is None or ma10 is None:
        items.append(_item("5/10MA 排列", None, .10, "資料不足：需要 10 根日 K"))
    else:
        c = closes[-1]
        score = 100 if c > ma5 > ma10 else -100 if c < ma5 < ma10 else 40 if c > ma10 else -40 if c < ma10 else 0
        items.append(_item("5/10MA 排列", score, .10, f"收盤 {c:.2f}；MA5 {ma5:.2f}；MA10 {ma10:.2f}"))

    if thin:
        items.append(_item("量價配合", None, .10, "薄流動性：量能不適用"))
    elif volumes is None or len(volumes) < 20:
        items.append(_item("量價配合", None, .10, "資料不足：需要 20 根成交量"))
    else:
        base = sum(volumes[-20:]) / 20
        vr = sum(volumes[-5:]) / 5 / base if base > 0 else None
        if vr is None:
            items.append(_item("量價配合", None, .10, "資料不足：均量為零"))
        else:
            change = closes[-1] - closes[-6]
            score = (100 if change > 0 else -80 if change < 0 else 0) if vr >= 1.5 else (20 if change > 0 else -20 if change < 0 else 0) if vr <= .7 else 0
            direction = "漲" if change > 0 else "跌" if change < 0 else "平"
            items.append(_item("量價配合", score, .10, f"五日均量／二十日均量 {vr:.2f}；近五日價{direction}"))
    return items


def mid_items(closes: list[float], highs: list[float] | None,
              lows: list[float] | None, volumes: list[float] | None,
              *, thin: bool = False) -> list[Item]:
    items: list[Item] = []
    ma20s, ma60s = ind.moving_average(closes, 20), ind.moving_average(closes, 60)
    ma20, ma60 = _last(ma20s), _last(ma60s)
    if ma20 is None or ma60 is None:
        items.append(_item("20/60MA 排列", None, .30, "資料不足：需要 60 根日 K"))
    else:
        slope = ind.ma_slope(ma60s, 20)
        c = closes[-1]
        if c > ma20 > ma60 and slope is not None and slope > 0:
            score, detail = 100, "多頭排列且季線上揚"
        elif c > ma20 > ma60:
            score, detail = 70, "多頭排列，季線斜率不足或走平"
        elif c > ma60 and ma20 > ma60:
            score, detail = 40, "站上季線，月線在季線上"
        elif c > ma60:
            score, detail = 10, "僅站上季線"
        elif c < ma20 < ma60 and (slope is None or slope < 0):
            score, detail = -100, "空頭排列且季線下彎"
        elif c < ma20 < ma60:
            score, detail = -70, "空頭排列"
        elif c < ma60:
            score, detail = -40, "跌破季線"
        else:
            score, detail = 0, "均線糾結"
        items.append(_item("20/60MA 排列", score, .30, detail))

    dif, signal, _ = ind.macd(closes)
    dv, sv = _last(dif), _last(signal)
    if dv is None or sv is None:
        items.append(_item("MACD 位階", None, .25, "資料不足：需要 MACD 形成期"))
    else:
        score = 0 if dv == sv == 0 else 100 if dv > 0 and dv > sv else 40 if dv > 0 else -20 if dv > sv else -100
        items.append(_item("MACD 位階", score, .25, f"DIF {dv:+.3f}、訊號線 {sv:+.3f}"))

    if highs is None or lows is None:
        items.append(_item("DMI/ADX(14)", None, .20, "資料不足：需要高低價"))
    else:
        plus, minus, adxs = ind.dmi_adx(highs, lows, closes)
        p, m, a = _last(plus), _last(minus), _last(adxs)
        if p is None or m is None or a is None:
            items.append(_item("DMI/ADX(14)", None, .20, "資料不足：需要 ADX 形成期"))
        else:
            direction = 1 if p > m else -1 if p < m else 0
            magnitude = 100 if a >= 40 else 75 if a >= 25 else 40 if a >= 20 else 15
            items.append(_item("DMI/ADX(14)", direction * magnitude, .20,
                               f"+DI {p:.1f}、-DI {m:.1f}、ADX {a:.1f}"))

    change = _last(ind.roc(closes, 60))
    items.append(_item("ROC(60)", _clip(change * 4) if change is not None else None, .15,
                       f"60 日報酬 {change:+.1f}%" if change is not None else "資料不足：需要 61 根日 K"))

    if thin:
        items.append(_item("OBV", None, .10, "薄流動性：OBV 不適用"))
    elif volumes is None:
        items.append(_item("OBV", None, .10, "資料不足：需要成交量"))
    else:
        series = ind.obv(closes, volumes)
        ma = _last(ind.moving_average(series, 20))
        value = _last(series)
        if ma is None or value is None:
            items.append(_item("OBV", None, .10, "資料不足：需要 20 根有效成交量"))
        else:
            recent = [v for v in series[-60:] if v is not None]
            score = 0 if value == ma else 100 if value > ma and value >= max(recent) else 50 if value > ma else -100 if value <= min(recent) else -50
            items.append(_item("OBV", score, .10, f"OBV {value:,.0f}；二十日均線 {ma:,.0f}"))
    return items


def long_items(closes: list[float], highs: list[float] | None,
               lows: list[float] | None) -> list[Item]:
    items: list[Item] = []
    ma60s, ma240s = ind.moving_average(closes, 60), ind.moving_average(closes, 240)
    ma240 = _last(ma240s)
    slope = ind.ma_slope(ma240s, 20)
    if ma240 is None:
        items.append(_item("240MA 年線", None, .35, "資料不足：需要 240 根日 K"))
        items.append(_item("60/240MA 交叉", None, .25, "資料不足：需要 240 根日 K"))
    else:
        c = closes[-1]
        deviation = (c / ma240 - 1) * 100
        if c == ma240:
            score = 0
        elif c > ma240 and slope is not None and slope > 0:
            score = 50 if deviation > 40 else 100
        elif c > ma240:
            score = 50
        elif slope is None or slope < 0:
            score = -50 if deviation < -40 else -100
        else:
            score = -50
        items.append(_item("240MA 年線", score, .35,
                           f"乖離 {deviation:+.1f}%；二十日斜率 {slope:+.1f}%" if slope is not None else f"乖離 {deviation:+.1f}%；斜率資料不足"))
        ma60 = _last(ma60s)
        golden = ma60 > ma240
        recent = ind.crossed_within(ma60s, ma240s, 60, "up" if golden else "down")
        cross_score = 0 if ma60 == ma240 else 100 if golden and recent else 70 if golden else -100 if recent else -70
        items.append(_item("60/240MA 交叉", cross_score, .25,
                           "季線與年線相等" if ma60 == ma240 else "季線在年線上" if golden else "季線在年線下"))

    if highs is None or lows is None or len(closes) < 120:
        items.append(_item("52 週位置", None, .20, "資料不足：需要至少 120 根高低價"))
    else:
        hi, lo = max(highs[-240:]), min(lows[-240:])
        position = (closes[-1] - lo) / (hi - lo) if hi > lo else None
        if position is None:
            items.append(_item("52 週位置", None, .20, "資料不足：高低價區間為零"))
        else:
            score = 70 if position >= .95 else 100 if position >= .7 else 40 if position >= .55 else 0 if position > .45 else -40 if position >= .3 else -100 if position >= .05 else -70
            items.append(_item("52 週位置", score, .20, f"區間位置 {position:.0%}"))
    change = _last(ind.roc(closes, 120))
    items.append(_item("ROC(120)", _clip(change * 2.5) if change is not None else None, .20,
                       f"120 日報酬 {change:+.1f}%" if change is not None else "資料不足：需要 121 根日 K"))
    return items


def strength_axis(closes: list[float], highs: list[float] | None,
                  lows: list[float] | None, volumes: list[float] | None,
                  scores: list[float | None]) -> float | None:
    if highs is None or lows is None or volumes is None or len(volumes) < 20:
        return None
    _, _, adxs = ind.dmi_adx(highs, lows, closes)
    adx = _last(adxs)
    mean20 = sum(volumes[-20:]) / 20
    if adx is None or mean20 <= 0:
        return None
    relative = sum(volumes[-5:]) / 5 / mean20
    directions = [1 if score > 0 else -1 if score < 0 else 0 for score in scores if score is not None]
    if not directions:
        return None
    consistency = abs(sum(directions)) / len(directions)
    return max(0.0, min(100.0, .4 * min(adx / 50, 1) * 100
                         + .3 * min(relative / 3, 1) * 100 + .3 * consistency * 100))
