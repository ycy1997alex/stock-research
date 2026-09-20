"""Stock universe loaded from JSON, with an editable external override.

Edit ``%STOCKDATA_ROOT%/research_symbols.json`` to add a symbol without
changing Python code or rebuilding the desktop executable. If it is absent,
the bundled ``symbols.json`` supplies the initial 15-symbol universe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from barometer import config as barometer_config


DEFAULT_UNIVERSE_PATH = Path(__file__).with_name("symbols.json")
EXTERNAL_UNIVERSE_NAME = "research_symbols.json"
_REQUIRED = frozenset({"symbol", "name", "market", "group"})
_GROUP_MARKET = {"tw": "TW", "us": "US", "adr": "US"}


@dataclass(frozen=True, slots=True)
class Universe:
    tw_stocks: tuple[str, ...]
    us_stocks: tuple[str, ...]
    adrs: tuple[str, ...]
    names: dict[str, str]
    adr_pairs: tuple[tuple[str, str], ...]
    pair_notes: tuple[str, ...]
    thin_liquidity: tuple[str, ...]

    @property
    def all_symbols(self) -> tuple[str, ...]:
        return self.tw_stocks + self.us_stocks + self.adrs


def load_universe(path: Path) -> Universe:
    """Read and validate one complete universe; never fill missing fields."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("symbols"), list) or not data["symbols"]:
        raise ValueError(f"{path}: symbols must be a nonempty list")

    groups: dict[str, list[str]] = {group: [] for group in _GROUP_MARKET}
    names: dict[str, str] = {}
    pairs_requested: list[tuple[str, str]] = []
    thin: list[str] = []
    for index, row in enumerate(data["symbols"]):
        if not isinstance(row, dict):
            raise ValueError(f"{path}: symbols[{index}] must be an object")
        missing = _REQUIRED - row.keys()
        if missing:
            raise ValueError(f"{path}: symbols[{index}] missing {', '.join(sorted(missing))}")
        symbol, name, market, group = (row[key] for key in ("symbol", "name", "market", "group"))
        if not all(isinstance(value, str) and value.strip() for value in (symbol, name, market, group)):
            raise ValueError(f"{path}: symbols[{index}] required fields must be nonempty strings")
        if group not in _GROUP_MARKET or market != _GROUP_MARKET[group]:
            raise ValueError(f"{path}: symbols[{index}] invalid market/group: {market}/{group}")
        if symbol in names:
            raise ValueError(f"{path}: duplicate symbol {symbol}")
        names[symbol] = name
        groups[group].append(symbol)
        pair = row.get("pair")
        if pair is not None:
            if group != "tw" or not isinstance(pair, str) or not pair.strip():
                raise ValueError(f"{path}: symbols[{index}] pair requires a TW stock and nonempty string")
            pairs_requested.append((symbol, pair))
        if row.get("thin_liquidity", False):
            thin.append(symbol)

    adrs = set(groups["adr"])
    pairs = tuple((tw, adr) for tw, adr in pairs_requested if adr in adrs)
    notes = tuple(f"{tw} 對照組 {adr} 未列入標的清單" for tw, adr in pairs_requested if adr not in adrs)
    return Universe(
        tw_stocks=tuple(groups["tw"]),
        us_stocks=tuple(groups["us"]),
        adrs=tuple(groups["adr"]),
        names=names,
        adr_pairs=pairs,
        pair_notes=notes,
        thin_liquidity=tuple(thin),
    )


def active_universe(root: Path | None = None) -> Universe:
    """External file wins if present; an invalid file fails before fetching."""
    root = barometer_config.stockdata_root() if root is None else root
    override = root / EXTERNAL_UNIVERSE_NAME
    return load_universe(override if override.exists() else DEFAULT_UNIVERSE_PATH)


_UNIVERSE = active_universe()
TW_STOCKS = _UNIVERSE.tw_stocks
US_STOCKS = _UNIVERSE.us_stocks
ADRS = _UNIVERSE.adrs
ALL_SYMBOLS = _UNIVERSE.all_symbols
NAMES = _UNIVERSE.names
ADR_PAIRS = _UNIVERSE.adr_pairs
PAIR_NOTES = _UNIVERSE.pair_notes
THIN_LIQUIDITY = _UNIVERSE.thin_liquidity

# Data sufficiency is a scoring rule, independent of the watched universe.
MIN_BARS_MID_TERM = 60
MIN_BARS_LONG_TERM = 200
