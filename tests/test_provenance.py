"""Research score rows retain price and chip provenance through shared render."""
import datetime as dt

from research.domain import scoring_stock
from research.render import page as rpage


def test_research_row_receives_actual_underlying_source_and_fetch_time():
    symbol = "2330.TW"
    day = dt.date(2026, 9, 18)
    score = scoring_stock.score_stock(symbol, [100 + i * 0.2 for i in range(220)])
    tabs = rpage.build_tabs(
        {symbol: ([(day, score)], {"weighted_average": score.overall})},
        provenance_by_symbol={symbol: ("價格：twse_stock_day_all；籌碼：TWSE T86",
                                       "2026-09-20 18:00")},
    )
    row = next(row for tab in tabs for row in tab.rows if row.label.startswith(symbol))
    assert row.source == "價格：twse_stock_day_all；籌碼：TWSE T86"
    assert row.data_date == day.isoformat()
    assert row.fetched_at == "2026-09-20 18:00"
