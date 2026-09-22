import datetime as dt
import json

from research import config
from research.datasources.names import parse_twse_names


def test_official_short_names_override_config_and_keep_fallback_source(tmp_path):
    stamp = dt.datetime(2026, 9, 22, 12)
    rows = [{"公司代號": "2330", "公司簡稱": "臺積電", "出表日期": "1150922"},
            {"公司代號": "2454", "公司簡稱": "", "出表日期": "1150922"}]
    got = parse_twse_names(rows, ("2330.TW", "2454.TW"), stamp)
    assert got["2330.TW"]["name"] == "臺積電"
    assert got["2330.TW"]["source"] == "TWSE t187ap03_L"
    assert "2454.TW" not in got
    root = tmp_path
    (root / "research_name_directory.json").write_text(
        json.dumps(got, ensure_ascii=False), encoding="utf-8")
    universe = config.load_universe(config.DEFAULT_UNIVERSE_PATH)
    names, sources = config.load_display_names(universe, root)
    assert names["2330.TW"] == "臺積電"
    assert names["2454.TW"] == "聯發科"
    assert sources["2454.TW"] == "設定檔回退"
    assert sources["AAPL"] == "設定檔"


def test_invalid_name_cache_cannot_rename_unrelated_symbol(tmp_path):
    (tmp_path / "research_name_directory.json").write_text(json.dumps({
        "2330.TW": {"name": "Wrong", "source": "fallback"},
        "AAPL": {"name": "Wrong", "source": "TWSE t187ap03_L"},
    }), encoding="utf-8")
    names, _ = config.load_display_names(config.load_universe(config.DEFAULT_UNIVERSE_PATH), tmp_path)
    assert names["2330.TW"] == "台積電"
    assert names["AAPL"] == "Apple"
