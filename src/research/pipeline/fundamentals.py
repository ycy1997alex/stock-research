"""Assemble independent fundamentals from official TW and Yahoo snapshots."""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from barometer.domain.coverage import Coverage
from barometer.pipeline.runlog import RunLog

from research.datasources import fundamentals as source
from research.domain.fundamentals import FundamentalReport, Metric
from research.storage.fundamentals import FundamentalStore
from research.storage.tw_local import TwLocalStore


@dataclass(frozen=True, slots=True)
class Result:
    coverage: dict[str, Coverage]
    notes: tuple[str, ...]


def refresh(store: FundamentalStore, tw_symbols: tuple[str, ...] | list[str],
            us_symbols: tuple[str, ...] | list[str], stamp: dt.datetime,
            *, fetch_tw: Callable = source.fetch_tw_official,
            fetch_us: Callable = source.fetch_us_yahoo) -> Result:
    """One official market fetch, one Yahoo fetch per US symbol, dated in storage."""
    log = RunLog(task="stock_fundamentals")
    coverage: dict[str, Coverage] = {}
    notes: list[str] = []
    try:
        try:
            tw_reports = fetch_tw(stamp)
        except Exception as exc:
            tw_reports = {}
            notes.append(f"TWSE 季報取得失敗：{type(exc).__name__}: {exc}")
        for symbol in tw_symbols:
            report = tw_reports.get(symbol)
            if report is not None:
                store.put(report, stamp)
            coverage[symbol] = report.coverage if report else Coverage(0, 11)
            if not report:
                notes.append(f"{symbol}: 官方季報資料不足")
        for symbol in us_symbols:
            try:
                report = fetch_us(symbol, stamp)
            except Exception as exc:
                prior = store.get_asof(symbol, stamp.date())
                report = prior or FundamentalReport(symbol, {})
                notes.append(f"{symbol}: Yahoo 財報取得失敗：{type(exc).__name__}: {exc}")
            else:
                store.put(report, stamp)
            coverage[symbol] = report.coverage
            if report.coverage.available == 0:
                notes.append(f"{symbol}: 基本面欄位資料不足")
        for symbol, amount in coverage.items():
            log.set_count(f"covered::{symbol}", amount.available)
        for note in notes:
            log.note(note)
        log.finish("partial" if notes else "ok")
        TwLocalStore(store.conn).record_run(log.run_id, log.task, log.started_at,
                                            log.ended_at, log.status, log.counts)
    except Exception as exc:
        log.note(f"中止：{type(exc).__name__}: {exc}")
        log.finish("error")
        try:
            TwLocalStore(store.conn).record_run(log.run_id, log.task, log.started_at,
                                                log.ended_at, log.status, log.counts)
        except Exception:
            pass
        log.append()
        raise
    log.append()
    return Result(coverage, tuple(notes))


def merge_quarter_history(store: FundamentalStore, symbols, history: dict,
                          stamp: dt.datetime) -> dict[str, int]:
    """把一次性補到的季別併進**今天**這一份快照，回每檔併完後的季別數。

    只動 `quarters`，今天抓到的欄位原封不動。補回來的季別掛在今天的觀測日底下 ——
    官方那張表給不出財報首次公開日，所以它們標的是取得日，不是公開日（回補批 R-4）。
    """
    filled: dict[str, int] = {}
    for symbol in symbols:
        current = store.get_asof(symbol, stamp.date())
        if current is None:
            filled[symbol] = 0
            continue
        quarters = {quarter.period: quarter for quarter in history.get(symbol, ())}
        quarters.update({quarter.period: quarter for quarter in current.quarters})
        merged = tuple(quarters[key] for key in sorted(quarters))
        store.put(FundamentalReport(symbol, current.metrics, merged, current.industry), stamp)
        filled[symbol] = len(merged)
    return filled


def _metric(value: object, provenance: dict, period: str | None = None) -> Metric:
    date_text = provenance.get("data_date")
    stamp_text = provenance.get("retrieved_at")
    try:
        data_date = dt.date.fromisoformat(date_text) if date_text else None
        stamp = dt.datetime.fromisoformat(stamp_text) if stamp_text else None
    except ValueError:
        data_date = stamp = None
    return Metric(value if isinstance(value, (int, float)) else None,
                  provenance.get("source", ""), data_date, stamp, period)


def compose_tw_report(symbol: str, view: dict, quarterly: FundamentalReport | None,
                      day: dt.date) -> FundamentalReport:
    """Read TWSE valuation/monthly revenue; never copy either into local scoring."""
    local, fundamentals = view.get("local") or {}, view.get("fundamentals") or {}
    provenance = view.get("provenance") or {}
    fundamental_provenance = view.get("fundamental_provenance") or {}
    valuation = local.get("valuation") or {}
    metrics = {}
    for field in ("pe_ratio", "pb_ratio", "dividend_yield_pct"):
        metrics[field] = _metric(valuation.get(field), provenance.get("valuation") or {})
    revenue = fundamentals.get("revenue") or {}
    metrics["revenue_yoy_pct"] = _metric(
        revenue.get("revenue_yoy_pct"), fundamental_provenance.get("revenue") or {},
        revenue.get("reporting_period"),
    )
    quarters = ()
    if quarterly is not None:
        current = quarterly.asof(day)
        metrics.update(current.metrics)
        quarters = current.quarters
    return FundamentalReport(symbol, metrics, quarters)
