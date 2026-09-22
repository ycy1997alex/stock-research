"""Calibrate native display weight from availability and raw-gap stability.

No forward returns, trades, or future prices enter this selection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MIN_SESSIONS = 30
MIN_COVERAGE = .50
MAX_P90_RAW_GAP = 15.0


@dataclass(frozen=True, slots=True)
class Candidate:
    weight: float
    p90_gap: float | None


@dataclass(frozen=True, slots=True)
class Calibration:
    selected: float
    coverage: float
    sessions: int
    candidates: tuple[Candidate, ...]


def calibrate_weight(samples: list[tuple[float | None, float | None]],
                     candidates: tuple[float, ...]) -> Calibration:
    if not candidates or 0 not in candidates or any(not 0 <= weight <= 1 for weight in candidates):
        raise ValueError("candidates must include zero and lie in [0,1]")
    present = [(technical, local) for technical, local in samples
               if technical is not None and local is not None]
    coverage = len(present) / len(samples) if samples else 0.0
    results = []
    for weight in sorted(set(candidates)):
        gaps = sorted(abs(weight * (local - technical)) for technical, local in present)
        p90 = gaps[math.ceil(.9 * len(gaps)) - 1] if gaps else None
        results.append(Candidate(weight, p90))
    eligible = (len(samples) >= MIN_SESSIONS and coverage >= MIN_COVERAGE)
    selected = max((item.weight for item in results
                    if eligible and item.p90_gap is not None
                    and item.p90_gap <= MAX_P90_RAW_GAP), default=0.0)
    return Calibration(selected, coverage, len(samples), tuple(results))
