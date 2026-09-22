"""Persist an official display-name snapshot outside either public repository."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from research.datasources.names import fetch_twse_names

DIRECTORY_FILE = "research_name_directory.json"


def refresh(root: Path, symbols: tuple[str, ...] | list[str], stamp: dt.datetime,
            *, fetch=fetch_twse_names) -> dict[str, dict[str, str]]:
    records = fetch(symbols, stamp)
    path = root / DIRECTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return records
