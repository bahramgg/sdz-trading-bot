"""Base + pattern detection and zone construction (master plan §2.2, §2.3).

A zone is anchored on its leg-out (the confirming ERC). Scanning by leg-out
guarantees each zone is created strictly at candle-close of the leg-out, so
``confirm_index`` is always known from closed data only.
"""
from __future__ import annotations

from typing import List, Sequence

from config import Params
from engine.candles import Classified, Dir
from engine.zones import Pattern, Zone, ZoneType


def _pattern_of(leg_in: Dir, leg_out: Dir) -> tuple[ZoneType, Pattern] | None:
    if leg_out == Dir.BULL and leg_in == Dir.BEAR:
        return ZoneType.DEMAND, Pattern.DBR
    if leg_out == Dir.BULL and leg_in == Dir.BULL:
        return ZoneType.DEMAND, Pattern.RBR
    if leg_out == Dir.BEAR and leg_in == Dir.BULL:
        return ZoneType.SUPPLY, Pattern.RBD
    if leg_out == Dir.BEAR and leg_in == Dir.BEAR:
        return ZoneType.SUPPLY, Pattern.DBD
    return None


def _boundaries(
    ztype: ZoneType, base: Sequence[Classified], mode: str
) -> tuple[float, float, float]:
    """Return (proximal, distal, test_edge) for the base per §2.3.

    ``test_edge`` is the wick near-edge (base high for demand, base low for
    supply): the outermost boundary price must enter to "test" the zone. The
    entry ``proximal`` sits deeper (body-based by default), so a wick that taps
    the test band without reaching proximal counts as a test, not a fill.
    """
    lows = [c.candle.low for c in base]
    highs = [c.candle.high for c in base]
    body_hi = [max(c.candle.open, c.candle.close) for c in base]
    body_lo = [min(c.candle.open, c.candle.close) for c in base]
    if ztype == ZoneType.DEMAND:
        distal = min(lows)
        test_edge = max(highs)
        proximal = test_edge if mode == "wick" else max(body_hi)
        return proximal, distal, test_edge
    else:  # SUPPLY
        distal = max(highs)
        test_edge = min(lows)
        proximal = test_edge if mode == "wick" else min(body_lo)
        return proximal, distal, test_edge


def detect_zones(
    classified: Sequence[Classified], symbol: str, tf: str, params: Params
) -> List[Zone]:
    """Detect every valid zone in the series. Logs all zones (no score filter);
    scoring and the trade filter happen downstream (§2.5)."""
    zones: List[Zone] = []
    n = len(classified)
    for j in range(n):
        leg_out = classified[j]
        if not leg_out.is_erc:
            continue

        # Full run of consecutive basing candles immediately before the leg-out.
        end = j - 1
        if end < 0 or not classified[end].is_basing:
            continue
        start = end
        while start - 1 >= 0 and classified[start - 1].is_basing:
            start -= 1
        run_len = end - start + 1
        if run_len > params.max_base_candles:
            continue  # base too long -> invalid (§2.2)

        leg_in_idx = start - 1
        if leg_in_idx < 0 or not classified[leg_in_idx].is_erc:
            continue  # leg-in must be an ERC immediately before the base

        pat = _pattern_of(classified[leg_in_idx].direction, leg_out.direction)
        if pat is None:
            continue
        ztype, pattern = pat

        base = classified[start : end + 1]
        base_high = max(c.candle.high for c in base)
        base_low = min(c.candle.low for c in base)

        # Leg-out must actually leave the base (§2.2).
        if ztype == ZoneType.DEMAND and not (leg_out.candle.close > base_high):
            continue
        if ztype == ZoneType.SUPPLY and not (leg_out.candle.close < base_low):
            continue

        proximal, distal, test_edge = _boundaries(ztype, base, params.proximal_mode)

        # Discard oversized zones (§2.3).
        atr = leg_out.atr
        if atr > 0 and abs(proximal - distal) > params.zone_max_atr * atr:
            continue

        zones.append(
            Zone(
                symbol=symbol,
                tf=tf,
                ztype=ztype,
                pattern=pattern,
                proximal=proximal,
                distal=distal,
                test_edge=test_edge,
                leg_in_index=leg_in_idx,
                base_start=start,
                base_end=end,
                leg_out_index=j,
                confirm_ts=leg_out.candle.ts,
                atr_at_confirm=atr,
            )
        )
    return zones
