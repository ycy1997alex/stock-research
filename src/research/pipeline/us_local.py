"""Fetch US issuer-local snapshots and retain their underlying data dates."""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from barometer.pipeline.runlog import RunLog

from research.datasources import us_local as source
from research.storage.tw_local import TwLocalStore
from research.storage.us_local import UsLocalStore

DIMENSIONS = ("institutional", "insider", "analyst")


@dataclass(frozen=True, slots=True)
class Result:
    coverage: dict[str, int]
    notes: tuple[str, ...]
    processed: int = 0
    remaining: int = 0
    cycle: str | None = None


def run(store: UsLocalStore, symbols: list[str] | tuple[str, ...], day: dt.date,
        *, fetch: Callable[[str, dt.date], dict[str, source.Observation]] = source.fetch_one,
        retrieved_at: dt.datetime | None = None,
        cycle: str | None = None, batch_size: int | None = None) -> Result:
    if batch_size is not None and batch_size < 1:
        raise ValueError("batch_size must be positive")
    if cycle is not None and not cycle.strip():
        raise ValueError("cycle must not be empty")
    log = RunLog(task="us_local")
    notes: list[str] = []
    retrieved_at = retrieved_at or dt.datetime.now(ZoneInfo("Asia/Taipei"))
    ordered = list(dict.fromkeys(symbols))
    completed: set[str] = set()
    if cycle is not None:
        store.init_batch_schema()
        if cycle == "auto":
            cycle = store.active_auto_cycle(ordered, retrieved_at)
        completed = store.completed_symbols(cycle)
    pending = [symbol for symbol in ordered if symbol not in completed]
    selected = pending[:batch_size] if batch_size is not None else pending
    processed = 0
    try:
        for symbol in selected:
            got = fetch(symbol, day)
            for name in DIMENSIONS:
                observation = got.get(name)
                if observation is None:
                    notes.append(f"{symbol} {name}: 資料不足，不落地成 0")
                    continue
                if observation.data_date > day:
                    raise ValueError(f"{symbol} {name}: 資料日期晚於評分日")
                store.put(symbol, name, observation.data_date, observation.value,
                          observation.source, retrieved_at)
            if cycle is not None:
                store.mark_complete(cycle, symbol, retrieved_at)
            processed += 1
        counts = {name: sum(name in store.get_asof(day, symbol) for symbol in ordered)
                  for name in DIMENSIONS}
        remaining = len(pending) - processed
        for key, count in counts.items():
            log.set_count(key, count)
        log.set_count("processed", processed)
        log.set_count("remaining", remaining)
        for note in notes:
            log.note(note)
        log.finish("partial" if notes or remaining else "ok")
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
    return Result(counts, tuple(notes), processed, remaining, cycle)
