"""Read TWSE listed-company short names from its all-company directory."""
from __future__ import annotations

import datetime as dt

import requests

TWSE_NAMES_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_NAME_SOURCE = "TWSE t187ap03_L"


def parse_twse_names(rows: list[dict], symbols: tuple[str, ...] | list[str],
                     stamp: dt.datetime) -> dict[str, dict[str, str]]:
    if not isinstance(rows, list):
        raise ValueError("TWSE company directory is not a list")
    wanted = set(symbols)
    names = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = f"{str(row.get('公司代號', '')).strip()}.TW"
        name = row.get("公司簡稱")
        if symbol in wanted and isinstance(name, str) and name.strip():
            names[symbol] = {"name": name.strip(), "source": TWSE_NAME_SOURCE,
                             "fetched_at": stamp.isoformat()}
    return names


def fetch_twse_names(symbols: tuple[str, ...] | list[str], stamp: dt.datetime,
                     get=requests.get) -> dict[str, dict[str, str]]:
    response = get(TWSE_NAMES_URL, timeout=25,
                   headers={"User-Agent": "stock-research/0.1 (personal research)"})
    response.raise_for_status()
    return parse_twse_names(response.json(), symbols, stamp)
