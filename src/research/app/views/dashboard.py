"""個股桌面儀表板的 View（ToDo §1.1 第 22 條、§9 Day 27 第 8 項）。

**這一層只認 Presenter，不認 SQLite**
（`tests/test_layer_boundary.py` 用 AST 掃描守著 §3.2）。

---

**跟 market-barometer 那一側刻意不同的兩件事：**

1. **沒有「強制重抓」按鈕。** 那一側有，因為總經指標各有各的公布時間，
   需要盯著。這一側的分數是 `tools/fetch_stocks.py` → `tools/score_stocks.py`
   跑完寫進去的 —— 放一顆重抓鈕只會讓人以為按了就會變新。
   這裡的按鈕是「重新載入」，它**只重讀本機資料庫，一次網路都不打**。

2. **沒有背景執行緒。** 那一側要打十幾個網路請求，跑在主執行緒上會讓視窗
   凍住十幾秒。這一側只讀 15 檔的 SQLite，是毫秒級的事，丟到執行緒裡只是
   多一層出錯的地方。**沒有慢操作就不要有併發** —— 這是簡化，不是省略。

保留的是關窗處理：`after` 的 id 要記下來、關窗時要全部取消，
少了這步關窗後那些 callback 會炸 `invalid command name`。

視窗尺寸沿用 `barometer.app.geometry`（上下 3%~87%、左右 3%~97%），
**不另寫一份** —— 兩份算式遲早會有一份先改。

widget 一律用 ttkbootstrap，不跟原生 `tk.*` 混用（混用的樣式會對不起來）。
"""
from __future__ import annotations

import tkinter as tk

import ttkbootstrap as bs
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X, Y

from barometer.app.geometry import shrink_for_frame, window_box

from research.app.presenters.dashboard import TAB_TITLES, StockPresenter

COLUMNS = (
    ("label", "標的", 200),
    ("value", "總分", 90),
    ("data_date", "資料日期", 110),
    ("freq", "頻率", 70),
    ("note", "三期分項與但書", 620),
)

TITLE = "stock-research —— 台美權值股三期評分"

# 頁尾那一行。**每一個出口都要掛**，桌面這個出口也不例外。
DISCLAIMER = "五個交易日只有五個點，一律是定性觀察。本頁不構成投資建議。"


class StockDashboardWindow:
    def __init__(self, root: tk.Misc, presenter: StockPresenter) -> None:
        self.root = root
        self.presenter = presenter
        self._after_ids: set[str] = set()
        self._closing = False

        root.title(TITLE)
        self._box = window_box(root.winfo_screenwidth(), root.winfo_screenheight())
        root.geometry(self._box.as_geometry())
        root.minsize(720, 480)

        top = bs.Frame(root, padding=(10, 8))
        top.pack(fill=X)
        # 「重新載入」而不是「重抓」—— 它只重讀本機資料庫。
        # 名字要對得上行為，不然使用者會以為按了就有新資料。
        self.btn = bs.Button(top, text="重新載入（不打網路）", bootstyle="primary",
                             command=self._reload_all)
        self.btn.pack(side=LEFT)
        bs.Label(top, text="分數由管線寫入，這個視窗只負責顯示").pack(side=LEFT, padx=12)

        self.nb = bs.Notebook(root)
        self.nb.pack(fill=BOTH, expand=True, padx=10, pady=(4, 6))
        self.trees: dict[str, bs.Treeview] = {}
        for key, title in TAB_TITLES:
            frame = bs.Frame(self.nb)
            self.nb.add(frame, text=title)
            self.trees[key] = self._make_tree(frame)

        self.status = bs.Label(root, text="", anchor="w", padding=(10, 4))
        self.status.pack(fill=X)
        bs.Label(root, text=DISCLAIMER, anchor="w", padding=(10, 0, 10, 6),
                 bootstyle="secondary").pack(fill=X)

        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._reload_current())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._reload_all()
        self._fit_outer_edges()

    def _fit_outer_edges(self) -> None:
        """把標題列與邊框的厚度扣掉，讓**看得到的邊界**落在 3%~87% / 3%~97%。

        外框有多厚只有視窗實際開出來之後才量得到，所以這一步必須在
        `update_idletasks()` 之後做，而且只做一次。
        """
        try:
            self.root.update_idletasks()
            frame_w = max(0, self.root.winfo_rootx() - self.root.winfo_x()) * 2
            frame_h = (max(0, self.root.winfo_rooty() - self.root.winfo_y())
                       + frame_w // 2)
            if frame_w == 0 and frame_h == 0:
                return
            self.root.geometry(
                shrink_for_frame(self._box, frame_w, frame_h).as_geometry()
            )
        except tk.TclError:
            pass  # 量不到就維持原尺寸，不值得為了幾個 pixel 讓視窗開不起來

    # ---------------- 版面 ----------------

    def _make_tree(self, parent) -> bs.Treeview:
        tree = bs.Treeview(parent, columns=[c[0] for c in COLUMNS],
                           show="headings")
        for name, title, width in COLUMNS:
            tree.heading(name, text=title)
            tree.column(name, width=width, anchor="w")
        vs = bs.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        vs.pack(side=RIGHT, fill=Y)
        return tree

    def _current_key(self) -> str:
        idx = self.nb.index(self.nb.select()) if self.nb.tabs() else 0
        return TAB_TITLES[idx][0]

    def _fill(self, key: str) -> None:
        tree = self.trees[key]
        tree.delete(*tree.get_children())
        for r in self.presenter.load(key):
            tree.insert("", "end", values=(
                r.label, r.value or "—", r.data_date or "—", r.freq, r.note,
            ))

    def _reload_current(self) -> None:
        if self._closing:
            return
        self._fill(self._current_key())
        self.status.config(text=self.presenter.status())

    def _reload_all(self) -> None:
        if self._closing:
            return
        for key, _ in TAB_TITLES:
            self._fill(key)
        self.status.config(text=self.presenter.status())

    # ---------------- 關窗 ----------------

    def on_close(self) -> None:
        """先取消所有排程中的 after，才 destroy。

        順序不能換 —— 反過來的話，destroy 之後那些 callback 會炸
        `invalid command name`。這一側沒有背景執行緒，所以不必 join。
        """
        self._closing = True
        for aid in self._after_ids:
            try:
                self.root.after_cancel(aid)
            except tk.TclError:
                pass
        self._after_ids.clear()
        self.root.destroy()
