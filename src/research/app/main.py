"""個股桌面程式的組裝根（ToDo §1.1 第 22 條、§3.2）。

**這是唯一一個可以認得 storage 的地方。** Ports & Adapters 的形狀就是這樣：
介面在內層、實作在外層，把兩者接起來的組裝根待在最外面。
`views/` 與 `presenters/` 一個都不准 import 它
（`tests/test_layer_boundary.py` 用 AST 掃描守著，而且會反過來檢查
這支檔案**真的**有 import —— 沒有的話代表接線搬到表現層去了）。

跑法：
    python -m research.app.main

---

**資料層與 market-barometer 共用同一個 `STOCKDATA_ROOT`**（§1 第 8 條）。
所以這裡用的是 `barometer.config` 的路徑解析與同一個 `market.db`，
不另外開一個資料庫 —— 兩份資料庫遲早會有一份是舊的。

**這支程式一次網路都不打。** 它只讀 `tools/score_stocks.py` 寫好的分數。
真正打網路的是那兩支 tools。

視窗建立順序有兩件事不能反過來（跟 market-barometer 同樣的坑）：

1. `SetCurrentProcessExplicitAppUserModelID` 要在 root 建立**之前**呼叫，
   否則工作列會把它歸到 Python 直譯器底下。
2. `bs.Window()` 要傳 `iconphoto=None`，否則 ttkbootstrap 自己的 logo 會蓋掉
   .ico，而且不會有任何錯誤訊息。
"""
from __future__ import annotations

import sys

import ttkbootstrap as bs

from barometer import config as bconfig
from barometer.storage.sqlite_repo import SqliteRepo

from research.app.presenters.dashboard import StockPresenter
from research.app.views.dashboard import StockDashboardWindow

APP_ID = "alexyu.stock-research"
THEME = "darkly"
ICON_NAME = "app.ico"


def _set_taskbar_identity() -> None:
    """讓工作列認得這支程式，而不是把它歸到 Python 直譯器底下。

    **ID 跟 market-barometer 不同** —— 相同的話兩支程式會被 Windows 併成
    工作列上的同一格，而它們是兩支不同的程式。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001 — 設不了圖示不該讓程式開不起來
        pass


def _enable_dpi_awareness() -> float:
    """宣告自己看得懂 DPI，回傳縮放倍率。**必須在建立 root 之前呼叫。**

    不宣告的話 Windows 會給一個縮放後的邏輯螢幕尺寸（150% 的 1920×1080 會
    回報成 1280×720），「視窗佔螢幕幾 %」就會差個 0.5~1%，而且字會糊掉。
    """
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return (dpi or 96) / 96.0
    except Exception:  # noqa: BLE001
        return 1.0


def _icon_path():
    """圖示路徑。打包之後 datas 會被解壓到暫存目錄，所以不能寫死相對路徑。

    `barometer.config.resource_path` 解的是 barometer 自己的資源；
    這支程式的圖示放在 `research/` 底下，所以自己算一次。
    """
    from pathlib import Path

    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "research" / ICON_NAME
    return Path(__file__).resolve().parents[1] / ICON_NAME


def _apply_icon(root) -> None:
    path = _icon_path()
    if not path.exists():
        return
    try:
        root.iconbitmap(str(path))
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    bconfig.ensure_dirs()
    repo = SqliteRepo(bconfig.db_path())
    repo.init_schema()

    _set_taskbar_identity()
    scale = _enable_dpi_awareness()      # 一定要在 bs.Window() 之前
    root = bs.Window(themename=THEME, iconphoto=None)
    if scale != 1.0:
        root.tk.call("tk", "scaling", scale * 96 / 72)
    _apply_icon(root)

    try:
        StockDashboardWindow(root, StockPresenter(repo))
        root.mainloop()
    finally:
        # 不論正常關窗還是未攔到的例外，連線都要關掉
        repo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
