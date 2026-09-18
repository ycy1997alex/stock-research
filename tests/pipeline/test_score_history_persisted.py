"""個股分數的歷史也要有人在寫（2026-09-18，ToDo §10）。

驗收：**`publish.py` 跑完之後，`score_history` 必須有一筆 `as_of` 等於該 scope
最新交易日的分數。**

這一側失效的方式跟 market-barometer 那側不同，但結果一樣：`tools/publish.py`
直接呼叫 `run_stock_scores.score_series()`（純函式）把數字放進頁面，
**從來沒走過會落地的 `run()`**。所以 `score_history` 的 `stock` scope 停在
2026-09-04 —— 那是唯一一次手動跑 `scores_stock` 的日子。

`tools/run_daily.ps1` 的註解寫著「評分不在這裡跑 —— publish.py 產頁面的時候
會自己算」。那句話是對的，缺的是後半句：**算完要存下來。**
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLISH = ROOT / "tools" / "publish.py"


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                out.add(f"{node.func.value.id}.{node.func.attr}")
    return out


def test_publish_persists_the_scores_it_just_computed():
    calls = _calls(PUBLISH)
    assert "run_stock_scores.score_series" in calls, (
        "先確認這條測試掃得到東西 —— 掃不到的話下面那句會白綠"
    )
    assert "run_stock_scores.run" in calls, (
        "tools/publish.py 只算不存 —— 頁面正常，但 score_history 不會前進"
    )
