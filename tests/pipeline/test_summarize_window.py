"""`summarize_window` 不滿五天時要**大聲失敗**（2026-09-08）。

跟 `../market-barometer/tests/pipeline/test_summarize_window.py` 是同一條規格，
因為兩支管線是同一個寫法。這一側更容易撞到：**SPCX 2026-06-12 才上市**，
而 `last_n_sessions` 的規則是「不足 n 天就給有幾天算幾天 —— 不補、不外推」。

桌面 Presenter 那一側刻意相反（回 None、標「資料不足（N/5 天）」），
差別在「有沒有人正在看著」：畫面不能整頁掛掉，批次可以也應該。
"""
from __future__ import annotations

import datetime as dt

import pytest

from research.domain import scoring_stock
from research.pipeline import run_stock_scores


def _term(score: float | None) -> scoring_stock.TermScore:
    return scoring_stock.TermScore(score=score, reason="")


def _scored(symbol: str, n: int) -> list[tuple[dt.date, scoring_stock.StockScore]]:
    days = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)][:n]
    return [
        (
            day,
            scoring_stock.StockScore(
                symbol=symbol,
                short=_term(80.0), mid=_term(80.0), long=_term(80.0),
            ),
        )
        for day in days
    ]


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_short_window_raises(n):
    with pytest.raises(ValueError):
        run_stock_scores.summarize_window(_scored("2330.TW", n))


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_error_names_the_symbol(n):
    """15 檔跑到一半炸掉，訊息一定要說出是哪一檔。"""
    with pytest.raises(ValueError, match="SPCX"):
        run_stock_scores.summarize_window(_scored("SPCX", n))


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_error_states_how_many_days(n):
    with pytest.raises(ValueError) as exc:
        run_stock_scores.summarize_window(_scored("HNHPF", n))
    assert f"{n}/5" in str(exc.value)


def test_error_lists_the_dates():
    with pytest.raises(ValueError) as exc:
        run_stock_scores.summarize_window(_scored("SPCX", 3))
    msg = str(exc.value)
    assert "2026-09-01" in msg and "2026-09-03" in msg


def test_empty_window_raises_too():
    """一天都沒有的時候不能死在 IndexError —— 那句話同樣看不懂。"""
    with pytest.raises(ValueError, match="0/5"):
        run_stock_scores.summarize_window([])


def test_exactly_five_days_still_works():
    summary = run_stock_scores.summarize_window(_scored("2330.TW", 5))
    assert summary["weighted_average"] == pytest.approx(80.0)
    assert summary["simple_average"] == pytest.approx(80.0)
    assert len(summary["dates"]) == 5
    assert len(summary["changes"]) == 5
