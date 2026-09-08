r"""stock-research 發布：兩層鎖（ToDo §5.1、§5.3、§9 Day 27 第 3、6 項）。

與 market-barometer 的差別只有兩處：

  1. **兩層鎖** —— 材料是 `key + NUL + password`，2 × 2 = 4 組有效組合
  2. **不開 lint** —— 這個 repo 可以有買賣與短中長線建議（§2.1）

其餘（信封加密、每次換 salt/IV/CEK、明文只落在 build/）完全共用
market-barometer 的 crypto 與 render —— 兩個站用同一套機制，
Day 27 才講得清楚。

⚠️ **已知風險**：這個站的外層 Key 與 market-barometer 的 Password 有字串重疊。
只要那邊任何一組流出（它的密碼本來就要印在文章上給讀者用），這裡的外層 Key
就跟著流出，**兩層鎖實際降級成一層**，安全性只剩內層那一層在擋。
現階段已知並接受，但心裡要照一層鎖的強度放內容。

具體是哪幾組字串重疊，**只記在 `%STOCKDATA_ROOT%\secrets\publish.json`**，
不寫在這裡：這是 public repo，把密碼寫進註解跟寫進程式碼一樣糟，
而且 git history 撤不回來（§5.1、§12 第 1 條）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "market-barometer" / "src"))

from barometer import config  # noqa: E402
from barometer.crypto import credentials, envelope, shell  # noqa: E402
from barometer.domain import windows  # noqa: E402
from barometer.pipeline import publish_gate  # noqa: E402
from barometer.pipeline import build_page  # noqa: E402
from barometer.render import page as base_page  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402

from research import config as rc  # noqa: E402
from research.datasources import chips_tw  # noqa: E402
from research.pipeline import run_stock_scores  # noqa: E402
from research.render import page as rpage  # noqa: E402

SITE = credentials.STOCK_RESEARCH
TITLE = "stock-research"
TAGLINE = "台美權值股的三期評分 —— 私人研究用，不對外分享"
DOCS = _HERE / "docs"


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    force = "--force" in argv
    config.ensure_dirs()

    # 台股才有三大法人資料 —— 一天抓一次全市場，抽出要的那五檔（§6 規則 5）
    tw_bars = csv_audit.read_current(rc.TW_STOCKS[0])
    tw_days = windows.last_n_sessions([b.date for b in tw_bars], 5)
    per_symbol, notes = chips_tw.net_shares_by_symbol(list(rc.TW_STOCKS), tw_days)
    for n in notes:
        print(f"  ! {n}")
    chips_by_symbol = {s: dict(zip(tw_days, v)) for s, v in per_symbol.items()}

    rows_by_symbol = {}
    for sym in rc.ALL_SYMBOLS:
        bars = csv_audit.read_current(sym)
        if not bars:
            continue
        scored = run_stock_scores.score_series(
            sym, bars, net_by_date=chips_by_symbol.get(sym)
        )
        rows_by_symbol[sym] = (scored, run_stock_scores.summarize_window(scored))

    tabs = rpage.build_tabs(rows_by_symbol)
    # enforce_lint=False：這一側可以有建議（§2.1）
    html = base_page.render(
        tabs, title=TITLE, tagline=TAGLINE,
        footer_notes=rpage.FOOTER, enforce_lint=False,
        last_run_at=build_page.last_fetch_at(),
    )

    plain_path = config.build_dir() / "stock-research.plain.html"
    plain_path.write_text(html, encoding="utf-8")
    print(f"明文  {plain_path}（{len(html):,} 字元）")

    gate = publish_gate.Gate(config.build_dir() / "stock-research.gate.json")
    decision = gate.should_publish(html, force=force)
    print(f"閘門  {decision.reason}")
    if not decision.publish and not dry:
        print("\n沒有變，docs/ 一個字都沒動 —— 也就不會有 commit。")
        return 0

    creds = credentials.load(SITE)
    env = envelope.seal(html, creds.materials, slot_ids=creds.slot_ids)
    sealed = shell.wrap(env, title=TITLE, mode=creds.mode)
    print(f"密文  pub_id={env['pub_id']}  {len(creds)} 組憑證（兩層鎖）"
          f"  PBKDF2 {env['kdf']['iter']:,} 次")

    # §9 Day 27 第 6 項：4 組憑證逐一實測解鎖
    for material, slot in zip(creds.materials, creds.slot_ids):
        assert envelope.open_envelope(env, material) == html
        assert envelope.which_slot(env, material) == slot
    print(f"驗收  {len(creds)} 組組合逐一解開、槽位代號沒有錯位")

    if dry:
        out = config.build_dir() / "stock-research.sealed.html"
        out.write_text(sealed, encoding="utf-8")
        print(f"\n--dry-run：密文寫到 {out}，docs/ 沒有動")
        return 0

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(sealed, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"\n寫出  {DOCS / 'index.html'}（{len(sealed):,} 字元）")
    gate.record(html)
    (config.build_dir() / "stock-research.pubid.json").write_text(
        json.dumps({"pub_id": env["pub_id"], "symbols": len(rows_by_symbol)},
                   ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
