"""Technical and future fundamental coverage remain separate in research."""
import datetime as dt

from barometer.render.page import render
from research.domain import scoring_stock
from research.render import page as rpage


def test_short_history_renormalizes_score_and_marks_low_technical_coverage():
    score = scoring_stock.score_stock("SPCX", [100 + i * 0.1 for i in range(59)])
    assert score.short.score is not None
    assert score.mid.score is None
    assert score.long.score is None
    assert score.overall == score.short.score
    tabs = rpage.build_tabs(
        {"SPCX": ([(dt.date(2026, 9, 18), score)],
                  {"weighted_average": score.overall})})
    row = next(row for tab in tabs for row in tab.rows if row.label.startswith("SPCX"))
    assert row.coverage.available == 1
    assert row.coverage.expected == 3
    assert row.fundamental_coverage.expected == 0
    html = render(tabs, "research")
    assert "低涵蓋・降級" in html
    assert "技術面 1/3 項（33%）" in html
    assert "基本面：尚未接入" in html
