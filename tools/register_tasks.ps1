# 把這個 repo 的排程宣告在一個地方（ToDo §1 第 3 條、§9 Day 27 第 8 項）。
#
# 兩個任務，跟 market-barometer 那六個各自獨立註冊 —— 兩個 repo 在程式上有
# 相依（資料層共用），排程上刻意不互相呼叫：一邊掛掉不該把另一邊也拖下水。
#
# **執行前會先把現有任務的定義匯出備份**，路徑印在畫面上。
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_tasks.ps1
#
# 驗證：`Get-ScheduledTaskInfo -TaskName Research-Publish`，看 NextRunTime。

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $RepoRoot "tools"

# 時刻表的理由：
#   18:10 抓 15 檔 —— 排在 Barometer-Daily-TW（18:00）之後。美股那五檔拿到的是
#         昨夜收盤，跟 barometer 早上 09:00 抓到的是同一根，不會比較舊
#   22:45 發布 —— 排在 Barometer-Chips-TW-Late（22:30）與 Barometer-Publish
#         （22:40）之後：個股評分要吃三大法人，等籌碼面全部落地再產頁面
$Tasks = @(
    @{ Name = "Research-Daily";   At = "18:10"; Script = "run_daily.ps1";        Desc = "stock-research daily fetch (15 symbols)" },
    @{ Name = "Research-Publish"; At = "22:45"; Script = "publish_and_push.ps1"; Desc = "stock-research publish + push docs/" }
)

# --- 備份現有定義 ---
$backupDir = Join-Path $env:STOCKDATA_ROOT "runlog"
if (-not $env:STOCKDATA_ROOT) { $backupDir = $env:TEMP }
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }
$backup = Join-Path $backupDir ("scheduled_tasks_research_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".xml")

$existing = @()
foreach ($t in $Tasks) {
    try { $existing += (Export-ScheduledTask -TaskName $t.Name -ErrorAction Stop) } catch { }
}
if ($existing) {
    Set-Content -Path $backup -Value ($existing -join "`r`n") -Encoding utf8
    Write-Output "backup: $backup ($($existing.Count) task(s))"
} else {
    Write-Output "backup: nothing to back up (no task registered yet)"
}

# --- 註冊 ---
# 這是筆電：電池上也要跑，跑到一半拔電源也不要停 —— New-ScheduledTaskSettingsSet
# 的預設值兩個都相反，不明寫的話任務會在沒插電的時候安靜地不跑。
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive

foreach ($t in $Tasks) {
    $script = Join-Path $Tools $t.Script
    if (-not (Test-Path $script)) { throw "missing script: $script" }

    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $script + '"'))
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($argList -join " ")
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At

    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Description $t.Desc -Force | Out-Null
    Write-Output ("registered {0,-18} {1}  {2}" -f $t.Name, $t.At, $t.Script)
}

Write-Output ""
Get-ScheduledTask -TaskName ($Tasks | ForEach-Object { $_.Name }) |
    ForEach-Object {
        $i = $_ | Get-ScheduledTaskInfo
        "{0,-18} State={1,-8} Next={2}" -f $_.TaskName, $_.State, $i.NextRunTime
    }
