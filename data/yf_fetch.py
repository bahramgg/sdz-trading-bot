"""Forex OHLCV via yfinance (fallback source, master plan §1.3).

yfinance intraday history is limited (~730d for 1h), so this is the live/backtest
fallback; Dukascopy (duka_fetch) is preferred for deep forex history.
"""
from __future__ import annotations

from typing import List

from config import watchlist

# yfinance interval strings
_YF_INTERVAL = {"15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"}


def fetch_ohlcv(symbol: str, tf: str, period: str = "730d") -> List[list]:
    """Return [[ts_ms, o, h, l, c, v], ...] for a forex pair via yfinance.

    ``symbol`` is the plan symbol (e.g. EURUSD); mapped to the yfinance ticker
    via watchlist.yaml. 4h is aggregated from 1h since yfinance has no 4h.
    """
    import yfinance as yf  # lazy import

    ticker = watchlist()["forex"]["yf_map"].get(symbol, symbol)
    interval = _YF_INTERVAL.get(tf, "1h")
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        return []
    rows: List[list] = []
    for ts, r in df.iterrows():
        ms = int(ts.timestamp() * 1000)
        rows.append([ms, float(r["Open"]), float(r["High"]),
                     float(r["Low"]), float(r["Close"]),
                     float(r.get("Volume", 0) or 0)])
    if tf == "4h":
        rows = aggregate(rows, factor=4)
    return rows


def aggregate(rows: List[list], factor: int) -> List[list]:
    """Aggregate N base bars into one (OHLC roll-up). Drops a trailing partial."""
    out: List[list] = []
    for i in range(0, len(rows) - factor + 1, factor):
        chunk = rows[i:i + factor]
        out.append([
            chunk[0][0],
            chunk[0][1],
            max(r[2] for r in chunk),
            min(r[3] for r in chunk),
            chunk[-1][4],
            sum(r[5] for r in chunk),
        ])
    return out
