"""stock-research 的標的清單（ToDo §7.2）。

**這個 repo 的內容只有自己看** —— 具名個股的數值、評分、建議只出現在這裡，
不進 iThome 挑戰內容（§2.1）。挑戰內容那邊只講「什麼是權值股、名單從哪裡查、
為什麼是這幾檔」這些觀念。

資料層與 market-barometer **共用**（同一個 STOCKDATA_ROOT），抓一次餵兩個站，
避免重複打 API（§1 第 8 條）。
"""
from __future__ import annotations

# 台股權值股 —— 顯示單位「張」（內部一律存股）
TW_STOCKS: tuple[str, ...] = (
    "2330.TW",   # 台積電
    "2454.TW",   # 聯發科
    "2308.TW",   # 台達電
    "2317.TW",   # 鴻海
    "3711.TW",   # 日月光投控
)

# 美股權值股 —— 顯示單位「股」
US_STOCKS: tuple[str, ...] = (
    "NVDA", "AAPL", "GOOG", "MSFT", "AMZN", "SPCX", "META",
)

# 台灣 ADR —— 顯示單位「股」
ADRS: tuple[str, ...] = ("TSM", "HNHPF", "ASX")

ALL_SYMBOLS = TW_STOCKS + US_STOCKS + ADRS

NAMES: dict[str, str] = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2317.TW": "鴻海", "3711.TW": "日月光投控",
    "NVDA": "NVIDIA", "AAPL": "Apple", "GOOG": "Alphabet",
    "MSFT": "Microsoft", "AMZN": "Amazon", "SPCX": "SpaceX", "META": "Meta",
    "TSM": "台積電 ADR", "HNHPF": "鴻海 ADR", "ASX": "日月光 ADR",
}

# 對照組：同一家公司的台股與 ADR 可以互看
ADR_PAIRS: tuple[tuple[str, str], ...] = (
    ("2330.TW", "TSM"),
    ("2317.TW", "HNHPF"),
    ("3711.TW", "ASX"),
)

# §10 已知的坑
#   SPCX  2026-06-12 才上市，日線筆數極少 → MA200 不可得，
#         「52 週高點回撤」只能退化成「上市以來高點」，
#         中期／長期評分**回傳「資料不足」，不准硬算**
#   HNHPF 零缺值但**薄流動性**（9/4 只成交 8,200 股，同日 TSM 是 12,276,300 股）
#         → 量價與籌碼指標會失真
#   GOOG  已擇定 GOOG（無投票權）而非 GOOGL，文章要寫明為什麼
MIN_BARS_MID_TERM = 60    # 中期評分至少要這麼多根
MIN_BARS_LONG_TERM = 200  # 長期評分至少要這麼多根

THIN_LIQUIDITY = ("HNHPF",)
