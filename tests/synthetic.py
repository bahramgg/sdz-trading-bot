"""Deterministic synthetic candle builders for engine/backtest tests.

Prices are chosen so ATR seeds cleanly to ~1.0, making ERC/basing thresholds
easy to reason about by hand.
"""
from __future__ import annotations

from typing import List

from engine.candles import Candle

_TF_MS = 3_600_000  # 1h in ms; only relative spacing matters for tests


def _c(i: int, o: float, h: float, l: float, cl: float, v: float = 1.0) -> Candle:
    return Candle(ts=1_600_000_000_000 + i * _TF_MS, open=o, high=h, low=l, close=cl, volume=v)


def seed(n: int, level: float = 100.0) -> List[Candle]:
    """n flat basing candles with range ~1.0 to seed ATR ~= 1.0."""
    out = []
    for i in range(n):
        out.append(_c(i, level, level + 0.5, level - 0.5, level))
    return out


def demand_dbr() -> List[Candle]:
    """A clean drop-base-rally demand zone that later fills and hits TP.

    Expected zone: proximal=98.3, distal=97.8, DBR, score 8 (fresh, 1-ERC
    departure, 2-candle base, open-space margin, neutral HTF).
    """
    cs = seed(18)                                   # idx 0..17  ATR ~1.0
    n = len(cs)
    cs.append(_c(n + 0, 100.0, 100.2, 98.0, 98.2))  # 18 leg-in bear ERC
    cs.append(_c(n + 1, 98.2, 98.6, 97.8, 98.1))    # 19 base 1 (basing)
    cs.append(_c(n + 2, 98.1, 98.5, 97.9, 98.3))    # 20 base 2 (basing)
    cs.append(_c(n + 3, 98.3, 100.6, 98.2, 100.4))  # 21 leg-out bull ERC (confirm)
    cs.append(_c(n + 4, 99.5, 99.6, 98.2, 98.5))    # 22 pullback -> fill @98.3, no TP
    cs.append(_c(n + 5, 98.5, 100.3, 98.4, 100.2))  # 23 rally -> TP @100.1
    cs.append(_c(n + 6, 100.2, 100.4, 99.8, 100.0)) # 24 tail
    return cs


def supply_rbd() -> List[Candle]:
    """A rally-base-drop supply zone (mirror of demand_dbr)."""
    cs = seed(18)
    n = len(cs)
    cs.append(_c(n + 0, 100.0, 102.0, 99.8, 101.8))  # leg-in bull ERC
    cs.append(_c(n + 1, 101.8, 102.2, 101.4, 101.9)) # base 1
    cs.append(_c(n + 2, 101.9, 102.1, 101.5, 101.7)) # base 2
    cs.append(_c(n + 3, 101.7, 101.8, 99.4, 99.6))   # leg-out bear ERC (confirm)
    cs.append(_c(n + 4, 100.5, 101.8, 100.4, 101.5)) # pullback -> fill @101.7? high 101.8>=101.7
    cs.append(_c(n + 5, 101.5, 101.6, 99.7, 99.9))   # drop -> TP
    cs.append(_c(n + 6, 99.9, 100.2, 99.6, 100.0))
    return cs


def flat_no_zone() -> List[Candle]:
    """Only basing candles -> no ERC -> no zones at all."""
    return seed(40)
