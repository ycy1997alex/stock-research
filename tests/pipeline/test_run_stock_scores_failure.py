"""管線中止時仍要留下 runlog（2026-09-08）。

跟 `../market-barometer/tests/pipeline/test_run_scores_failure.py` 同一條規格 ——
兩支 `run()` 是同一個寫法，所以同一個洞兩邊都有。

**記完 runlog 再重拋。** 重拋是重點：吞掉的話就變回「安靜失敗」，
那正是這次要避免的。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.ports import PriceBar
from barometer.pipeline import runlog

from research.pipeline import run_stock_scores


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """資料層指到暫存目錄 —— `config.root()` 每次都重讀環境變數。"""
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    return tmp_path


def _bars(symbol: str, n: int) -> list[PriceBar]:
    days = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)][:n]
    now = dt.datetime(2026, 9, 8, 18, 0, 0)
    return [
        PriceBar(symbol=symbol, date=d, open=100.0, high=101.0, low=99.0,
                 close=100.0, volume_shares=1000.0, source="test", as_of=now)
        for d in days
    ]


@pytest.fixture
def three_days(monkeypatch):
    """SPCX 那種情況：本機只有 3 個交易日。"""
    monkeypatch.setattr(
        run_stock_scores.csv_audit, "read_current",
        lambda symbol, **kw: _bars(symbol, 3),
    )


def _runs() -> list[dict]:
    return runlog.read_runs(dt.datetime.now().strftime("%Y-%m"))


def test_short_history_still_raises(isolated_root, three_days):
    with pytest.raises(ValueError, match="SPCX"):
        run_stock_scores.run(["SPCX"])


def test_failed_run_is_recorded_in_the_runlog(isolated_root, three_days):
    with pytest.raises(ValueError):
        run_stock_scores.run(["SPCX"], task="test_stock_scores")

    runs = _runs()
    assert len(runs) == 1, "失敗的執行沒有留下任何 runlog"
    assert runs[0]["task"] == "test_stock_scores"


def test_failed_run_is_marked_error_not_ok(isolated_root, three_days):
    with pytest.raises(ValueError):
        run_stock_scores.run(["SPCX"])

    assert _runs()[0]["status"] == "error"


def test_failed_run_records_why(isolated_root, three_days):
    with pytest.raises(ValueError):
        run_stock_scores.run(["SPCX"])

    notes = " ".join(_runs()[0]["notes"])
    assert "SPCX" in notes
    assert "3/5" in notes


def test_successful_run_still_records_ok(isolated_root, monkeypatch):
    monkeypatch.setattr(
        run_stock_scores.csv_audit, "read_current",
        lambda symbol, **kw: _bars(symbol, 5),
    )
    log = run_stock_scores.run(["2330.TW"], task="test_ok")

    assert log.status == "ok"
    runs = _runs()
    assert len(runs) == 1 and runs[0]["status"] == "ok"


def test_runlog_written_only_once_per_run(isolated_root, three_days):
    """重拋不得讓同一次執行被記兩筆。"""
    with pytest.raises(ValueError):
        run_stock_scores.run(["SPCX"])

    assert len(_runs()) == 1
