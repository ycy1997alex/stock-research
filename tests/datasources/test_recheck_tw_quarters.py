"""回補批 R-4（一）：台股季報的歷史要來自官方，而且不得假裝知道首次公開日。

`t187ap17_L` 只回最新一季（實測 1,053 列全是 115Q2），所以歷史季別另走公開資訊
觀測站的營益分析查詢彙總表 `t163sb06`（實測可指定年度／季別）。
⚠️ 兩張表都是**累計至該季**，不是單季；口徑要跟著資料走，不能在文字上含糊。
"""
from __future__ import annotations

import datetime as dt
import gzip
from pathlib import Path

from research.datasources import fundamentals as source

FIXTURE = gzip.decompress(
    (Path(__file__).resolve().parents[1] / "fixtures" / "mops_t163sb06_114Q3.html.gz").read_bytes()
).decode("utf-8")
STAMP = dt.datetime(2026, 9, 22, 19, 0)


def test_period_maps_to_the_official_roc_year_and_season():
    assert source.mops_quarter_params("2025Q3") == {"year": "114", "season": "03"}
    assert source.mops_quarter_params("2026Q1") == {"year": "115", "season": "01"}


def test_parses_real_page_into_cumulative_quarter_metrics():
    parsed = source.parse_tw_quarter_page(FIXTURE, "2025Q3", STAMP)
    assert parsed["2330.TW"].gross_margin_pct == 58.97
    assert parsed["2317.TW"].gross_margin_pct == 6.27
    assert parsed["2330.TW"].period == "2025Q3"
    # 口徑：官方這張表是年度累計（每年 Q1 歸零），不是單季
    assert parsed["2330.TW"].basis == "年度累計"
    # 取得日是今天；這張表給不出「財報首次公開日」，所以不得假裝有
    assert parsed["2330.TW"].data_date == STAMP.date()


def test_history_fetch_asks_for_each_period_and_keeps_them_sorted():
    asked = []

    class Response:
        text = FIXTURE

        def raise_for_status(self):
            return None

    def fake_post(url, data=None, **kwargs):
        asked.append((url, data["year"], data["season"]))
        return Response()

    got = source.fetch_tw_quarter_history(("2025Q3", "2025Q4"), STAMP, post=fake_post)
    assert [(year, season) for _url, year, season in asked] == [("114", "03"), ("114", "04")]
    assert all(url.endswith("ajax_t163sb06") for url, _y, _s in asked)
    assert [q.period for q in got["2330.TW"]] == ["2025Q3", "2025Q4"]
