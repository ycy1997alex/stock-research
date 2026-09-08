"""個股桌面儀表板 Presenter 的測試（ToDo §1.1 第 22 條、§9 Day 27 第 8 項）。

**先寫這一份，再寫實作**（§3.3）。

驗收句就是規格：
  1. 開視窗與切分頁**一次網路都不打** —— 只讀 score_history
  2. 「資料不足」顯示成字串，**不是 0 分**
  3. 美股沒有籌碼那一維時，那一維**整欄不出現**（不是 0）

第 2、3 點是同一件事的兩面：`subscores` 裡**缺 key** 代表算不出來。
硬把它當 0 的話，畫面上會多出一個看起來很正常、實際上是憑空捏造的分數。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.ports import ScoreRecord
from research import config as rc

from research.app.presenters.dashboard import SCOPE, TABS, StockPresenter


class FakeScores:
    """只實作 ScoreHistoryRepository 用得到的那一半。

    **任何打網路的嘗試都會炸** —— 這正是「開視窗不打網路」的驗收方式：
    不是去數請求數，而是讓網路在測試裡根本不存在。
    """

    def __init__(self, records: dict[tuple[str, str], list[ScoreRecord]] | None = None):
        self._records = records or {}
        self.calls: list[tuple[str, str]] = []

    def get_scores(self, scope: str, symbol: str) -> list[ScoreRecord]:
        self.calls.append((scope, symbol))
        return self._records.get((scope, symbol), [])

    def put_score(self, *a, **k):  # pragma: no cover - Port 要求，測試用不到
        raise AssertionError("Presenter 不該寫入分數")


def _rec(symbol: str, day: str, score: float, subs: dict[str, float]) -> ScoreRecord:
    return ScoreRecord(
        scope=SCOPE,
        symbol=symbol,
        as_of=dt.date.fromisoformat(day),
        score=score,
        subscores=subs,
        price_version="v1",
    )


FULL = {"short": 80.0, "mid": 70.0, "long": 60.0}


# ---------------- 分頁組成 ----------------

def test_two_tabs_only():
    """兩個分頁：台股權值股 / 美股權值股。網頁那側也是這兩個。"""
    assert list(TABS) == ["tw", "us"]


def test_tw_tab_holds_the_five_tw_stocks():
    assert TABS["tw"] == rc.TW_STOCKS
    assert len(TABS["tw"]) == 5


def test_us_tab_holds_us_stocks_and_adrs():
    """美股分頁含 7 檔美股 + 3 檔 ADR = 10 檔。"""
    assert TABS["us"] == rc.US_STOCKS + rc.ADRS
    assert len(TABS["us"]) == 10


# ---------------- 驗收 1：只讀快取，不打網路 ----------------

def test_load_reads_history_only():
    """load() 只呼叫 get_scores，不做別的。"""
    repo = FakeScores()
    rows = StockPresenter(repo).load("tw")

    assert len(rows) == 5
    assert repo.calls == [(SCOPE, s) for s in rc.TW_STOCKS]


def test_presenter_needs_no_refresher():
    """Presenter 不注入任何會打網路的東西也要能完整運作。"""
    rows = StockPresenter(FakeScores()).load("us")
    assert len(rows) == 10


def test_no_history_says_not_scored_yet():
    rows = StockPresenter(FakeScores()).load("tw")
    assert rows[0].value is None
    assert "尚未評分" in rows[0].note


# ---------------- 驗收 2：「資料不足」是字串，不是 0 ----------------

def test_missing_term_renders_as_insufficient_not_zero():
    """SPCX 只有 59 根日 K：中期與長期算不出來。

    `subscores` 裡沒有 mid / long 這兩個 key，畫面上要寫「資料不足」。
    """
    repo = FakeScores({
        (SCOPE, "SPCX"): [_rec("SPCX", "2026-09-04", 80.0, {"short": 80.0})],
    })
    row = next(r for r in StockPresenter(repo).load("us") if r.key == "SPCX")

    assert "中期 資料不足" in row.note
    assert "長期 資料不足" in row.note
    assert "中期 0" not in row.note
    assert "長期 0" not in row.note


def test_insufficient_term_is_not_averaged_into_the_total():
    """算不出來的那一維不得被當成 0 拉低總分。

    總分是管線算好寫進去的 `score`，Presenter 原樣顯示、不重算 ——
    重算一次的話，桌面上的數字就可能跟網頁上的對不起來。
    """
    repo = FakeScores({
        (SCOPE, "SPCX"): [_rec("SPCX", "2026-09-04", 80.0, {"short": 80.0})],
    })
    row = next(r for r in StockPresenter(repo).load("us") if r.key == "SPCX")

    assert row.value == "80.0"


# ---------------- 驗收 3：籌碼那一維不存在時整欄不出現 ----------------

def test_tw_stock_shows_chips_dimension():
    repo = FakeScores({
        (SCOPE, "2330.TW"): [
            _rec("2330.TW", "2026-09-04", 75.0, {**FULL, "chips": 65.0}),
        ],
    })
    row = next(r for r in StockPresenter(repo).load("tw") if r.key == "2330.TW")
    assert "籌碼 65" in row.note


def test_us_stock_omits_chips_dimension_entirely():
    """美股沒有台灣的三大法人資料 —— 那一維是「不存在」，不是 0。"""
    repo = FakeScores({
        (SCOPE, "NVDA"): [_rec("NVDA", "2026-09-04", 75.0, FULL)],
    })
    row = next(r for r in StockPresenter(repo).load("us") if r.key == "NVDA")

    assert "籌碼" not in row.note


# ---------------- 其他規格 ----------------

def test_thin_liquidity_carries_a_caveat():
    """HNHPF 零缺值但薄流動性：照算，但必須掛但書。"""
    repo = FakeScores({
        (SCOPE, "HNHPF"): [_rec("HNHPF", "2026-09-04", 55.0, FULL)],
    })
    row = next(r for r in StockPresenter(repo).load("us") if r.key == "HNHPF")

    assert "薄流動性" in row.note


def test_label_carries_the_chinese_name():
    repo = FakeScores({
        (SCOPE, "2330.TW"): [_rec("2330.TW", "2026-09-04", 75.0, FULL)],
    })
    row = next(r for r in StockPresenter(repo).load("tw") if r.key == "2330.TW")

    assert "台積電" in row.label


def test_five_day_weighted_average_uses_the_shared_weights():
    """五日加權用 §8.1 的同一組權重（10/15/20/25/30），不另寫一份。"""
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
    repo = FakeScores({
        (SCOPE, "AAPL"): [_rec("AAPL", d, 50.0, FULL) for d in days],
    })
    row = next(r for r in StockPresenter(repo).load("us") if r.key == "AAPL")

    # 五天都是 50，任何一組權重加權後都還是 50
    assert "五日加權 50.0" in row.note


def test_data_date_comes_from_the_latest_record():
    repo = FakeScores({
        (SCOPE, "MSFT"): [
            _rec("MSFT", "2026-09-03", 60.0, FULL),
            _rec("MSFT", "2026-09-04", 61.0, FULL),
        ],
    })
    row = next(r for r in StockPresenter(repo).load("us") if r.key == "MSFT")

    assert row.data_date == "2026-09-04"


# ---------------- 狀態列 ----------------

def test_status_counts_symbols_not_a_single_timestamp():
    """**不是**一行「最後更新：…」。

    15 檔的資料日期不見得同一天（美股 9/7 勞動節休市，台股照常），
    印一個時間戳等於宣稱它們都是那天的。
    """
    repo = FakeScores({
        (SCOPE, "2330.TW"): [_rec("2330.TW", "2026-09-04", 75.0, FULL)],
        (SCOPE, "NVDA"): [_rec("NVDA", "2026-09-03", 70.0, FULL)],
    })
    text = StockPresenter(repo).status()

    assert "2026-09-04" in text and "2026-09-03" in text
    assert "最後更新" not in text


def test_status_with_no_data_says_so():
    assert "尚未評分" in StockPresenter(FakeScores()).status()
