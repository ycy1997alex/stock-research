r"""stock-research 發布：兩層鎖（ToDo §5.1、§5.3、§9 Day 27 第 3、6 項）。

與 market-barometer 的差別只有兩處：

  1. **兩層鎖** —— 材料是 `key + NUL + password`，2 × 2 = 4 組有效組合
  2. **不開 lint** —— 這個 repo 可以有買賣與短中長線建議（§2.1）

其餘（信封加密、每次換 salt/IV/CEK、明文只落在 build/）完全共用
market-barometer 的 crypto 與 render —— 兩個站用同一套機制，
Day 27 才講得清楚。

⚠️ **外層 Key 與 market-barometer 的 Password 有字串重疊，這是刻意的。**
那邊的 Password 裡只有一組會印在文章上給讀者，而那一組**不是**這裡的 Key；
其餘幾組是作者自用，兼作這裡的外層 Key —— 記一組就能開兩個站。讀者拿到的
那組在這裡連外層都過不了，所以這邊仍然是實打實的兩層鎖。

撐著第二層的就是那條紀律：**對外只給那一組**。紀律一破（截圖、口耳相傳），
這裡才會降級成一層，只剩內層在擋。

具體是哪幾組字串，**只記在 `%STOCKDATA_ROOT%\secrets\publish.json`**，
不寫在這裡：這是 public repo，把密碼寫進註解跟寫進程式碼一樣糟，
而且 git history 撤不回來（§5.1、§12 第 1 條）。
"""
from __future__ import annotations

import json
import sys
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

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
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402

from research import config as rc  # noqa: E402
from research.datasources import chips_tw  # noqa: E402
from research.pipeline import run_stock_scores  # noqa: E402
from research.pipeline import tw_local  # noqa: E402
from research.pipeline import us_local  # noqa: E402
from research.pipeline import fundamentals  # noqa: E402
from research.domain import local_stock  # noqa: E402
from research.domain.fundamentals import FundamentalReport  # noqa: E402
from research.render import page as rpage  # noqa: E402
from research.storage.tw_local import TwLocalStore  # noqa: E402
from research.storage.us_local import UsLocalStore  # noqa: E402
from research.storage.fundamentals import FundamentalStore  # noqa: E402

SITE = credentials.STOCK_RESEARCH
TITLE = "stock-research"
TAGLINE = "台美權值股的三期評分，私人研究用，不對外分享"
DOCS = _HERE / "docs"


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    force = "--force" in argv
    config.ensure_dirs()

    # 台股才有三大法人資料 —— 一天抓一次全市場，抽出要的那五檔（§6 規則 5）
    tw_bars = csv_audit.read_current(rc.TW_STOCKS[0])
    tw_days = windows.last_n_sessions([b.date for b in tw_bars], 5)
    with SqliteRepo(config.db_path()) as chips_repo:
        chips_repo.init_schema()
        per_symbol, notes = chips_tw.net_shares_by_symbol(list(rc.TW_STOCKS), tw_days, repo=chips_repo)
        # Each endpoint returns the entire listed market; select watched stocks
        # only after one fetch and retain each source's own publication date.
        latest_session = tw_days[-1]
        volumes = {}
        closes = {}
        for symbol in rc.TW_STOCKS:
            bars = csv_audit.read_current(symbol)
            volumes[symbol] = next((bar.volume_shares for bar in reversed(bars)
                                    if bar.date == latest_session), None)
            closes[symbol] = next((bar.close for bar in reversed(bars)
                                   if bar.date == latest_session), None)
        local_store = TwLocalStore(chips_repo.conn)
        local_result = tw_local.run(
            local_store, latest_session, list(rc.TW_STOCKS),
            volume_shares_by_symbol=volumes, close_twd_by_symbol=closes,
        )
        local_by_symbol = {symbol: tw_local.local_view(local_store, symbol, latest_session)
                           for symbol in rc.TW_STOCKS}
        us_result = us_local.run(UsLocalStore(chips_repo.conn),
                                 list(rc.US_STOCKS + rc.ADRS),
                                 dt.datetime.now(ZoneInfo("Asia/Taipei")).date())
        fundamental_store = FundamentalStore(chips_repo.conn)
        fundamental_store.init_schema()
        fundamental_stamp = dt.datetime.now(ZoneInfo("Asia/Taipei"))
        fundamental_result = fundamentals.refresh(
            fundamental_store, rc.TW_STOCKS, rc.US_STOCKS + rc.ADRS,
            fundamental_stamp,
        )
        fundamentals_by_symbol = {
            symbol: fundamentals.compose_tw_report(
                symbol, local_by_symbol[symbol],
                fundamental_store.get_asof(symbol, fundamental_stamp.date()),
                fundamental_stamp.date(),
            ) for symbol in rc.TW_STOCKS
        }
        fundamentals_by_symbol.update({
            symbol: fundamental_store.get_asof(symbol, fundamental_stamp.date())
                    or FundamentalReport(symbol, {})
            for symbol in rc.US_STOCKS + rc.ADRS
        })
    for n in notes:
        print(f"  ! {n}")
    for note in local_result.notes:
        print(f"  ! {note}")
    for dataset, coverage in local_result.coverage.items():
        print(f"{dataset}: {coverage.label('涵蓋率')}")
    for dataset, available in us_result.coverage.items():
        print(f"US {dataset}: {available}/{len(rc.US_STOCKS + rc.ADRS)}")
    for symbol in rc.ALL_SYMBOLS:
        print(f"基本面 {symbol}: {fundamentals_by_symbol[symbol].coverage.label()}")
    for note in fundamental_result.notes:
        print(f"  ! {note}")
    chips_by_symbol = {s: dict(zip(tw_days, v)) for s, v in per_symbol.items()}

    rows_by_symbol = {}
    missing_reasons: dict[str, str] = {}
    provenance_by_symbol: dict[str, tuple[str, str]] = {}
    local_meta_by_symbol: dict[str, tuple[str, int]] = {}
    with SqliteRepo(config.db_path()) as price_repo:
        price_repo.init_schema()
        tw_store = TwLocalStore(price_repo.conn)
        us_store = UsLocalStore(price_repo.conn)

        def load_local(symbol: str, day: dt.date) -> dict:
            return (tw_local.local_view(tw_store, symbol, day)
                    if symbol.endswith((".TW", ".TWO")) else us_store.get_asof(day, symbol))

        for sym in rc.ALL_SYMBOLS:
            current = csv_audit.read_current(sym)
            adjusted = price_repo.get_adjusted_prices(sym)
            if not current:
                missing_reasons[sym] = "本機沒有價格序列"
                continue
            if not adjusted:
                missing_reasons[sym] = "還原序列資料不足，無法計分"
                continue
            if adjusted[-1].date < current[-1].date:
                missing_reasons[sym] = "還原序列尚未涵蓋最新交易日，無法計分"
                continue
            price_source = current[-1].source or "未記錄"
            source = f"價格：{price_source}"
            if sym in rc.TW_STOCKS and sym in chips_by_symbol:
                source += "；籌碼：TWSE T86"
            provenance_by_symbol[sym] = (
                source, current[-1].as_of.strftime("%Y-%m-%d %H:%M"))
            scored = run_stock_scores.score_series(
                sym, adjusted, net_by_date=chips_by_symbol.get(sym), local_loader=load_local
            )
            rows_by_symbol[sym] = (scored, run_stock_scores.summarize_window(scored))
            if sym in rc.US_STOCKS + rc.ADRS:
                local = local_stock.score_us_local(us_store.get_asof(adjusted[-1].date, sym), adjusted[-1].date)
                dated = [item for item in local.items if item.score is not None and item.data_date]
                if dated:
                    oldest = max(dated, key=lambda item: item.age_days)
                    local_meta_by_symbol[sym] = (oldest.data_date, oldest.age_days)

    # 分數落地（§10，2026-09-18）。`run_daily.ps1` 的註解寫著「評分不在這裡跑，
    # publish.py 產頁面的時候會自己算」—— 那句話是對的，缺的是後半句：算完要
    # 存下來。原本只呼叫 score_series()（純函式），所以 score_history 的 stock
    # scope 停在唯一一次手動跑 scores_stock 的 2026-09-04。
    #
    # 餵同一份籌碼資料，寫下來的分數才會跟頁面上的是同一個數字。
    scores = run_stock_scores.run(
        list(rows_by_symbol), chips_by_symbol=chips_by_symbol
    )
    print(f"分數  {scores.counts.get('symbols_ok', 0)} 檔寫進 score_history"
          f"（run_id={scores.run_id}）")

    tabs = rpage.build_tabs(
        rows_by_symbol, provenance_by_symbol=provenance_by_symbol,
        missing_reasons=missing_reasons,
        local_by_symbol=local_by_symbol,
        local_coverage={name: (coverage.available, coverage.expected)
                        for name, coverage in local_result.coverage.items()},
        local_meta_by_symbol=local_meta_by_symbol,
        fundamentals_by_symbol=fundamentals_by_symbol,
    )
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
