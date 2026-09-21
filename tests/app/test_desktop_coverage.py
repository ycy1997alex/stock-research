"""Research desktop labels technical coverage and unavailable fundamentals."""
import datetime as dt

from barometer.domain.ports import ScoreRecord
from research.app.presenters.dashboard import StockPresenter


class Scores:
    def get_scores(self, scope, symbol):
        if symbol != "SPCX":
            return []
        return [ScoreRecord(scope, symbol, dt.date(2026, 9, 18), 80.0,
                            {"short": 80.0}, "v1")]


def test_research_desktop_marks_one_of_three_and_keeps_fundamentals_separate():
    row = next(r for r in StockPresenter(Scores()).load("us") if r.key == "SPCX")
    assert row.value == "80.0"
    assert "技術面 1/3 項（33%）" in row.note
    assert "低涵蓋・降級" in row.note
    assert "基本面：尚未接入" in row.note
