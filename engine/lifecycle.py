"""Zone lifecycle transitions (§2.4) and set-and-forget trade plan (§2.6)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from config import Params
from engine.candles import Classified
from engine.zones import Zone, ZoneState, ZoneType


@dataclass(frozen=True)
class TradePlan:
    ztype: ZoneType
    entry: float
    stop: float
    target: float
    r: float           # per-unit risk = |entry - stop|
    target_r: float    # reward in R multiples

    @property
    def sign(self) -> int:
        return 1 if self.ztype == ZoneType.DEMAND else -1


def build_trade_plan(
    zone: Zone,
    params: Params,
    cost_buffer: float = 0.0,
    opposing_proximal: Optional[float] = None,
) -> Optional[TradePlan]:
    """Compute entry/stop/target for a zone (§2.6).

    ``cost_buffer`` is a price-unit floor for the stop distance (spread/fee);
    ``opposing_proximal`` is the price of the nearest opposing zone, used by the
    opposing_zone / hybrid target modes.
    """
    entry = zone.proximal
    atr = zone.atr_at_confirm
    buffer = max(params.stop_buffer_atr * atr, cost_buffer)

    if zone.ztype == ZoneType.DEMAND:
        stop = zone.distal - buffer
    else:
        stop = zone.distal + buffer

    r = abs(entry - stop)
    if r <= 0:
        return None

    sign = 1 if zone.ztype == ZoneType.DEMAND else -1
    fixed_target = entry + sign * 3.0 * r

    def dist_r(price: float) -> float:
        return (sign * (price - entry)) / r  # signed reward in R

    mode = params.tp_mode
    if mode == "fixed_3R":
        target = fixed_target
    elif mode == "opposing_zone":
        target = opposing_proximal if opposing_proximal is not None else fixed_target
    elif mode == "hybrid":
        candidates = [fixed_target]
        if opposing_proximal is not None and dist_r(opposing_proximal) > 0:
            candidates.append(opposing_proximal)
        # nearest target (min reward distance), then floor at 2R
        target = min(candidates, key=lambda p: dist_r(p))
        if dist_r(target) < params.tp_hybrid_floor_r:
            target = entry + sign * params.tp_hybrid_floor_r * r
    else:
        raise ValueError(f"unknown tp_mode: {mode}")

    tr = dist_r(target)
    if tr <= 0:
        return None
    return TradePlan(ztype=zone.ztype, entry=entry, stop=stop, target=target, r=r, target_r=tr)


def advance_lifecycle(
    zone: Zone,
    classified: Sequence[Classified],
    params: Params,
    tf_is_curve: bool = False,
) -> Zone:
    """Walk the zone forward from confirm+1 to end, updating state in place.

    Order of checks per candle (§2.4):
      1. break: candle CLOSES beyond distal -> broken (terminal).
      2. test:  candle trades into the [proximal, distal] band -> test_count++.
      3. expire: age since confirm > ZONE_MAX_AGE_BARS -> expired (terminal).
    A zone that is consumed by a trade is handled by the backtester, not here.
    """
    max_age = None if tf_is_curve else params.zone_max_age_bars_default
    for i in range(zone.confirm_index + 1, len(classified)):
        c = classified[i].candle

        # 1. break on close beyond distal
        if zone.ztype == ZoneType.DEMAND and c.close < zone.distal:
            zone.state = ZoneState.BROKEN
            zone.broken_index = i
            return zone
        if zone.ztype == ZoneType.SUPPLY and c.close > zone.distal:
            zone.state = ZoneState.BROKEN
            zone.broken_index = i
            return zone

        # 2. test: any trade into the wick test band [distal, test_edge]
        if zone.candle_tests(c.low, c.high):
            zone.test_count += 1
            if zone.state == ZoneState.FRESH:
                zone.state = ZoneState.TESTED

        # 3. expiry
        if max_age is not None and (i - zone.confirm_index) > max_age:
            zone.state = ZoneState.EXPIRED
            zone.expired_index = i
            return zone

    return zone
