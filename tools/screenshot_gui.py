"""Capture both stock-research desktop tabs with the shared GUI QA runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[2] / "market-barometer" / "tools" / "screenshot_gui.py"


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, str(RUNNER), "--site", "research"]))
