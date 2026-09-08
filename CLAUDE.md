# CLAUDE.md

給 Claude Code 在這個 repo 裡工作時看的。**動任何東西之前先看這份。**

| 文件 | 給誰看 | 內容 |
|---|---|---|
| `README.md` | 人 | 這是什麼、怎麼跑 |
| **`CLAUDE.md`（這份）** | Claude Code | 動它的時候要注意什麼 |
| `UI_README.md` | 要改介面的人 | 兩個介面怎麼組起來、四個 UI 決策的理由 |
| `使用者指引.html` | **終端使用者** | 隨 `.exe` 一起交付。**裡面不得出現任何開發脈絡** —— 不提檔名、路徑、程式、指令、開發工具 |

**這份是自足的** —— 不必先去讀 market-barometer 的 CLAUDE.md。兩個 repo 在程式上有相依（管線核心來自那邊），但**文件上各自完整**。

## 這是什麼

台美權值股的**本機評分管線**。個人使用，內容不進 iThome 挑戰的文章。

管線核心、加密、渲染、五日加權**全部沿用 `market-barometer`**，這一側只換一組標的與一套個股評分。兩個站用同一套機制是刻意的：各寫一份的話，改一邊就會忘記另一邊。

## 紅線（違反任一條，這套東西就沒有意義了）

1. **密碼與金鑰不進 repo。** 這是 public repo。`secrets/`、`Key/` 已被 `.gitignore` 擋著，不要用 `git add -f` 繞過。**也不要把金鑰印出來。**
2. **明文 HTML 不進 git。** 只寫進 `%STOCKDATA_ROOT%\build\`，只有密文進 `docs/`。
3. **每次發布重新產生 salt / IV / CEK。** AES-GCM 重用 IV 可以直接還原明文。
4. **原始價格序列不進任何 repo**，連加密的也不放（yfinance 的條款）。
5. **自動修復歷史資料一律不做。** 比對只記旗標，重抓永遠是手動的。半夜自己重寫歷史卻沒人知道，比壞掉還糟。
6. **表現層不得 import `storage/` 或 `datasources/`。** `tests/test_layer_boundary.py` 用 AST 掃描守著，而且會**反過來**檢查 `app/main.py` 真的有 import 資料層 —— 沒有的話代表接線偷偷搬到表現層去了。
7. **不產生「保證」「一定」這種語氣，每一頁都掛「不構成投資建議」。** 這一側**可以**把分數翻成一個行動描述，那是它與 market-barometer 唯一的內容差異；但「可以有建議」不代表可以隨便寫。

## 寫程式的規矩

**先寫測試，再寫實作。** 每一項需求的「驗收句」就是規格，測試跟著規格先寫。 **跑一次確認它紅過，才有意義** —— 用 `pytest.importorskip` 之類的東西讓整份測試被跳過，會得到一個什麼都沒守到的綠燈。

**算不出來就說算不出來。** 這個專案最常出現的判斷是「這一格沒有資料」，處置一律是回 `INSUFFICIENT` / `None` 並附上原因，**絕不回 0**。 0 會被平均進去，把「不知道」變成「很糟」。

**判定看變化，不看水位。** 拿相鄰兩列的值去比會永遠亮燈。

**邊界規則寫成測試，不寫成註解。** 註解半年後只是一段沒人看的文字。

**單位不互相換算**：股（`_shares`）、張（`_lots`）。欄位名一律帶單位字尾。內部一律存「股」，只在顯示層換算成「張」。

**兩個市場的日期不會對齊。** 台股一年 243~244 根、美股 252 根； 2026-09-07 是美國勞動節，台股照常。任何假設兩市場對齊的程式碼都會安靜地錯位。

## 環境與指令

這台機器**有 conda**（26.1.1，已在 PATH 上），這個專案用 **`barometer`** 環境（`C:\Users\Alex\anaconda3\envs\barometer`，Python 3.13.15）—— **跟 market-barometer 同一個環境**，因為管線核心就是從那邊裝進來的。

⚠️ **`conda activate` 在這台的 PowerShell 裡不會生效。** 沒有 conda init 過的 profile，`conda activate barometer` 會回傳 exit 0 然後什麼都沒做，`python` 仍然指向 base。**它不報錯，只是安靜地用錯環境。** 用底下的絕對路徑，或 `conda run -n barometer python ...`；真要 activate 得先跑 `(& "C:\Users\Alex\anaconda3\Scripts\conda.exe" shell.powershell hook) | Out-String | Invoke-Expression`。

```powershell
$py = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"
$env:STOCKDATA_ROOT = "D:\Research\_stockdata"     # 與 market-barometer 共用同一個資料層

& $py -m pytest -q                                  # 測試
& $py tools/fetch_stocks.py                         # 抓 15 檔
& $py tools/score_stocks.py                         # 三期評分 + 五日加權
& $py tools/publish.py                              # 明文 → 兩層鎖加密 → docs/
& $py ../market-barometer/tools/verify_publish.py stock-research

# 桌面程式（唯讀顯示，一次網路都不打）
$env:PYTHONPATH = "D:\Research\stock-research\src;D:\Research\market-barometer\src"
& $py -m research.app.main

# 打包
& $py -m PyInstaller --clean --noconfirm packaging/research.spec   # → dist\stock-research.exe
```

同樣要加 `PYTHONIOENCODING=utf-8`。

安裝時 `pip install -e ../market-barometer` 先裝管線核心。 **目前這個 env 兩個套件都沒有 `pip install -e`**，測試靠 `pyproject.toml` 的 `pythonpath` 設定跑；直接 `python -m` 執行則要自己給 `PYTHONPATH`。

## 與 market-barometer 的差別

| | market-barometer | 這裡 |
|---|---|---|
| 買賣建議 | **完全不放**，`enforce_lint=True` 擋著 | **可以有**，`enforce_lint=False` |
| 鎖 | 一層（Password） | 兩層（Key + Password，2×2 = 4 組） |
| 標的 | 指數與 ETF | 個股（台股 5 + 美股 7 + ADR 3） |
| 桌面程式 | 操作台：「強制重抓」**會打網路**，有背景執行緒 | 顯示器：「重新載入」**不打網路**，沒有執行緒 |

**桌面程式那一列不是省略，是設計。** 分數由 `tools/score_stocks.py` 寫入，視窗只負責顯示。放一顆「重抓」會讓人以為按了就有新資料 —— 名字要對得上行為。沒有慢操作就不要有併發：讀 15 檔 SQLite 是毫秒級，丟到執行緒裡只是多一層會出錯的地方。

**「可以有建議」不代表可以隨便寫。** 這一側仍然不產生「保證」「一定」這種語氣，而且每一頁還是掛「不構成投資建議」。差別只在它可以把分數翻成一個行動描述，market-barometer 連那句都不生成。

## 打包這支 exe 最容易出事的地方

**`pathex` 要同時給兩個 repo 的 `src`。** 少了 market-barometer 那一條， build 會成功、exe 會在啟動時死於 `No module named 'barometer'`。 `packaging/research.spec` 開頭有一段檢查，找不到隔壁 repo 就直接讓 build 失敗，而不是產出一顆跑不起來的 exe。

**驗收不是 `exit 0`** —— 看的是「build log 裡零個 `Library not found`」加上「實際啟動 exe、視窗真的出現」。兩種情況都 exit 0。

AppUserModelID 是 `alexyu.stock-research`，跟 market-barometer **刻意不同** —— 相同的話 Windows 會把兩支程式併成工作列上的同一格。

## 這裡最容易出事的地方

**算不出來的那幾格特別多，而且特別容易被硬算。**

- `SPCX` 2026-06-12 才上市，只有 59 根日 K。**中期（需 60 根）與長期（需 200 根）一律回「資料不足」，不准硬算。** 硬算出來的數字會長得跟其他十四檔一模一樣，沒有人會發現那格是空的，而且 0 分會被平均進總分。
- `HNHPF` 零缺值但**薄流動性**（單日曾只成交 8,200 股）。照算，但必須掛上但書。
- 美股與 ADR **沒有台灣的三大法人資料**，籌碼面那一維就是不存在，不是 0 分。

**算不出來要怎麼說，分兩種**（2026-09-08 定案，跟 barometer 那側一致）： UI 回 `None` 並標「資料不足（N/5 天）」，因為畫面不能整頁掛掉；管線**直接 raise**，因為安靜產出一份少了幾檔的結果比整支失敗糟得多。管線中止時要**記完 runlog 再重拋** —— 沒有紀錄的失敗，事後跟「排程根本沒觸發」長得一模一樣。

**個股的籌碼面跟指數／ETF 讀法不同。** 三大法人買賣超套在個股上是最直覺的那個讀法；套在 ETF 上多半是套利與申贖；套在加權指數上是全市場資金流向。同一個數字三種意思。

**T86 一天只抓一次。** 它一次回全市場一萬多檔，抽出要的那五檔就好。五檔各打一次 = 一天多打四次註定重複的請求。

## 安全性的實話

⚠️ **這個站實質上是一層鎖。** 兩層鎖的外層 Key 與 market-barometer 的 Password 有字串重疊，那邊任何一組流出（它的密碼本來就要印在文章上給讀者用），這裡的外層 Key 就跟著流出。安全性等於內層那兩個 Password 的強度。

**「私有 ≠ 可以對外分享」。** 內容一次「傳給朋友看」，上面所有前提就失效。放進來的東西要能承受萬一被看到。

## Git

**不要主動 commit / push。** commit 一律由作者發動。工作到了 commit 點就說一句，然後把指令印出來（`/git-commit`）—— **印出指令就是交付，執行是作者的事。**
