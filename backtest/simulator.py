"""Event-driven backtester (master plan §2.6, §3).

Deterministic: identical inputs -> identical trades (no RNG, no wall clock).
No lookahead: a zone's decision at fill index only reads candles up to that
index; the intrabar ambiguity rule (§2.6) resolves same-candle SL+TP with a
lower timeframe if supplied, else counts a LOSS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from config import Params
from engine.candles import Candle, Classified, classify
from engine.lifecycle import TradePlan, build_trade_plan
from engine.patterns import detect_zones
from engine.score import HtfContext, ScoreResult, htf_trend, score_zone
from engine.zones import Zone, ZoneState, ZoneType
from backtest.costs import per_side_cost, round_trip_cost


@dataclass
class Trade:
    zone: Zone
    plan: TradePlan
    score: int
    freshness: int
    entry_index: int
    exit_index: int
    entry_ts: int
    exit_ts: int
    entry: float
    exit_price: float
    outcome: str          # WIN | LOSS
    gross_r: float
    cost_r: float
    market: str

    @property
    def realized_r(self) -> float:
        return self.gross_r - self.cost_r


@dataclass
class SimConfig:
    market: str
    symbol: str
    tf: str
    tf_is_curve: bool = False


def build_htf_context(curve: Sequence[Candle], confirm_ts: int,
                      params: Params, lookback: int = 60) -> Optional[HtfContext]:
    """Build HTF curve context as of ``confirm_ts`` using only earlier bars."""
    closed = [c for c in curve if c.ts <= confirm_ts]
    if len(closed) < max(3, params.ema_period // 2):
        return None
    window = closed[-lookback:]
    closes = [c.close for c in closed]
    highs = [c.high for c in window]
    lows = [c.low for c in window]
    trend = htf_trend(closes, [c.high for c in closed], [c.low for c in closed],
                      params.ema_period)
    return HtfContext(trend=trend, range_low=min(lows), range_high=max(highs))


def _find_opposing(zone: Zone, all_zones: Sequence[Zone],
                   decision_index: int) -> Optional[float]:
    """Nearest valid opposing-type zone proximal in the profit direction,
    among zones confirmed before the decision (§2.5). None => open space."""
    want = ZoneType.SUPPLY if zone.ztype == ZoneType.DEMAND else ZoneType.DEMAND
    entry = zone.proximal
    best: Optional[float] = None
    for z in all_zones:
        if z is zone or z.ztype != want:
            continue
        if z.confirm_index >= decision_index:
            continue
        if zone.ztype == ZoneType.DEMAND:
            if z.proximal > entry and (best is None or z.proximal < best):
                best = z.proximal
        else:
            if z.proximal < entry and (best is None or z.proximal > best):
                best = z.proximal
    return best


def _hit(ztype: ZoneType, c: Candle, stop: float, target: float) -> tuple[bool, bool]:
    if ztype == ZoneType.DEMAND:
        return (c.low <= stop, c.high >= target)
    return (c.high >= stop, c.low <= target)


def _resolve_ambiguity(ztype: ZoneType, c: Candle, plan: TradePlan,
                       lower_tf: Optional[Sequence[Candle]]) -> str:
    """Same candle touched both SL and TP. Use one-TF-lower data if available;
    otherwise LOSS (§2.6, conservative by design)."""
    if lower_tf:
        for lc in lower_tf:
            if lc.ts < c.ts or lc.ts >= c.ts + _tf_ms_guess(c, lower_tf):
                continue
            sl, tp = _hit(ztype, lc, plan.stop, plan.target)
            if sl and not tp:
                return "LOSS"
            if tp and not sl:
                return "WIN"
            if sl and tp:
                return "LOSS"
    return "LOSS"


def _tf_ms_guess(c: Candle, lower_tf: Sequence[Candle]) -> int:
    if len(lower_tf) >= 2:
        return lower_tf[1].ts - lower_tf[0].ts
    return 1


def simulate_symbol(
    candles: Sequence[Candle],
    cfg: SimConfig,
    params: Params,
    curve_candles: Optional[Sequence[Candle]] = None,
    lower_tf_candles: Optional[Sequence[Candle]] = None,
) -> tuple[List[Trade], List[Zone]]:
    """Run the full pipeline for one symbol/TF: classify -> detect -> score ->
    simulate. Returns (trades, all_zones). Every zone is returned with its score
    so callers can bucket-log all zones, not just tradeable ones (§3)."""
    classified = classify(candles, params)
    zones = detect_zones(classified, cfg.symbol, cfg.tf, params)
    trades: List[Trade] = []

    for zone in zones:
        # Advance lifecycle to find fill; simulate the single allowed trade.
        trade = _simulate_zone(zone, zones, classified, cfg, params,
                               curve_candles, lower_tf_candles)
        if trade is not None:
            trades.append(trade)
    return trades, zones


def _simulate_zone(zone, all_zones, classified, cfg, params,
                   curve_candles, lower_tf_candles) -> Optional[Trade]:
    prior_tests = 0
    max_age = None if cfg.tf_is_curve else params.zone_max_age_bars_default

    n = len(classified)
    for i in range(zone.confirm_index + 1, n):
        c = classified[i].candle

        # break: close beyond distal, no fill -> zone dead
        if zone.ztype == ZoneType.DEMAND and c.close < zone.distal:
            return None
        if zone.ztype == ZoneType.SUPPLY and c.close > zone.distal:
            return None
        # expiry without fill
        if max_age is not None and (i - zone.confirm_index) > max_age:
            return None

        # fill? entry limit at proximal, active while fresh/tested(1)
        entry_allowed = prior_tests <= 1
        reaches = (c.low <= zone.proximal) if zone.ztype == ZoneType.DEMAND \
            else (c.high >= zone.proximal)

        if entry_allowed and reaches:
            return _open_and_manage(zone, all_zones, classified, i, prior_tests,
                                    cfg, params, curve_candles, lower_tf_candles)

        # not filled — did the candle tap the wick test band without reaching
        # the entry line? that is a prior test that ages the zone's freshness.
        if zone.candle_tests(c.low, c.high):
            prior_tests += 1
    return None


def _open_and_manage(zone, all_zones, classified, fill_i, prior_tests, cfg, params,
                     curve_candles, lower_tf_candles) -> Optional[Trade]:
    cost_buf = per_side_cost(cfg.market, cfg.symbol, zone.proximal)
    opposing = _find_opposing(zone, all_zones, fill_i)
    plan = build_trade_plan(zone, params, cost_buffer=cost_buf,
                            opposing_proximal=opposing)
    if plan is None:
        return None

    htf = build_htf_context(curve_candles, zone.confirm_ts, params) if curve_candles else None
    sc: ScoreResult = score_zone(
        zone, classified, params,
        prior_tests=prior_tests,
        opposing_proximal=opposing,
        trade_r=plan.r,
        htf=htf,
        decision_index=fill_i,
    )
    zone.score = sc.score
    zone.score_breakdown = sc.breakdown
    zone.state = ZoneState.CONSUMED

    # Trade filter (§2.5): only score >= MIN_SCORE actually trades.
    if sc.score < params.min_score:
        return None

    if plan.tp1 is not None:
        return _manage_scaleout(zone, plan, sc, classified, fill_i, cfg, params,
                                lower_tf_candles)
    return _manage_setforget(zone, plan, sc, classified, fill_i, cfg, params,
                             lower_tf_candles)


def _make_trade(zone, plan, sc, classified, fill_i, exit_k, exit_price,
                gross_r, cost, cfg) -> Trade:
    return Trade(
        zone=zone, plan=plan, score=sc.score, freshness=sc.breakdown["freshness"],
        entry_index=fill_i, exit_index=exit_k,
        entry_ts=classified[fill_i].candle.ts, exit_ts=classified[exit_k].candle.ts,
        entry=zone.proximal, exit_price=exit_price,
        outcome=("WIN" if gross_r > 0 else "LOSS"),
        gross_r=gross_r, cost_r=cost / plan.r, market=cfg.market,
    )


def _manage_setforget(zone, plan, sc, classified, fill_i, cfg, params, lower_tf):
    """Original set-and-forget management: one target, one stop (§2.6)."""
    for k in range(fill_i, len(classified)):
        c = classified[k].candle
        sl, tp = _hit(zone.ztype, c, plan.stop, plan.target)
        outcome = None
        exit_price = 0.0
        if sl and tp:
            outcome = _resolve_ambiguity(zone.ztype, c, plan, lower_tf)
            exit_price = plan.stop if outcome == "LOSS" else plan.target
        elif sl:
            outcome, exit_price = "LOSS", plan.stop
        elif tp:
            outcome, exit_price = "WIN", plan.target
        if outcome is not None:
            gross_r = plan.target_r if outcome == "WIN" else -1.0
            cost = round_trip_cost(cfg.market, cfg.symbol, zone.proximal, exit_price)
            return _make_trade(zone, plan, sc, classified, fill_i, k, exit_price,
                               gross_r, cost, cfg)
    return None


def _manage_scaleout(zone, plan, sc, classified, fill_i, cfg, params, lower_tf):
    """Scale-out management: take ``scale_fraction`` off at TP1, move the stop to
    breakeven, let the runner target the final target. Turns many round-trips to
    -1R into small wins — the profit-factor lever. Same conservative intrabar
    ambiguity rule as set-and-forget."""
    entry = zone.proximal
    frac = params.scale_fraction
    partial_r = frac * params.scale_tp1_r
    be = entry if params.scale_move_be else plan.stop
    partial_taken = False
    stop = plan.stop

    def reached(price, c):  # did candle c trade to `price` in the trade's favor?
        return c.high >= price if zone.ztype == ZoneType.DEMAND else c.low <= price

    def cost_of(runner_exit):
        # entry (full) + partial exit at TP1 (frac) + runner exit (1-frac), per side
        return (per_side_cost(cfg.market, cfg.symbol, entry)
                + frac * per_side_cost(cfg.market, cfg.symbol, plan.tp1)
                + (1 - frac) * per_side_cost(cfg.market, cfg.symbol, runner_exit))

    for k in range(fill_i, len(classified)):
        c = classified[k].candle
        if not partial_taken:
            sl, tp1 = _hit(zone.ztype, c, stop, plan.tp1)
            if sl and tp1:
                # conservative: assume the original stop hit before TP1
                if _resolve_ambiguity(zone.ztype, c, plan, lower_tf) == "LOSS":
                    cost = round_trip_cost(cfg.market, cfg.symbol, entry, stop)
                    return _make_trade(zone, plan, sc, classified, fill_i, k, stop,
                                       -1.0, cost, cfg)
                partial_taken, stop = True, be
            elif sl:
                cost = round_trip_cost(cfg.market, cfg.symbol, entry, stop)
                return _make_trade(zone, plan, sc, classified, fill_i, k, stop,
                                   -1.0, cost, cfg)
            elif tp1:
                partial_taken, stop = True, be
            else:
                continue
            # Partial just taken on THIS candle. Only credit the runner's final
            # target if the same candle printed it; the breakeven stop is not
            # armed until the next candle (this candle's low is the fill dip).
            if reached(plan.target, c):
                gross = partial_r + (1 - frac) * plan.target_r
                return _make_trade(zone, plan, sc, classified, fill_i, k, plan.target,
                                   gross, cost_of(plan.target), cfg)
            continue

        # Phase 2 (candles after TP1): stop is at breakeven.
        be_hit, tp = _hit(zone.ztype, c, be, plan.target)
        if be_hit:  # conservative: breakeven before final target on the same candle
            return _make_trade(zone, plan, sc, classified, fill_i, k, be,
                               partial_r, cost_of(be), cfg)
        if tp:
            gross = partial_r + (1 - frac) * plan.target_r
            return _make_trade(zone, plan, sc, classified, fill_i, k, plan.target,
                               gross, cost_of(plan.target), cfg)
    return None
