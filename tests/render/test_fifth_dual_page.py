import datetime as dt

from research.domain import scoring_stock
from research.render import page


def test_stock_row_explains_two_scores_raw_gap_strength_and_each_indicator():
    closes = [100 + i * .2 for i in range(300)]
    score = scoring_stock.score_stock(
        "2330.TW", closes, opens=[x-.1 for x in closes],
        highs=[x+1 for x in closes], lows=[x-1 for x in closes],
        volumes=[100_000]*300, local_score=-60,
        local_reasons=("A 官方估值：PE 30（有效）",),
    )
    row = page._stock_row("2330.TW", [(dt.date(2026,9,21), score)],
                          {"weighted_average": score.overall})
    assert "可比" in row.value and "本地" in row.value
    assert "原始差距" in row.change
    assert "強度 C" in row.note
    assert "KD(9,3,3)" in row.note and "A 官方估值" in row.note
    assert "權重" in row.note


def test_us_local_age_is_shown_beside_native_score():
    closes = [100 + i * .1 for i in range(300)]
    score = scoring_stock.score_stock("AAPL", closes,
                 local_score=20, local_reasons=("13F 機構持股：延遲 91 天（有效）",))
    row = page._stock_row("AAPL", [(dt.date(2026,9,21), score)],
                          {"weighted_average": score.overall},
                          local_data_date="2026-06-22", local_age_days=91)
    assert "本地維度資料日：2026-06-22（延遲 91 天）" in row.note
