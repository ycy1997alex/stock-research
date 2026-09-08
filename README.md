# stock-research

台美權值股的**本機評分管線**。個人使用。

> ⚠️ **這個 repo 是 public，內容靠頁面加密擋住 —— 但那是「加了鎖的公開頁面」，不是「私密頁面」。**
> 密文放在 public repo，任何人可以下載後離線慢慢猜密碼，沒有速率限制。放進去的東西要能承受萬一被看到。

---

## Overview

- **標的**：台股權值股 5 檔（顯示單位「張」）、美股權值股 7 檔、台灣 ADR 3 檔（顯示單位「股」）。
- **資料層與 `market-barometer` 共用**（同一個 `STOCKDATA_ROOT`）—— 抓一次餵兩個站，避免重複打 API。
- **管線核心來自 `market-barometer`**，這裡只放個股專屬的評分與渲染。
- **鎖**：兩層（Key × 2 配 Password × 2），而 market-barometer 是一層。
- **兩個介面**：桌面程式（`.exe`）與加密網頁，看的是同一份分數。

### 與 market-barometer 的界線

| | market-barometer | stock-research |
|---|---|---|
| 定位 | 30 天挑戰的成果，公開 | 自己實際在用的 |
| 標的 | 指數與 ETF | 具名個股 |
| 買賣建議 | **完全不放** | 可以有 |
| 程式碼 | 管線核心 | 只有個股專屬的評分與渲染 |
| 桌面程式 | 操作台：有「強制重抓」，**會打網路** | 顯示器：只有「重新載入」，**不打網路** |

具名個股的數值、評分、建議**只出現在這裡**。挑戰內容那邊只講「什麼是權值股、名單從哪裡查、為什麼是這幾檔」這些觀念。

---

## Architecture

結構刻意與 `market-barometer` 對稱，並沿用它的分層與 Ports：

```
src/research/
├─ config.py                    ← 標的清單與已知的坑
├─ app.ico                      ← 多解析度圖示（由 tools/make_icon.py 產生）
├─ domain/
│  └─ scoring_stock.py          ← 三期評分 + 籌碼面第四維度
├─ datasources/
│  └─ chips_tw.py               ← 從 T86 抽出個股的三大法人買賣超
├─ pipeline/
│  └─ run_stock_scores.py       ← 逐日回算 + 五日加權（權重與大盤共用）
├─ render/
│  └─ page.py                   ← 兩個分頁：台股權值股 / 美股權值股
└─ app/                         ← 桌面 TTK（唯讀顯示，不打網路）
   ├─ presenters/dashboard.py   ← StockPresenter
   ├─ views/dashboard.py        ← StockDashboardWindow
   └─ main.py                   ← 組裝根（唯一認得 storage 的地方）

tools/
├─ fetch_stocks.py              ← 抓 15 檔
├─ score_stocks.py              ← 三期評分、五日加權、變化與平滑化
├─ make_icon.py                 ← 產生 app.ico（一次性）
└─ publish.py                   ← 兩層鎖發布（Key + Password）

packaging/research.spec          ← PyInstaller onefile
```

Domain 層一樣是純規則、零 I/O；表現層一樣不得 import storage ——
`tests/test_layer_boundary.py` 用 AST 掃描守著，不靠自律。

**加密、渲染、五日加權全部沿用 `market-barometer`**，這一側只換一組標的與
一套評分。兩個站用同一套機制是刻意的 —— 各寫一份的話，改一邊就會忘記另一邊。

與 market-barometer 唯一的行為差異是 `enforce_lint=False`：這個 repo
**可以**有買賣與短中長線建議，那條線畫在內容本身，不畫在鎖上。

### 對照組設計

同一家公司的台股與 ADR 可以互看：`2330.TW` vs `TSM`、`2317.TW` vs `HNHPF`、`3711.TW` vs `ASX`。

---

## 已知的坑（2026-09-06 實測）

| 標的 | 實測 | 處置 |
|---|---|---|
| `SPCX` | 只有 **59 根**日線（2026-06-12 上市） | MA200 不可得，「52 週高點回撤」退化成「上市以來高點」。中期／長期評分**回傳「資料不足」，不准硬算** |
| `HNHPF` | 零缺值，但 9/4 只成交 **8,200 股**（同日 TSM 是 12,276,300 股） | 不是壞資料，是**薄流動性** —— 量價與籌碼指標會失真 |
| `GOOG` vs `GOOGL` | 兩檔價格不同，GOOG 無投票權 | 已擇定 `GOOG` |
| 張／股 | T86 單位是**股**、K 線量是**張** | 換算寫在資料層，顯示層才轉 |

---

## Setup & run

```powershell
conda activate barometer
pip install -e ../market-barometer      # 管線核心
pip install -e ".[dev]"

$env:STOCKDATA_ROOT = "D:\Research\_stockdata"
python tools/fetch_stocks.py            # 抓 15 檔
python tools/score_stocks.py            # 三期評分 + 五日加權
python tools/publish.py                 # 明文 → 兩層鎖加密 → docs/
python ../market-barometer/tools/verify_publish.py stock-research
pytest -q
```


> ⚠️ **`conda activate` 在某些 PowerShell 環境會靜默失效。** 如果 shell 沒有被 `conda init` 過（作者這台就是），`conda activate barometer` 會回傳 exit 0 然後什麼都沒做 —— `python` 仍然指向 base，**不會有任何錯誤訊息**，直到後面某個套件找不到才爆出來。
>
> 確認方式：`conda activate` 之後跑 `python -c "import sys; print(sys.executable)"`，路徑裡要有 `envs\barometer`。不是的話，改用 `conda run -n barometer python ...`，或先掛 hook：
>
> ```powershell
> (& "C:\Users\Alex\anaconda3\Scripts\conda.exe" shell.powershell hook) | Out-String | Invoke-Expression
> conda activate barometer
> ```

### 桌面程式

```powershell
python -m research.app.main
```

沒有 `pip install -e` 的話要自己給路徑（兩個 repo 的 `src` 都要）：

```powershell
$env:PYTHONPATH = "D:\Research\stock-research\src;D:\Research\market-barometer\src"
```

**這支程式一次網路都不打**，它只顯示上面那兩支 tools 寫好的分數。
所以按鈕叫「重新載入」而不是「重抓」。

打包成 exe：

```powershell
python -m PyInstaller --clean --noconfirm packaging/research.spec
```

產出 `dist\stock-research.exe`（41.9 MB）。**驗收看的是「build log 裡零個
`Library not found`」加上「實際啟動 exe、視窗真的出現」，不是 `exit 0`**
—— 兩種情況都 exit 0。

`packaging/research.spec` 需要 `market-barometer` 與 `stock-research`
**並排放在同一層**；找不到隔壁 repo 它會直接讓 build 失敗，
而不是產出一顆啟動就死在 `No module named 'barometer'` 的 exe。

發布憑證在 `%STOCKDATA_ROOT%\secrets\publish.json`，**不在這個 repo 裡，也不
可以放進來** —— 這是 public repo，進了版控就撤不回來。

⚠️ **這個站實質上是一層鎖。** 兩層鎖的外層 Key 與 market-barometer 的 Password
有字串重疊，那邊任何一組流出，這邊的 Key 就跟著流出。所以安全性等於內層那兩個
Password 的強度。放進來的東西要能承受萬一被看到。

---

## Dependencies

| 套件 | 用途 |
|---|---|
| `barometer` | 管線核心（`pip install -e ../market-barometer`）：資料層、加密、渲染、五日加權全部來自它 |
| `pytest` | 測試（`[dev]`） |

**這個 repo 刻意沒有自己的資料源與加密實作。** 兩個站用同一套機制，各寫一份
的話改一邊就會忘記另一邊。這裡只有個股專屬的評分與 T86 的抽取。

---

## Configuration

| 項目 | 值 |
|---|---|
| `STOCKDATA_ROOT` | 資料根目錄，**與 market-barometer 共用**，預設 `D:\Research\_stockdata` |
| 發布憑證 | `%STOCKDATA_ROOT%\secrets\publish.json` 的 `stock-research` 區塊（兩層鎖，2 × 2 = 4 組） |
| 金鑰 | 這個 repo 不直接用任何外部金鑰；shioaji 與 FRED 由 `barometer` 那側處理 |

`Key/` 與 `secrets/` 都被 `.gitignore` 擋著。**這是 public repo，不要用
`git add -f` 繞過。**

---

## 免責

**不構成投資建議。** 單次執行的觀察一律是定性觀察，不是統計證據。
