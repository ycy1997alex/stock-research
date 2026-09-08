# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller .spec —— stock-research 個股桌面儀表（ToDo §1.1 第 22 條、§9 Day 27 第 9 項）。

**跟 market-barometer 那支最大的不同：這支要收兩個 repo 的 src。**
管線核心、加密、渲染、五日加權全部來自 `barometer`，這一側只有個股專屬的
評分與 View。`pathex` 少了 market-barometer 那一條，build 會成功、
exe 會在啟動時死於 `No module named 'barometer'`。

**shioaji 一樣刻意不打包進來**（§12 第 5 條）—— 它是選配相依，只有本機
每日對帳用得到。把一個有下單能力的套件塞進要發出去的 exe 沒有任何好處。

資源檔要進 datas，不然 onefile 解壓到暫存目錄之後 `Path(__file__)` 那一路
會找不到它們：
  - `barometer/storage/schema.sql` —— SqliteRepo.init_schema() 要讀
  - `research/app.ico`             —— 視窗標題列與工作列那兩面

**驗收不是 `exit 0`。** 看的是「build log 裡零個 `Library not found`」
加上「實際啟動 exe，視窗真的出現」—— 兩種情況都 exit 0（§10）。
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# --- conda 環境的原生 DLL 在 <sys.prefix>\Library\bin，那不在 PyInstaller 的
# 相依搜尋路徑上。少了這一行，build 會成功、exe 會在啟動時死於
# `ImportError: DLL load failed while importing _ctypes`。
# CI 上跑的是官方 python，這個目錄不存在，多一段 PATH 沒有副作用。
os.environ["PATH"] = (
    os.path.join(sys.prefix, "Library", "bin") + os.pathsep + os.environ["PATH"]
)

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
# 管線核心在隔壁 repo。這一條掉了，exe 一啟動就死在 `No module named 'barometer'`
BAROMETER_SRC = ROOT.parent / "market-barometer" / "src"

if not (BAROMETER_SRC / "barometer").is_dir():
    raise SystemExit(
        f"找不到 barometer 的原始碼：{BAROMETER_SRC}\n"
        "這支 spec 需要 market-barometer 與 stock-research 並排放在同一層。"
    )

# --- numpy 2.5 的子模組要整包收，不能靠內建 hook ---
# 只靠內建 hook 的話，build 會成功、exe 會在啟動時死在
# `No module named 'numpy._core._exceptions'`，而 pandas 把它轉譯成一句
# 沒什麼幫助的「Unable to import required dependency numpy」。
# **這是「測試全綠也抓不到」最典型的一種** —— 測試跑的是 env 裡的 numpy，
# 不是打包進去的那一份。
np_datas, np_binaries, np_hidden = collect_all("numpy")

# ttkbootstrap 的主題定義是資料檔，不收的話 exe 會找不到 darkly。
# 它相依 PIL —— PIL 一旦被放進 excludes，build 照樣 exit 0、
# 零個 Library not found，一啟動才死在 `No module named 'PIL'`。
bs_datas, bs_binaries, bs_hidden = collect_all("ttkbootstrap")

a = Analysis(
    [str(SRC / "research" / "app" / "main.py")],
    pathex=[str(SRC), str(BAROMETER_SRC)],
    binaries=np_binaries + bs_binaries,
    datas=[
        (str(BAROMETER_SRC / "barometer" / "storage" / "schema.sql"),
         "barometer/storage"),
        # 圖示也要進 datas，不只是 icon= —— 前者給執行中的視窗與工作列用，
        # 後者只決定 Explorer 裡那顆。兩個來源不同，缺一個就會有一面不對。
        (str(SRC / "research" / "app.ico"), "research"),
    ] + np_datas + bs_datas,
    hiddenimports=[
        "research.app.views.dashboard",
        "research.app.presenters.dashboard",
        "ttkbootstrap",
    ] + np_hidden + bs_hidden,
    hookspath=[],
    runtime_hooks=[],
    # ⚠️ excludes 會過期，而且過期的方式是「exe 打得起來、跑不起來」。
    # 換 UI 套件或加相依之後要重驗這張清單。
    excludes=[
        "shioaji", "matplotlib", "scipy", "IPython", "jupyter",
        "pytest", "setuptools", "PyQt5", "PySide6",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="stock-research",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=False：這是 GUI 程式，不要在背後開一個黑窗。
    # 打包壞掉時改成 True 重建一次，traceback 才看得到。
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 多解析度圖示（16/24/32/48/64/128/256），由 tools/make_icon.py 產生。
    # 這顆決定的是 **Explorer 裡** 那一面；標題列與工作列在 app/main.py 設。
    icon=str(SRC / "research" / "app.ico"),
)
