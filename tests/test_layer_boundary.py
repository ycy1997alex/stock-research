"""表現層不得認得資料層（ToDo §3.2、§12 第 7 條）。

market-barometer 那側有一份一模一樣的守衛。這個 repo 原本沒有 `app/`，
所以也沒有這份測試；§1.1 第 22 條加了桌面程式之後，同一條界線就得同樣守著。

**用 AST 掃描，不用 grep。** grep 會被字串、註解、以及跨行的 import 騙過去；
AST 看的是真的 import 節點。

界線本身：`app/views/`、`app/presenters/`、`render/` 這三處不得 import
`storage` 或 `datasources`。組裝根 `app/main.py` 是唯一的例外 ——
Ports & Adapters 的形狀就是「介面在內層、實作在外層、把兩者接起來的那個點
待在最外面」。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "research"

# 這幾個資料夾底下的每一支檔案都受管
GUARDED = ("app/views", "app/presenters", "render")

# 不准出現的頂層套件（含 barometer 那一側的，跨 repo 一樣算破口）
FORBIDDEN = ("storage", "datasources")


def _guarded_files() -> list[Path]:
    out: list[Path] = []
    for folder in GUARDED:
        d = SRC / folder
        if d.is_dir():
            out.extend(p for p in d.rglob("*.py") if p.name != "__init__.py")
    return sorted(out)


def _imported_modules(tree: ast.AST) -> list[str]:
    """這支檔案 import 了哪些模組（含 `from x.y import z` 的 `x.y`）。"""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_there_is_something_to_guard():
    """守衛本身不能因為資料夾改名就安靜地變成零檔案通過。

    這一條看起來多餘，但少了它，把 `views/` 改名成 `view/` 之後
    整份測試會變成「掃了 0 個檔案，全過」—— 綠燈，而且什麼都沒守到。
    """
    assert _guarded_files(), f"{GUARDED} 底下一支檔案都沒有，界線沒有被守到"


@pytest.mark.parametrize("path", _guarded_files(), ids=lambda p: p.name)
def test_presentation_layer_does_not_import_data_layer(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    hits = [
        mod
        for mod in _imported_modules(tree)
        for part in mod.split(".")
        if part in FORBIDDEN
    ]

    assert not hits, (
        f"{path.relative_to(SRC)} import 了資料層：{sorted(set(hits))}。"
        "表現層只能認 domain 的 Port，實作由 app/main.py 注入。"
    )


def test_assembly_root_is_the_only_place_that_knows_both():
    """`app/main.py` 是唯一可以同時認得兩邊的地方 —— 它應該真的認得。

    反過來守：如果哪天 main.py 也不 import storage 了，代表接線搬到了
    別處，而那個「別處」多半就在受管的資料夾裡。
    """
    main = SRC / "app" / "main.py"
    if not main.exists():
        pytest.skip("還沒有桌面程式")

    mods = _imported_modules(ast.parse(main.read_text(encoding="utf-8")))
    assert any(
        part in FORBIDDEN for mod in mods for part in mod.split(".")
    ), "組裝根沒有 import 任何資料層 —— 接線是不是搬到表現層去了？"


# ---- 回補批 R-1：domain 不得依賴 pandas / numpy ----
#
# barometer 那側原本只有 `tests/domain/test_fifth_indicators.py` 掃 `indicators.py`
# 一支；5-2~5-7 真正住的是這個 repo 的 `domain/`，卻完全沒有守衛。
# 純 Python list 版本是刻意的（§9.1 第 6 條），不是還沒來得及改。

DATAFRAME_LIBS = ("pandas", "numpy")


def _domain_files() -> list[Path]:
    d = SRC / "domain"
    return sorted(d.rglob("*.py")) if d.is_dir() else []


def test_there_is_a_domain_to_guard():
    """同 `test_there_is_something_to_guard`：資料夾改名不得讓守衛安靜地失效。"""
    assert _domain_files(), "domain/ 底下一支 .py 都沒有，下面那條守衛等於沒在守"


@pytest.mark.parametrize("path", _domain_files(), ids=lambda p: p.name)
def test_domain_does_not_import_dataframe_libraries(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    hits = [
        mod
        for mod in _imported_modules(tree)
        if mod.split(".")[0] in DATAFRAME_LIBS
    ]

    assert not hits, (
        f"{path.relative_to(SRC)} import 了 {sorted(set(hits))} —— "
        "domain 要維持純 Python list 版本（§9.1 第 6 條）。"
    )
