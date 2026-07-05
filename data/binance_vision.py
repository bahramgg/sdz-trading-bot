"""Deep crypto OHLCV via Binance public data (data-api.binance.vision).

Binance's public market-data host is not geo-blocked like api.binance.com, and
serves spot klines back to a pair's listing (BTC/ETH ~2017, SOL ~2020-08). This
is the source used to assemble the TRAIN window (2019-2023) that the exchanges
reachable via ccxt could not provide, enabling a legitimate P3/P4 split.

Uses ``requests`` which honors HTTPS_PROXY automatically.
"""
from __future__ import annotations

import time
from typing import List, Optional

_BASE = "https://data-api.binance.vision/api/v3/klines"

_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000,
}


def fetch_ohlcv(symbol: str, tf: str, since_ms: int,
                until_ms: Optional[int] = None) -> List[list]:
    """Return [[ts, o, h, l, c, v], ...] in [since_ms, until_ms], closed bars only.

    ``symbol`` is the plan form (e.g. BTC/USDT); the slash is stripped for the
    Binance ticker (BTCUSDT).
    """
    import requests

    ticker = symbol.replace("/", "")
    step = _TF_MS[tf]
    until = until_ms if until_ms is not None else int(time.time() * 1000)
    now = int(time.time() * 1000)
    out: List[list] = []
    cursor = since_ms
    sess = requests.Session()

    while cursor < until:
        resp = sess.get(_BASE, params={
            "symbol": ticker, "interval": tf,
            "startTime": cursor, "limit": 1000,
        }, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for row in batch:
            ts = int(row[0])
            if ts > until or ts + step > now:      # drop out-of-range / forming bar
                continue
            out.append([ts, float(row[1]), float(row[2]),
                        float(row[3]), float(row[4]), float(row[5])])
        last = int(batch[-1][0])
        if last <= cursor:
            break
        cursor = last + step
    return out
