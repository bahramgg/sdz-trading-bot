"""Odds Enhancer score, 0-10 (master plan §2.5).

Score is computed at trade-decision time on closed data only. Every forward-
looking feature is bounded by ``decision_index`` (the candle at which the trade
would fill), so scoring never peeks past the decision — the lookahead test
covers this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from config import Params
from engine.candles import Candle, Classified, Dir
from engine.zones import Zone, ZoneType


@dataclass(frozen=True)
class HtfContext:
    """Higher-timeframe curve context for the HTF-alignment enhancer."""

    trend: Dir              # BULL / BEAR / FLAT from htf_trend()
    range_low: float        # recent HTF swing low  (curve range)
    range_high: float       # recent HTF swing high (curve range)


def htf_trend(curve_closes: Sequence[float], highs: Sequence[float],
              lows: Sequence[float], ema_period: int) -> Dir:
    """Deterministic HTF trend: EMA slope sign AND 2-swing structure (§2.5).

    BULL iff EMA is rising and structure is higher-highs & higher-lows;
    BEAR iff EMA is falling and structure is lower-highs & lower-lows;
    otherwise FLAT (scored as neutral).
    """
    if len(curve_closes) < 2:
        return Dir.FLAT
    ema = _ema(curve_closes, ema_period)
    slope = ema[-1] - ema[-2]

    swing_highs = _swings(highs, kind="high")
    swing_lows = _swings(lows, kind="low")
    struct = Dir.FLAT
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh = swing_highs[-1] > swing_highs[-2]
        hl = swing_lows[-1] > swing_lows[-2]
        lh = swing_highs[-1] < swing_highs[-2]
        ll = swing_lows[-1] < swing_lows[-2]
        if hh and hl:
            struct = Dir.BULL
        elif lh and ll:
            struct = Dir.BEAR

    if slope > 0 and struct == Dir.BULL:
        return Dir.BULL
    if slope < 0 and struct == Dir.BEAR:
        return Dir.BEAR
    return Dir.FLAT


def _ema(values: Sequence[float], period: int) -> List[float]:
    k = 2.0 / (period + 1)
    out: List[float] = []
    prev = values[0]
    for v in values:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def _swings(series: Sequence[float], kind: str) -> List[float]:
    """Simple 3-bar fractal swings. Returns the swing prices in order."""
    out: List[float] = []
    for i in range(1, len(series) - 1):
        if kind == "high" and series[i] > series[i - 1] and series[i] > series[i + 1]:
            out.append(series[i])
        elif kind == "low" and series[i] < series[i - 1] and series[i] < series[i + 1]:
            out.append(series[i])
    return out


@dataclass(frozen=True)
class ScoreResult:
    score: int
    breakdown: dict


def _departure_points(zone: Zone, classified: Sequence[Classified],
                      decision_index: int) -> int:
    """§2.5 Departure strength: >=2 consecutive same-dir ERCs, or a gap, on the
    leg-out => 2; a single ERC => 1. Bounded by decision_index."""
    leg_out = classified[zone.leg_out_index]
    dir_ = leg_out.direction

    # consecutive same-direction ERCs starting at the leg-out
    count = 0
    i = zone.leg_out_index
    while i < min(decision_index, len(classified)) and classified[i].is_erc \
            and classified[i].direction == dir_:
        count += 1
        i += 1
    if count >= 2:
        return 2

    # gap on the leg-out relative to the base-end candle
    if zone.leg_out_index >= 1:
        prev = classified[zone.leg_out_index - 1].candle
        lo = leg_out.candle
        if zone.ztype == ZoneType.DEMAND and lo.open > prev.high:
            return 2
        if zone.ztype == ZoneType.SUPPLY and lo.open < prev.low:
            return 2
    return 1  # exactly one ERC (leg-out is always an ERC by construction)


def score_zone(
    zone: Zone,
    classified: Sequence[Classified],
    params: Params,
    prior_tests: int = 0,
    opposing_proximal: Optional[float] = None,
    trade_r: Optional[float] = None,
    htf: Optional[HtfContext] = None,
    decision_index: Optional[int] = None,
) -> ScoreResult:
    """Compute the 0-10 odds-enhancer score for ``zone``.

    prior_tests       : tests recorded strictly before the decision (freshness).
    opposing_proximal : price of nearest opposing zone (profit margin).
    trade_r           : per-unit R distance (entry-stop), to convert margin to R.
    htf               : curve-TF context (HTF alignment); None => neutral.
    decision_index    : candle index of the trade decision; bounds departure.
    """
    if decision_index is None:
        decision_index = len(classified)

    b: dict = {}

    # 1. Freshness
    if prior_tests <= 0:
        b["freshness"] = 2
    elif prior_tests == 1:
        b["freshness"] = 1
    else:
        b["freshness"] = 0

    # 2. Departure strength
    b["departure"] = _departure_points(zone, classified, decision_index)

    # 3. Time at base
    n = zone.base_len
    b["time_at_base"] = 2 if n <= 3 else (1 if n <= 5 else 0)

    # 4. Profit margin (to opposing zone, in R)
    if opposing_proximal is None:
        b["profit_margin"] = 2          # open space (§2.5); logged separately
        b["open_space"] = True
    elif trade_r and trade_r > 0:
        reward_r = abs(opposing_proximal - zone.proximal) / trade_r
        b["profit_margin"] = 2 if reward_r >= 3 else (1 if reward_r >= 2 else 0)
        b["reward_r_to_opposing"] = round(reward_r, 3)
    else:
        b["profit_margin"] = 0

    # 5. HTF alignment
    b["htf_alignment"] = _htf_points(zone, htf)

    score = (b["freshness"] + b["departure"] + b["time_at_base"]
             + b["profit_margin"] + b["htf_alignment"])
    return ScoreResult(score=score, breakdown=b)


def _htf_points(zone: Zone, htf: Optional[HtfContext]) -> int:
    if htf is None or htf.trend == Dir.FLAT:
        return 1  # neutral
    agrees = (
        (zone.ztype == ZoneType.DEMAND and htf.trend == Dir.BULL)
        or (zone.ztype == ZoneType.SUPPLY and htf.trend == Dir.BEAR)
    )
    conflicts = (
        (zone.ztype == ZoneType.DEMAND and htf.trend == Dir.BEAR)
        or (zone.ztype == ZoneType.SUPPLY and htf.trend == Dir.BULL)
    )
    if conflicts:
        return 0
    if agrees and htf.range_high > htf.range_low:
        mid = (htf.range_high + htf.range_low) / 2.0
        cheap = zone.proximal <= mid           # demand wants cheap half
        expensive = zone.proximal >= mid       # supply wants expensive half
        in_right_half = cheap if zone.ztype == ZoneType.DEMAND else expensive
        return 2 if in_right_half else 1
    return 1
