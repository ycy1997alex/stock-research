import datetime as dt

from research.domain import local_stock, scoring_stock
from research.render import page


def _body(tabs, key):
    return next(tab for tab in tabs if tab.key == key).body


def test_stock_detail_explains_two_scores_raw_gap_strength_and_each_indicator():
    closes = [100 + i * .2 for i in range(300)]
    item = local_stock.LocalItem("A 官方估值", -60.0, 1.0, "有效", "PE 30；殖利率 1.0%（估值相對刻度）",
                                 "2026-09-18", 3, "TWSE BWIBBU_ALL")
    score = scoring_stock.score_stock(
        "2330.TW", closes, opens=[x-.1 for x in closes],
        highs=[x+1 for x in closes], lows=[x-1 for x in closes],
        volumes=[100_000]*300, local_score=-60,
        local_reasons=local_stock.LocalScore(-60.0, (item,)).reasons, local_items=(item,),
    )
    body = _body(page.build_tabs(
        {"2330.TW": ([(dt.date(2026, 9, 21), score)], {"weighted_average": score.overall})}), "tw")
    assert "可比分數" in body and "本地分數" in body
    assert "原始差距" in body
    assert "強度 C" in body
    assert "KD(9,3,3)" in body and "A 官方估值" in body
    assert "權重" in body
    assert "TWSE BWIBBU_ALL" in body and "延遲 3 天" in body


def test_us_local_age_is_shown_beside_native_score():
    closes = [100 + i * .1 for i in range(300)]
    score = scoring_stock.score_stock("AAPL", closes,
                 local_score=20, local_reasons=("13F 機構持股：延遲 91 天（有效）",))
    body = _body(page.build_tabs(
        {"AAPL": ([(dt.date(2026, 9, 21), score)], {"weighted_average": score.overall})},
        local_meta_by_symbol={"AAPL": ("2026-06-22", 91)}), "us")
    assert "本地維度資料日：2026-06-22（延遲 91 天）" in body
    assert "本地資料延遲 91 天" in body
    assert "13F 機構持股：延遲 91 天（有效）" in body   # 只有字串、沒有結構化觀測時照列
