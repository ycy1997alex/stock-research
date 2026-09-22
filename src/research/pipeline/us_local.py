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


def run(store: UsLocalStore, symbols: list[str] | tuple[str, ...], day: dt.date,
        *, fetch: Callable[[str, dt.date], dict[str, source.Observation]] = source.fetch_one,
        retrieved_at: dt.datetime | None = None) -> Result:
    log = RunLog(task="us_local")
    counts = {name: 0 for name in DIMENSIONS}
    notes: list[str] = []
    retrieved_at = retrieved_at or dt.datetime.now(ZoneInfo("Asia/Taipei"))
    try:
        for symbol in symbols:
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
                counts[name] += 1
        for key, count in counts.items():
            log.set_count(key, count)
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
    return Result(counts, tuple(notes))
