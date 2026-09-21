"""Ingest and assemble official Taiwan-only local data without scoring it.

Numeric local scoring belongs to batch five. Revenue is a separate fundamental
observation because the released event may already be reflected in price.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

from barometer.domain.coverage import Coverage
from barometer.pipeline.runlog import RunLog

from research.datasources import tw_local as source
from research.datasources.tw_local import Snapshot
from research.domain.margin_tw import estimate_margin
from research.storage.tw_local import TwLocalStore


LOCAL_DATASETS = frozenset({"valuation", "breadth", "distribution", "foreign", "day_trade", "lending", "margin_estimate"})
FETCH_DATASETS = ("valuation", "breadth", "revenue", "distribution", "foreign", "day_trade", "lending", "margin_estimate")


@dataclass(frozen=True, slots=True)
class IngestResult:
    coverage: dict[str, Coverage]
    notes: tuple[str, ...]


def run(
    store: TwLocalStore,
    session_date: dt.date,
    symbols: tuple[str, ...] | list[str],
    *,
    volume_shares_by_symbol: Mapping[str, float | None] | None = None,
    close_twd_by_symbol: Mapping[str, float | None] | None = None,
) -> IngestResult:
    """Fetch each official all-market dataset once and then select symbols."""
    log = RunLog(task="tw_local")
    coverage: dict[str, Coverage] = {}
    notes: list[str] = []
    try:
        for dataset in FETCH_DATASETS:
            try:
                snapshot = source.fetch(dataset, session_date)
                if dataset == "margin_estimate" and snapshot.data_date != session_date:
                    note = (f"{dataset}: 官方資料日期 {snapshot.data_date} 與收盤價日期"
                            f" {session_date} 不同；不以錯日價格推算")
                    notes.append(note)
                    log.note(note)
                    continue
                coverage[dataset] = save_snapshot(
                    store, dataset, snapshot, symbols,
                    volume_shares_by_symbol=volume_shares_by_symbol,
                    close_twd_by_symbol=close_twd_by_symbol,
                )
                log.set_count(dataset, coverage[dataset].available)
            except source.NotPublishedYet as exc:
                note = f"{dataset}: {exc}；未公布，不落地成 0"
                notes.append(note)
                log.note(note)
        log.finish("partial" if notes else "ok")
        store.record_run(log.run_id, log.task, log.started_at, log.ended_at,
                         log.status, log.counts)
    except Exception as exc:
        log.note(f"中止：{type(exc).__name__}: {exc}")
        log.finish("error")
        try:
            store.record_run(log.run_id, log.task, log.started_at, log.ended_at,
                             log.status, log.counts)
        except Exception:
            pass
        log.append()
        raise
    log.append()
    return IngestResult(coverage, tuple(notes))


def backfill_margin_history(
    store: TwLocalStore,
    session_closes: Mapping[dt.date, Mapping[str, float | None]],
    symbols: tuple[str, ...] | list[str],
) -> dict[dt.date, Coverage]:
    """Manually populate the initial cost history, once per trading session.

    This is never called by the daily publish path. A nonmatching report date is
    skipped rather than assigned to a different session or stored as zero.
    """
    log = RunLog(task="tw_margin_backfill")
    coverage: dict[dt.date, Coverage] = {}
    try:
        for day, closes in sorted(session_closes.items()):
            try:
                snapshot = source.fetch("margin_estimate", day)
            except source.NotPublishedYet as exc:
                log.note(f"{day}: {exc}；未公布，不落地成 0")
                continue
            if snapshot.data_date != day:
                log.note(f"{day}: 官方資料日期 {snapshot.data_date} 不符，跳過")
                continue
            coverage[day] = save_snapshot(
                store, "margin_estimate", snapshot, symbols,
                close_twd_by_symbol=closes,
            )
            log.set_count(f"{day.isoformat()}_available", coverage[day].available)
        log.finish("partial" if len(coverage) != len(session_closes) else "ok")
        store.record_run(log.run_id, log.task, log.started_at, log.ended_at,
                         log.status, log.counts)
    except Exception as exc:
        log.note(f"中止：{type(exc).__name__}: {exc}")
        log.finish("error")
        try:
            store.record_run(log.run_id, log.task, log.started_at, log.ended_at,
                             log.status, log.counts)
        except Exception:
            pass
        log.append()
        raise
    log.append()
    return coverage


def save_snapshot(
    store: TwLocalStore, dataset: str, snapshot: Snapshot, symbols: tuple[str, ...] | list[str],
    *, volume_shares_by_symbol: Mapping[str, float | None] | None = None,
    close_twd_by_symbol: Mapping[str, float | None] | None = None,
) -> Coverage:
    """Select watched symbols from one all-market result and record provenance."""
    if dataset not in LOCAL_DATASETS | {"revenue"}:
        raise ValueError(f"unknown local dataset: {dataset}")
    if dataset == "breadth":
        value = snapshot.values.get("market")
        if value is not None:
            store.put_market_daily(snapshot.data_date, dataset, _record(snapshot, value), snapshot.retrieved_at)
        return Coverage(int(value is not None), 1)

    found = 0
    for symbol in symbols:
        value = snapshot.values.get(symbol)
        if value is None or not _has_observation(value):
            continue
        value = dict(value)
        if dataset == "day_trade":
            volume = (volume_shares_by_symbol or {}).get(symbol)
            shares = value.get("day_trade_shares")
            value["day_trade_ratio_pct"] = (shares / volume * 100 if shares is not None and volume is not None and volume > 0 else None)
        if dataset == "margin_estimate":
            earlier = store.get_stock_daily_asof(snapshot.data_date - dt.timedelta(days=1), symbol)
            previous = earlier.get("margin_estimate")
            value = estimate_margin(
                value.get("margin_prev_shares"), value.get("margin_balance_shares"),
                (close_twd_by_symbol or {}).get(symbol),
                previous["value"] if previous else None,
            )
        record = _record(snapshot, value)
        if dataset == "day_trade" and value["day_trade_ratio_pct"] is not None:
            record["source"] += " + 本機同日成交量"
        if dataset == "margin_estimate":
            record["source"] += " + 本機同日收盤價（推算值）"
        if dataset == "distribution":
            store.put_stock_weekly(snapshot.data_date, symbol, record, snapshot.retrieved_at)
        elif dataset == "revenue":
            store.put_stock_monthly(value["reporting_period"], symbol, snapshot.data_date, record, snapshot.retrieved_at)
        else:
            store.put_stock_daily(snapshot.data_date, symbol, dataset, record, snapshot.retrieved_at)
        if dataset != "margin_estimate" or (value["maintenance_pct"] is not None
                                            and value["average_cost_twd"] is not None):
            found += 1
    return Coverage(found, len(symbols))


def _has_observation(value: dict) -> bool:
    """A row full of missing numeric values is not a covered symbol."""
    return any(
        item is not None and item != "" and key not in {"reporting_period"}
        and (not isinstance(item, dict) or bool(item))
        for key, item in value.items()
    )


def _record(snapshot: Snapshot, value: dict) -> dict:
    return {
        "value": value,
        "source": snapshot.source,
        "data_date": snapshot.data_date.isoformat(),
        "retrieved_at": snapshot.retrieved_at.isoformat(),
    }


def local_view(store: TwLocalStore, symbol: str, day: dt.date) -> dict:
    """Keep local and fundamental data distinct; never manufacture scores."""
    if not symbol.endswith(".TW"):
        return {"local": None, "fundamentals": None, "provenance": {},
                "comparable": None, "native": None, "note": "無對應資料"}
    records = store.get_stock_daily_asof(day, symbol)
    weekly = store.get_stock_weekly(day, symbol)
    market = store.get_market_daily_asof(day)
    if weekly:
        records["distribution"] = weekly
    if market.get("breadth"):
        records["breadth"] = market["breadth"]
    revenue = store.get_stock_monthly(day, symbol)
    return {
        "local": {key: rec["value"] for key, rec in records.items() if key in LOCAL_DATASETS} or None,
        "fundamentals": {"revenue": revenue["value"]} if revenue else None,
        "fundamental_provenance": ({"revenue": {k: revenue[k] for k in ("source", "data_date", "retrieved_at")}}
                                   if revenue else {}),
        "provenance": {key: {k: rec[k] for k in ("source", "data_date", "retrieved_at")}
                       for key, rec in records.items() if key in LOCAL_DATASETS},
        "comparable": None,
        "native": None,
        "note": None,
    }
