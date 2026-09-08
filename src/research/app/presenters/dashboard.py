"""個股桌面儀表板的 Presenter（ToDo §1.1 第 22 條、§9 Day 27 第 8 項）。

**這一層不認得 SQLite，也不認得 yfinance。** 它拿到的是
`barometer.domain.ports` 的 ScoreHistoryRepository，由 `app/main.py`
（組裝根）注入。`tests/test_layer_boundary.py` 用 AST 掃描守著。

---

**跟 market-barometer 那一側最大的差別：這裡沒有「更新」這個動作。**

那一側有三種動作（load / auto_refresh / force_refresh），因為總經指標各有
各的公布時間，需要盯著。這一側只有 `load()` —— 個股評分是
`tools/fetch_stocks.py` → `tools/score_stocks.py` 跑完寫進去的，
桌面程式**只負責把寫好的東西顯示出來**。

少一個按鈕不是偷懶，是這個 repo 的用法本來就不同：跑完管線才有新分數，
在視窗裡放一顆「重抓」只會讓人以為按了就會變新。

---

**分數一律原樣顯示，不在這裡重算。**

重算一次的話，桌面上的數字就可能跟網頁上的對不起來 ——
同一個問題兩個答案，比沒有答案更難查。
"""
from __future__ import annotations

from barometer.app.presenters.dashboard import ViewRow
from barometer.domain import weighting
from barometer.domain.ports import ScoreHistoryRepository

from research import config as rc
from research.domain import scoring_stock

SCOPE = "stock"
WINDOW = 5  # 五日視窗（§8.1）

# 兩個分頁，跟網頁那側一致。
TABS: dict[str, tuple[str, ...]] = {
    "tw": rc.TW_STOCKS,
    "us": rc.US_STOCKS + rc.ADRS,
}

TAB_TITLES: tuple[tuple[str, str], ...] = (
    ("tw", "台股權值股"),
    ("us", "美股權值股"),
)

# 三期 + 籌碼。**順序固定**，因為使用者是照位置在讀的。
TERMS: tuple[tuple[str, str], ...] = (
    ("short", "短期"), ("mid", "中期"), ("long", "長期"),
)
CHIPS_KEY = "chips"


class StockPresenter:
    def __init__(self, scores: ScoreHistoryRepository) -> None:
        self._scores = scores

    # ---------------- 只讀已寫好的分數，不打網路 ----------------

    def load(self, tab: str = "tw") -> list[ViewRow]:
        rows: list[ViewRow] = []
        for symbol in TABS.get(tab, ()):
            history = self._scores.get_scores(SCOPE, symbol)
            if not history:
                rows.append(
                    ViewRow(
                        key=symbol,
                        label=self._label(symbol),
                        value=None,
                        data_date=None,
                        freq="每日",
                        note="尚未評分（先跑 tools/fetch_stocks.py 與 tools/score_stocks.py）",
                    )
                )
                continue

            latest = history[-1]
            rows.append(
                ViewRow(
                    key=symbol,
                    label=self._label(symbol),
                    value=f"{latest.score:.1f}",
                    data_date=latest.as_of.isoformat(),
                    freq="每日",
                    note=self._note(symbol, latest, history),
                )
            )
        return rows

    # ---------------- 備註欄：三期、籌碼、五日加權、但書 ----------------

    def _note(self, symbol: str, latest, history: list) -> str:
        parts = [self._terms(latest.subscores)]

        # 不足五天就不算 —— `weighted_average` 對長度不是 5 的輸入會丟例外，
        # 而「剛開始跑、只有兩三天分數」是常態，不是異常。
        recent = [r.score for r in history[-WINDOW:]]
        wavg = weighting.weighted_average(recent) if len(recent) == WINDOW else None
        parts.append(
            f"五日加權 {wavg:.1f}" if wavg is not None
            else f"五日加權：資料不足（{len(recent)}/{WINDOW} 天）"
        )

        if symbol in rc.THIN_LIQUIDITY:
            parts.append("薄流動性，量價指標會失真")

        return "｜".join(parts)

    @staticmethod
    def _terms(subscores: dict[str, float]) -> str:
        """三期分項，加上籌碼（只有存在的時候）。

        **`subscores` 裡缺 key 代表「算不出來」，不是 0 分。**

        中期要 60 根日 K、長期要 200 根，SPCX 只有 59 根。硬算出來的數字會
        長得跟其他十四檔一模一樣，沒有人會發現那格是空的 —— 而且 0 分還會
        被當成一個評價。所以這裡顯示成字串。

        籌碼那一維更直接：美股與 ADR 沒有台灣的三大法人資料，
        那一維是**不存在**，所以整項不出現，連「資料不足」都不寫。
        寫了會讓人以為它本來應該有。
        """
        out = [
            f"{label} {subscores[key]:.0f}" if key in subscores
            else f"{label} {scoring_stock.INSUFFICIENT}"
            for key, label in TERMS
        ]
        if CHIPS_KEY in subscores:
            out.append(f"籌碼 {subscores[CHIPS_KEY]:.0f}")
        return "／".join(out)

    @staticmethod
    def _label(symbol: str) -> str:
        name = rc.NAMES.get(symbol, "")
        return f"{symbol} {name}".strip()

    # ---------------- 狀態列 ----------------

    def status(self) -> str:
        """**刻意不是一行「最後更新：…」。**

        15 檔的資料日期不見得是同一天 —— 2026-09-07 是美國勞動節，
        NYSE 不開盤而台股照常。印一個時間戳等於宣稱它們都是那天的。
        """
        dates: set[str] = set()
        n = 0
        for symbols in TABS.values():
            for symbol in symbols:
                history = self._scores.get_scores(SCOPE, symbol)
                if history:
                    dates.add(history[-1].as_of.isoformat())
                    n += 1
        if not dates:
            return "尚未評分 —— 先跑 tools/fetch_stocks.py 與 tools/score_stocks.py"
        return (f"{n} 檔，資料日期 {len(dates)} 種："
                + "、".join(sorted(dates)))
