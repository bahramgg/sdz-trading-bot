"""SQLite store: schema, idempotent re-fetch (P0 acceptance gate)."""
from __future__ import annotations

import os

from data.store import Store


def test_idempotent_upsert(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    rows = [[1000, 1, 2, 0.5, 1.5, 10], [2000, 1.5, 2.5, 1.0, 2.0, 11]]
    with Store(db) as s:
        assert s.upsert_ohlcv("BTC/USDT", "1h", rows) == 2
        # re-fetch overlapping window: no duplicates, values updated in place
        rows2 = [[2000, 1.5, 3.0, 1.0, 2.5, 12], [3000, 2.5, 3.5, 2.0, 3.0, 13]]
        s.upsert_ohlcv("BTC/USDT", "1h", rows2)
        lo, hi, n = s.ohlcv_span("BTC/USDT", "1h")
        assert (lo, hi, n) == (1000, 3000, 3)      # 3 unique bars, not 4
        candles = s.load_candles("BTC/USDT", "1h")
        assert candles[1].high == 3.0              # updated by second write


def test_load_range_filter(tmp_path):
    db = os.path.join(tmp_path, "t.db")
    with Store(db) as s:
        s.upsert_ohlcv("ETH/USDT", "4h",
                       [[t, 1, 1, 1, 1, 0] for t in (100, 200, 300, 400)])
        assert len(s.load_candles("ETH/USDT", "4h", start_ts=200, end_ts=300)) == 2
