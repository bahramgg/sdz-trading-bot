"""Deep forex OHLCV from Dukascopy pre-built hourly candle files.

Dukascopy serves compressed monthly candle files (one small .bi5 per month) at
datafeed.dukascopy.com — far lighter than aggregating tick data, and reachable
without an API key. Record format (big-endian, 24 bytes each):

    int32  time    seconds offset from the month start
    int32  open    price * point
    int32  close   price * point
    int32  low     price * point
    int32  high    price * point
    float  volume

Empty slots (weekends/holidays) decode to all-zero and are skipped. This is the
forex analogue of data/binance_vision.py and enables a real TRAIN/OOS split.
"""
from __future__ import annotations

import datetime as dt
import lzma
import struct
import time
import urllib.request
from typing import List, Optional

from data.yf_fetch import aggregate

_BASE = "https://datafeed.dukascopy.com/datafeed"
_REC = struct.Struct(">iiiiif")

# price scale (point value) per instrument
_POINT = {
    "EURUSD": 1e5, "GBPUSD": 1e5, "AUDUSD": 1e5, "NZDUSD": 1e5, "USDCHF": 1e5,
    "USDCAD": 1e5, "USDJPY": 1e3, "EURJPY": 1e3, "GBPJPY": 1e3, "XAUUSD": 1e3,
}

# how many 1h bars aggregate into the target TF
_AGG = {"1h": 1, "4h": 4, "1d": 24}


def _fetch_month(instr: str, year: int, month0: int, point: float) -> List[list]:
    """Download & decode one monthly hourly-candle file. month0 is 0-indexed."""
    url = f"{_BASE}/{instr}/{year}/{month0:02d}/BID_candles_hour_1.bi5"
    comp = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            comp = urllib.request.urlopen(req, timeout=40).read()
            break
        except Exception:
            if attempt == 3:
                return []
            time.sleep(2 ** attempt)
    if not comp:
        return []
    try:
        raw = lzma.decompress(comp)
    except lzma.LZMAError:
        return []

    month_start = dt.datetime(year, month0 + 1, 1, tzinfo=dt.timezone.utc)
    base_ms = int(month_start.timestamp() * 1000)
    rows: List[list] = []
    for off in range(0, len(raw) - _REC.size + 1, _REC.size):
        t, o, c, l, h, v = _REC.unpack_from(raw, off)
        if o == 0 and h == 0 and l == 0 and c == 0:
            continue  # weekend/holiday empty slot
        ts = base_ms + t * 1000
        rows.append([ts, o / point, h / point, l / point, c / point, float(v)])
    return rows


def fetch_ohlcv(symbol: str, tf: str, since_ms: int,
                until_ms: Optional[int] = None) -> List[list]:
    """Return [[ts, o, h, l, c, v], ...] for a forex pair in [since, until].

    Downloads 1h candles month-by-month and aggregates up to ``tf`` (1h/4h/1d).
    """
    instr = symbol.replace("/", "")
    point = _POINT.get(instr)
    if point is None:
        raise ValueError(f"no Dukascopy point scale for {instr}; add it to _POINT")
    if tf not in _AGG:
        raise ValueError(f"unsupported tf {tf}; duka_candles serves 1h/4h/1d")

    until = until_ms if until_ms is not None else int(time.time() * 1000)
    start = dt.datetime.fromtimestamp(since_ms / 1000, tz=dt.timezone.utc)
    end = dt.datetime.fromtimestamp(until / 1000, tz=dt.timezone.utc)

    hourly: List[list] = []
    y, m0 = start.year, start.month - 1
    while (y, m0) <= (end.year, end.month - 1):
        hourly.extend(_fetch_month(instr, y, m0, point))
        m0 += 1
        if m0 > 11:
            m0 = 0
            y += 1
    hourly = [r for r in hourly if since_ms <= r[0] <= until]
    hourly.sort(key=lambda r: r[0])

    factor = _AGG[tf]
    return hourly if factor == 1 else aggregate(hourly, factor=factor)
