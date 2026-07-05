"""Crypto OHLCV via ccxt public API (master plan §1.3).

Primary exchange Bybit, fallback OKX — both serve public OHLCV without keys,
though reachability varies by network/VPN, so the exchange id is config-driven.
Paginates backwards to cover multi-year history and returns closed candles only.
"""
from __future__ import annotations

import time
from typing import List, Optional, Sequence

from config import watchlist

_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def _exchange(exchange_id: str):
    import os
    import ccxt  # imported lazily so the package imports without ccxt present
    klass = getattr(ccxt, exchange_id)
    ex = klass({"enableRateLimit": True})
    # Honor an outbound HTTPS proxy (ccxt does not read HTTPS_PROXY on its own).
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        ex.httpsProxy = proxy
    ex.load_markets()
    return ex


def fetch_ohlcv(symbol: str, tf: str, since_ms: int, until_ms: Optional[int] = None,
                exchange_id: Optional[str] = None) -> List[list]:
    """Return [[ts, o, h, l, c, v], ...] in [since_ms, until_ms], closed bars only.

    Falls back to the configured fallback exchange on any error from the primary.
    """
    wl = watchlist()["crypto"]
    primary = exchange_id or wl["exchange"]
    fallback = wl.get("fallback_exchange")
    try:
        return _fetch_from(primary, symbol, tf, since_ms, until_ms)
    except Exception as exc:  # network/geo/exchange error -> try fallback
        if fallback and fallback != primary:
            return _fetch_from(fallback, symbol, tf, since_ms, until_ms)
        raise


def _fetch_from(exchange_id: str, symbol: str, tf: str, since_ms: int,
                until_ms: Optional[int]) -> List[list]:
    ex = _exchange(exchange_id)
    step = _TF_MS[tf]
    until = until_ms if until_ms is not None else int(time.time() * 1000)
    out: List[list] = []
    cursor = since_ms
    while cursor < until:
        batch = ex.fetch_ohlcv(symbol, timeframe=tf, since=cursor, limit=1000)
        if not batch:
            break
        out.extend(batch)
        last = batch[-1][0]
        if last <= cursor:
            break
        cursor = last + step
        time.sleep(ex.rateLimit / 1000.0)
    # keep only closed bars strictly within range (drop the possibly-forming last bar)
    now = int(time.time() * 1000)
    return [row for row in out
            if since_ms <= row[0] <= until and row[0] + step <= now]
