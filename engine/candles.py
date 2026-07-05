"""Candle model, ATR, and classification (master plan §2.1).

Everything here operates on a list of closed candles. No function looks at an
index beyond the one it is classifying, so classification of candle ``i`` is a
pure function of candles ``0..i`` — this is what makes the lookahead test pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Sequence

from config import Params


class Dir(Enum):
    BULL = 1
    BEAR = -1
    FLAT = 0


@dataclass(frozen=True)
class Candle:
    ts: int          # epoch ms, UTC, candle OPEN time
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def direction(self) -> Dir:
        if self.close > self.open:
            return Dir.BULL
        if self.close < self.open:
            return Dir.BEAR
        return Dir.FLAT


@dataclass(frozen=True)
class Classified:
    """A candle plus its rule classification and the ATR in force at its close."""

    candle: Candle
    atr: float
    is_erc: bool
    is_basing: bool

    @property
    def direction(self) -> Dir:
        return self.candle.direction


def true_range(cur: Candle, prev: Candle | None) -> float:
    if prev is None:
        return cur.high - cur.low
    return max(
        cur.high - cur.low,
        abs(cur.high - prev.close),
        abs(cur.low - prev.close),
    )


def atr_series(candles: Sequence[Candle], period: int) -> List[float]:
    """Wilder's ATR. ATR[i] uses only candles 0..i (no lookahead).

    Before ``period`` bars exist the running simple mean of TR is used, so an
    ATR is always defined for i>=0 (approximate early on, exact once seeded).
    """
    out: List[float] = []
    trs: List[float] = []
    prev_atr: float | None = None
    for i, c in enumerate(candles):
        tr = true_range(c, candles[i - 1] if i > 0 else None)
        trs.append(tr)
        if i + 1 < period:
            prev_atr = sum(trs) / len(trs)
        elif i + 1 == period:
            prev_atr = sum(trs) / period            # seed = simple mean of first `period` TRs
        else:
            prev_atr = (prev_atr * (period - 1) + tr) / period  # Wilder smoothing
        out.append(prev_atr)
    return out


def classify(candles: Sequence[Candle], params: Params) -> List[Classified]:
    """Classify each candle as ERC / basing / neither, per §2.1.

    ERC and basing are mutually exclusive by construction: an ERC has
    body/range >= 0.55 and range >= 1.3*atr, both of which violate the basing
    thresholds (0.45 body, 0.8*atr range).
    """
    atrs = atr_series(candles, params.atr_period)
    result: List[Classified] = []
    for c, atr in zip(candles, atrs):
        rng = c.range
        if rng <= 0 or atr <= 0:
            # degenerate bar (flat or no ATR yet): treat as basing, never ERC
            result.append(Classified(c, atr, is_erc=False, is_basing=True))
            continue
        body_ratio = c.body / rng
        is_erc = (rng >= params.erc_atr_mult * atr) and (body_ratio >= params.erc_body_min)
        is_basing = (body_ratio <= params.base_body_max) or (rng <= params.base_atr_max * atr)
        if is_erc:
            is_basing = False  # exclusivity guard against pathological inputs
        result.append(Classified(c, atr, is_erc=is_erc, is_basing=is_basing))
    return result
