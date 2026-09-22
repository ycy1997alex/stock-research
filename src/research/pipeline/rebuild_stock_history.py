"""Atomically replace legacy stock scores with the directional scale."""
from __future__ import annotations

import json

from research.pipeline import run_stock_scores, tw_local
from research.storage.tw_local import TwLocalStore
from research.storage.us_local import UsLocalStore


def rebuild(repo, symbols: list[str] | tuple[str, ...]) -> int:
    """Calculate every row first; replace only listed stock symbols in one transaction."""
    tw_store = TwLocalStore(repo.conn)
    us_store = UsLocalStore(repo.conn)

    def load_local(symbol, day):
        return (tw_local.local_view(tw_store, symbol, day)
                if symbol.endswith((".TW", ".TWO")) else us_store.get_asof(day, symbol))

    new_rows = []
    for symbol in symbols:
        bars = repo.get_adjusted_prices(symbol)
        if not bars:
            raise ValueError(f"{symbol}: 沒有還原價格，不重建舊分數")
        for day, score in run_stock_scores.score_series(
            symbol, bars, window=len(bars), local_loader=load_local,
        ):
            if score.comparable is None:
                continue
            parts = {name: value for name, value in (
                ("short", score.short.score), ("mid", score.mid.score),
                ("long", score.long.score), ("technical", score.technical),
                ("local", score.local), ("raw_gap", score.raw_gap),
            ) if value is not None}
            new_rows.append(("stock", symbol, day.isoformat(), score.comparable,
                             json.dumps(parts, ensure_ascii=False), "adjusted-v1",
                             score.comparable, score.native, score.strength))
    if not new_rows:
        raise ValueError("沒有可重建的個股分數")
    with repo.conn:
        for symbol in symbols:
            repo.conn.execute("DELETE FROM score_history WHERE scope='stock' AND symbol=?", (symbol,))
        repo.conn.executemany(
            "INSERT INTO score_history "
            "(scope,symbol,as_of,score,subscores_json,price_version,comparable,native,strength) "
            "VALUES (?,?,?,?,?,?,?,?,?)", new_rows,
        )
    return len(new_rows)
