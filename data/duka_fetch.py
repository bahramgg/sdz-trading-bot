"""Forex OHLCV via Dukascopy (master plan §1.3), preferred for deep history.

Uses the ``duka`` package to pull M1 bars and aggregates up to the target TF.
Requires network + the optional ``duka`` dependency; import is lazy so the
package loads without it.
"""
from __future__ import annotations

from datetime import date
from typing import List

from data.yf_fetch import aggregate

# minutes per target TF (M1 base -> aggregate)
_TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def fetch_ohlcv(symbol: str, tf: str, start: date, end: date,
                out_dir: str = "data/duka_cache") -> List[list]:
    """Return [[ts_ms, o, h, l, c, v], ...] aggregated to ``tf`` from M1.

    Dukascopy symbols are lowercase, no slash (e.g. eurusd, xauusd).
    """
    from duka.app import app as duka_app        # lazy import
    from duka.core.utils import TimeFrame
    import csv
    import glob
    import os

    duka_symbol = symbol.lower()
    os.makedirs(out_dir, exist_ok=True)
    duka_app([duka_symbol], start, end, 0, TimeFrame.M1, out_dir, True, 4)

    m1: List[list] = []
    for path in sorted(glob.glob(os.path.join(out_dir, f"{duka_symbol}*.csv"))):
        with open(path, newline="") as fh:
            for row in csv.reader(fh):
                # duka CSV: time, open, high, low, close, volume
                try:
                    ms = _to_ms(row[0])
                    m1.append([ms, float(row[1]), float(row[2]),
                               float(row[3]), float(row[4]),
                               float(row[5]) if len(row) > 5 else 0.0])
                except (ValueError, IndexError):
                    continue
    m1.sort(key=lambda r: r[0])
    factor = _TF_MINUTES[tf]  # M1 -> tf
    return aggregate(m1, factor=factor)


def _to_ms(s: str) -> int:
    from datetime import datetime
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"unparseable duka timestamp: {s}")
