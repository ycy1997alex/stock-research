"""0-2: the stock universe is data, with explicit validation."""

import json

import pytest

from research import config
from research.render import page


def _write(path, symbols):
    path.write_text(json.dumps({"symbols": symbols}, ensure_ascii=False), encoding="utf-8")


def test_external_file_adds_symbol_without_python_change(tmp_path):
    _write(tmp_path / "research_symbols.json", [
        {"symbol": "2308.TW", "name": "台達電", "market": "TW", "group": "tw"},
        {"symbol": "NEW", "name": "新增標的", "market": "US", "group": "us"},
    ])

    universe = config.active_universe(tmp_path)

    assert universe.all_symbols == ("2308.TW", "NEW")
    assert universe.us_stocks == ("NEW",)
    assert universe.names["NEW"] == "新增標的"


@pytest.mark.parametrize("missing", ["symbol", "name", "market", "group"])
def test_missing_required_field_fails_loudly(tmp_path, missing):
    row = {"symbol": "NEW", "name": "新增標的", "market": "US", "group": "us"}
    del row[missing]
    path = tmp_path / "research_symbols.json"
    _write(path, [row])

    with pytest.raises(ValueError, match=missing):
        config.load_universe(path)


def test_missing_pair_is_annotated_not_an_exception(tmp_path):
    path = tmp_path / "research_symbols.json"
    _write(path, [
        {"symbol": "2330.TW", "name": "台積電", "market": "TW", "group": "tw", "pair": "TSM"},
    ])

    universe = config.load_universe(path)

    assert universe.adr_pairs == ()
    assert "2330.TW" in universe.pair_notes[0]
    assert "TSM" in universe.pair_notes[0]


def test_missing_pair_note_reaches_page(monkeypatch):
    monkeypatch.setattr(config, "ADR_PAIRS", ())
    monkeypatch.setattr(config, "PAIR_NOTES", ("2330.TW 對照組 TSM 未列入標的清單",))

    tabs = page.build_tabs({})

    assert "2330.TW 對照組 TSM 未列入標的清單" in tabs[1].intro


def test_default_universe_keeps_existing_order():
    universe = config.load_universe(config.DEFAULT_UNIVERSE_PATH)

    assert universe.tw_stocks == ("2330.TW", "2454.TW", "2308.TW", "2317.TW", "3711.TW")
    assert universe.adrs == ("TSM", "HNHPF", "ASX")
    assert universe.adr_pairs == (("2330.TW", "TSM"), ("2317.TW", "HNHPF"), ("3711.TW", "ASX"))
