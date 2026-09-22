from barometer.app.presenters.dashboard import ViewRow
from research.app.views.dashboard import StockDashboardWindow, sort_view_rows


def _row(label, value, date):
    return ViewRow(key=label, label=label, value=value, data_date=date,
                   freq="每日", note="")


def test_desktop_sort_is_numeric_and_missing_values_remain_last():
    rows = [_row("Z", "8.0", "2026-09-22"),
            _row("B", None, None),
            _row("A", "10.0", "2026-09-21")]
    assert [row.label for row in sort_view_rows(rows, "value", False)] == ["Z", "A", "B"]
    assert [row.label for row in sort_view_rows(rows, "value", True)] == ["A", "Z", "B"]
    assert [row.label for row in sort_view_rows(rows, None, False)] == ["Z", "B", "A"]


def test_heading_click_cycles_ascending_descending_original_order():
    window = object.__new__(StockDashboardWindow)
    window._sort = {}
    seen = []
    window._fill = lambda key: seen.append((key, window._sort[key]))
    window._sort_column("tw", "value")
    window._sort_column("tw", "value")
    window._sort_column("tw", "value")
    assert seen == [("tw", ("value", False)), ("tw", ("value", True)),
                    ("tw", (None, False))]
