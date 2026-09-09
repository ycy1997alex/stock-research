# 每日排程的抓取進入點（ToDo §9 Day 24 第 11 項）。
#
# 跟 market-barometer 的 run_daily.ps1 同一個角色，但這邊只有一班：
# 15 檔（台股 5、美股 5、ADR 5）一次抓完。資料層與 market-barometer 共用，
# 這支只是換一組標的餵同一條管線。
#
# 評分不在這裡跑 —— `tools/publish.py` 產頁面的時候會自己算（run_stock_scores），
# 先算一次存起來再算一次只會多一份會過期的中間狀態。
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_daily.ps1

$ErrorActionPreference = "Stop"

$Python = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:STOCKDATA_ROOT = "D:\Research\_stockdata"
$env:PYTHONIOENCODING = "utf-8"

# 這個 wrapper 自己的訊息一律用 ASCII —— 排程任務的 stdout 走系統 ACP（950），
# 中文會變成亂碼。Python 那一側已經設了 PYTHONIOENCODING=utf-8，中文由它印。
Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') START stocks ==="
& $Python (Join-Path $RepoRoot "tools\fetch_stocks.py")
$code = $LASTEXITCODE
Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') END stocks exit=$code ==="

# 單一標的失敗不得讓整批看起來像壞了 —— 這條跟 barometer 那側一致，
# partial 在 fetch_prices.run() 裡已經算成 0。
exit $code
