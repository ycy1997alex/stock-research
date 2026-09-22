from barometer.render.page import Row, Tab, render
from research.render import page as research_page
from research import config


def test_stock_summary_keeps_configured_order_and_all_rows_by_default(monkeypatch):
    symbols = tuple(f"{number:04d}.TW" for number in range(200, 0, -1))
    monkeypatch.setattr(config, "TW_STOCKS", symbols)
    tabs = research_page.build_tabs({})
    summary = tabs[0]
    assert [row.label.split()[0] for row in summary.rows] == list(symbols)
    assert len(summary.rows) == 200
    assert summary.sortable


def test_page_sort_is_user_triggered_and_preserves_initial_row_order():
    tab = Tab("tw", "台股", [Row("Z", "+8", "2026-09-22"),
                             Row("A", "+10", "2026-09-21")], sortable=True)
    html = render([tab], "research")
    assert html.index("<td>Z") < html.index("<td>A")
    assert "data-sortable" in html
    assert "addEventListener('click'" in html
    assert "Top N" not in html
    assert ".slice(" not in html
