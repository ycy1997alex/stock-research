"""Official Taiwan source parsing contracts for batch three."""
from __future__ import annotations

import datetime as dt

import pytest

from research.datasources import tw_local


STAMP = dt.datetime(2026, 9, 21, 10, 0)


def test_valuation_uses_report_date_and_missing_is_not_zero():
    rows = [
        {"Date": "1150918", "Code": "2330", "PEratio": "28.52", "DividendYield": "0.89", "PBratio": "9.92"},
        {"Date": "1150918", "Code": "2317", "PEratio": "-", "DividendYield": "", "PBratio": "1.2"},
    ]
    got = tw_local.parse_valuation(rows, STAMP)
    assert got.data_date == dt.date(2026, 9, 18)
    assert got.source == "TWSE BWIBBU_ALL"
    assert got.retrieved_at == STAMP
    assert got.values["2330.TW"] == {"pe_ratio": 28.52, "dividend_yield_pct": 0.89, "pb_ratio": 9.92}
    assert got.values["2317.TW"]["pe_ratio"] is None
    assert "TSM" not in got.values


def test_breadth_reads_stock_counts_not_whole_market():
    payload = {"stat": "OK", "date": "20260918", "tables": [
        {"title": "漲跌證券數合計", "fields": ["類型", "整體市場", "股票"], "data": [
            ["上漲(漲停)", "9,531(119)", "748(32)"], ["下跌(跌停)", "4,331(55)", "251(0)"],
            ["持平", "968", "78"], ["未成交", "16,946", "1"],
        ]},
    ]}
    got = tw_local.parse_breadth(payload, STAMP)
    assert got.values["market"]["advancers_count"] == 748
    assert got.values["market"]["decliners_count"] == 251
    assert got.values["market"]["unchanged_count"] == 78
    assert got.values["market"]["advance_decline_pct"] == pytest.approx(748 / 999 * 100)


def test_unpublished_breadth_raises():
    with pytest.raises(tw_local.NotPublishedYet):
        tw_local.parse_breadth({"stat": "很抱歉，沒有符合條件的資料", "tables": []}, STAMP)


def test_monthly_revenue_preserves_reporting_and_release_dates():
    rows = [{"出表日期": "1150917", "資料年月": "11508", "公司代號": "2330",
             "營業收入-當月營收": "514805337", "營業收入-去年同月增減(%)": "53.32"}]
    got = tw_local.parse_revenue(rows, STAMP)
    assert got.data_date == dt.date(2026, 9, 17)
    assert got.values["2330.TW"]["reporting_period"] == "2026-08"
    assert got.values["2330.TW"]["revenue_ktwd"] == 514805337
    assert got.values["2330.TW"]["revenue_yoy_pct"] == 53.32


def test_tdcc_distribution_groups_by_symbol_and_grade():
    rows = [
        {"證券代號": "2330  ", "\ufeff資料日期": "20260918", "持股分級": "1", "人數": "2", "股數": "100", "占集保庫存數比例%": "1.0"},
        {"證券代號": "2330  ", "\ufeff資料日期": "20260918", "持股分級": "15", "人數": "3", "股數": "900", "占集保庫存數比例%": "9.0"},
    ]
    got = tw_local.parse_distribution(rows, STAMP)
    assert got.data_date == dt.date(2026, 9, 18)
    assert got.values["2330.TW"]["grades"]["15"]["holder_count"] == 3
    assert got.values["2330.TW"]["grades"]["15"]["shares"] == 900


def test_foreign_holdings_uses_stock_rows_and_units():
    got = tw_local.parse_foreign_holdings({"stat": "OK", "date": "20260918",
        "fields": ["證券代號", "發行股數", "外資及陸資尚可投資股數", "全體外資及陸資持有股數", "全體外資及陸資持股比率"],
        "data": [["2330", "25,932,370,067", "7,980,559,620", "17,951,810,447", "69.22"]]}, STAMP)
    assert got.values["2330.TW"]["foreign_held_shares"] == 17951810447
    assert got.values["2330.TW"]["foreign_holding_pct"] == 69.22


def test_day_trade_uses_individual_volume():
    payload = {"stat": "OK", "date": "20260918", "tables": [
        {"title": "當日沖銷交易標的及成交量值", "fields": ["證券代號", "當日沖銷交易成交股數", "當日沖銷交易買進成交金額"],
         "data": [["2330", "4,805,000", "11,764,940,000"]]},
    ]}
    got = tw_local.parse_day_trade(payload, STAMP)
    assert got.values["2330.TW"]["day_trade_shares"] == 4805000
    assert got.values["2330.TW"]["day_trade_buy_twd"] == 11764940000


def test_securities_lending_uses_second_balance_column():
    fields = ["代號", "名稱", "前日餘額", "賣出", "買進", "現券", "今日餘額", "次一營業日限額",
              "前日餘額", "當日賣出", "當日還券", "當日調整", "當日餘額", "次一營業日可限額", "備註"]
    row = ["2330", "台積電", "11,000", "5,000", "1,000", "0", "15,000", "6,483,092,516",
           "15,738,514", "131,000", "197,000", "0", "15,672,514", "6,293,132", " "]
    got = tw_local.parse_lending({"stat": "OK", "date": "20260918", "fields": fields, "data": [row]}, STAMP)
    assert got.values["2330.TW"]["short_balance_shares"] == 15000
    assert got.values["2330.TW"]["borrowed_short_balance_shares"] == 15672514


def test_one_all_market_fetch_serves_every_watched_symbol(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"Date": "1150918", "Code": code, "PEratio": "20",
                     "DividendYield": "1", "PBratio": "2"} for code in ("2330", "2317")]

    def get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(tw_local.requests, "get", get)
    tw_local._CACHE.clear()
    try:
        first = tw_local.fetch("valuation", dt.date(2026, 9, 18))
        second = tw_local.fetch("valuation", dt.date(2026, 9, 18))
        assert first is second
        assert len(calls) == 1
        assert set(first.values) == {"2330.TW", "2317.TW"}
    finally:
        tw_local._CACHE.clear()
