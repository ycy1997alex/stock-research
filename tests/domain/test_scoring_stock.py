"""個股短／中／長三期評分（ToDo §8.3、§9 Day 26 第 5 項）。

驗收句：**「15 檔都有分數，SPCX 的中期／長期回傳『資料不足』而不是硬算出來
的數字」**。後半句才是重點 —— 硬算得出一個數字比算不出來糟，因為它看起來
跟其他十四檔一模一樣，沒有人會發現它是空的。

三期的分界不是隨便切的，是**各自需要多少根 K 線**決定的：

    短期  20 根   MA5/MA20、RSI、布林
    中期  60 根   MA60、季線位置與動能
    長期 200 根   MA200、距 52 週高點

SPCX 2026-06-12 上市，只有 59 根 —— 剛好卡在中期門檻下面一根。這不是設計來
刁難它的，是它真的還沒有那麼多歷史。
"""
from __future__ import annotations

import pytest

from research.domain import scoring_stock as ss


def _rising(n: int, start: float = 100.0, step: float = 0.5) -> list[float]:
    return [start + step * i for i in range(n)]


def _falling(n: int, start: float = 300.0, step: float = 0.5) -> list[float]:
    return [start - step * i for i in range(n)]


# ---------------- 三期各自的資料門檻 ----------------

def test_full_history_scores_all_three_terms():
    s = ss.score_stock("2330.TW", _rising(244))
    assert s.short.score is not None
    assert s.mid.score is not None
    assert s.long.score is not None


def test_spcx_length_has_short_term_only():
    """SPCX 59 根：短期算得出來，中期與長期必須是資料不足。"""
    s = ss.score_stock("SPCX", _rising(59))
    assert s.short.score is not None
    assert s.mid.score is None
    assert s.long.score is None


def test_spcx_mid_and_long_say_why_rather_than_returning_zero():
    """回 None 而且附上原因 —— **不是 0 分**。0 分會被平均進去。"""
    s = ss.score_stock("SPCX", _rising(59))
    assert ss.INSUFFICIENT in s.mid.reason
    assert "59" in s.mid.reason      # 講出實際有幾根
    assert ss.INSUFFICIENT in s.long.reason


def test_insufficient_terms_are_excluded_from_the_overall_average():
    """資料不足的期別不進總平均，不然它會被當成 0 拉低整體。"""
    s = ss.score_stock("SPCX", _rising(59))
    assert s.overall is not None
    assert s.overall == pytest.approx(s.short.score)


def test_nothing_at_all_gives_no_overall():
    s = ss.score_stock("SPCX", _rising(5))
    assert s.overall is None
    assert s.short.score is None


# ---------------- 分數方向 ----------------

def test_downtrend_scores_lower_than_uptrend():
    up = ss.score_stock("2330.TW", _rising(244)).overall
    down = ss.score_stock("2330.TW", _falling(244)).overall
    assert up > down


def test_scores_stay_in_range():
    for closes in (_rising(244), _falling(244)):
        s = ss.score_stock("2330.TW", closes)
        for term in (s.short, s.mid, s.long):
            if term.score is not None:
                assert 0.0 <= term.score <= 100.0


# ---------------- 籌碼面第四維度 ----------------

def test_chips_dimension_uses_net_shares_relative_to_volume():
    """買賣超要除以成交量才有意義 —— 一萬張在台積電與在日月光不是同一件事。"""
    term = ss.score_chips_term(
        net_shares_series=[5_000_000] * 5,
        volume_shares_series=[100_000_000] * 5,
    )
    assert term.score is not None
    assert "%" in term.reason


def test_chips_dimension_is_insufficient_without_data():
    term = ss.score_chips_term(net_shares_series=[], volume_shares_series=[])
    assert term.score is None
    assert ss.INSUFFICIENT in term.reason


def test_thin_liquidity_symbols_are_flagged_not_silently_scored():
    """HNHPF 9/4 只成交 8,200 股 —— 量價與籌碼指標會失真（§10）。

    照算，但**必須掛上但書**，不能安靜地給一個看起來正常的數字。
    """
    s = ss.score_stock("HNHPF", _rising(244))
    assert any("薄流動性" in c for c in s.caveats)


def test_normal_symbols_have_no_liquidity_caveat():
    s = ss.score_stock("2330.TW", _rising(244))
    assert not any("薄流動性" in c for c in s.caveats)


def test_degraded_long_term_window_is_disclosed():
    """台股一年 243~244 根，不足 250 根時長期視窗會降級 —— 要講出來。"""
    s = ss.score_stock("2330.TW", _rising(210))
    assert any("降級" in c for c in s.caveats)
