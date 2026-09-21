from __future__ import annotations

from barometer.render import page as base_page
from research.render import page as rpage


def test_local_page_displays_independent_provenance_coverage_and_adr_absence():
    stamp = "2026-09-21T10:15:00"
    source = {"source": "TWSE BWIBBU_ALL", "data_date": "2026-09-18", "retrieved_at": stamp}
    view = {"local": {"valuation": {"pe_ratio": 28.52, "dividend_yield_pct": 0.89, "pb_ratio": 9.92}},
            "provenance": {"valuation": source}, "fundamentals": None, "fundamental_provenance": {},
            "comparable": None, "native": None}
    tabs = rpage.build_tabs({}, local_by_symbol={"2330.TW": view},
                            local_coverage={"valuation": (1, 5)})
    html = base_page.render(tabs, title="測試", tagline="資料維度", enforce_lint=False)
    assert "官方估值" in html
    assert "28.52" in html
    assert "TWSE BWIBBU_ALL" in html
    assert "2026-09-18" in html
    assert "2026-09-21T10:15:00" in html
    assert "1/5" in html
    assert "無對應資料" in html  # ADR rows


def test_revenue_is_separate_and_maintenance_is_marked_estimate():
    stamp = "2026-09-21T10:15:00"
    view = {
        "local": {"margin_estimate": {"maintenance_pct": 166.67, "average_cost_twd": 100.0}},
        "provenance": {"margin_estimate": {"source": "TWSE TWTA1U + 收盤價（推算值）", "data_date": "2026-09-18", "retrieved_at": stamp}},
        "fundamentals": {"revenue": {"reporting_period": "2026-08", "revenue_ktwd": 514805337}},
        "fundamental_provenance": {"revenue": {"source": "TWSE t187ap05_L", "data_date": "2026-09-17", "retrieved_at": stamp}},
    }
    tabs = rpage.build_tabs({}, local_by_symbol={"2330.TW": view})
    assert tabs[-2].title == "台股本地維度"
    assert tabs[-1].title == "台股月營收（獨立）"
    html = base_page.render(tabs, title="測試", tagline="資料維度", enforce_lint=False)
    assert "推算值" in html
    assert "514,805,337 仟元" in html
    assert "不進任何分數" in html


def test_tdcc_page_shows_actual_grade_share_not_just_grade_count():
    value = {"grades": {"1": {"holder_count": 2, "shares": 100, "custody_pct": 1.0},
                        "15": {"holder_count": 3, "shares": 900, "custody_pct": 9.0}}}
    rendered = rpage._local_value("distribution", value)
    assert "第1級 1.00%" in rendered
    assert "第15級 9.00%" in rendered
