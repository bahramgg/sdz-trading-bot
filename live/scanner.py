"""Live scanner — Sentinel pattern (master plan §4).

Async loop per (symbol, TF): on candle close -> update OHLCV -> run the zone
lifecycle -> evaluate alert triggers. Candle-close driven only; the currently
forming bar is never used (§1.4). No auto-execution in v1.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Sequence

from config import Params, watchlist
from data.store import Store
from engine.candles import Candle, classify
from engine.lifecycle import build_trade_plan
from engine.patterns import detect_zones
from engine.score import HtfContext, score_zone
from engine.zones import Zone, ZoneState
from live import telegram
from live.tracker import PaperTrade


class SymbolScanner:
    """Holds per-(symbol,tf) state and emits alerts as new candles close."""

    def __init__(self, symbol: str, tf: str, market: str, params: Params,
                 curve_tf: Optional[str] = None):
        self.symbol = symbol
        self.tf = tf
        self.market = market
        self.params = params
        self.curve_tf = curve_tf
        self._alerted: set[int] = set()          # confirm_ts of new-zone-alerted zones
        self._approached: set[int] = set()       # confirm_ts of approach-alerted zones
        self._last_seen_ts: Optional[int] = None  # last candle ts processed (warmup marker)
        self.paper: List[PaperTrade] = []

    def on_new_candles(self, candles: Sequence[Candle],
                       curve_candles: Optional[Sequence[Candle]] = None) -> List[str]:
        """Recompute zones on closed candles and return new alert strings.

        First call is a **warmup**: it seeds state from existing history and does
        NOT fire new-zone alerts for the backlog — only zones that confirm *after*
        the scanner starts trigger a new-zone alert. Approach alerts (price near a
        still-valid zone) fire on any pass. Each zone alerts at most once per kind.
        """
        from engine.lifecycle import advance_lifecycle
        from engine.zones import ZoneState
        from backtest.simulator import build_htf_context

        p = self.params
        classified = classify(candles, p)
        zones = detect_zones(classified, self.symbol, self.tf, p)
        alerts: List[str] = []
        last = candles[-1]
        warmup = self._last_seen_ts is None
        tf_is_curve = self.curve_tf is None
        # "New" means confirmed after the last bar we processed. On a cold start we
        # only treat a zone confirmed on the very latest bar as new, so a fresh
        # scanner surfaces a just-formed setup but not the whole historical backlog.
        threshold = (candles[-2].ts if len(candles) >= 2 else last.ts - 1) \
            if warmup else self._last_seen_ts

        for z in zones:
            advance_lifecycle(z, classified, p, tf_is_curve=tf_is_curve)
            valid = z.state in (ZoneState.FRESH, ZoneState.TESTED)

            plan = build_trade_plan(z, p)
            if plan is None:
                continue
            htf = (build_htf_context(curve_candles, z.confirm_ts, p)
                   if curve_candles else None)
            res = score_zone(z, classified, p, prior_tests=z.test_count,
                             trade_r=plan.r, htf=htf, decision_index=len(classified))
            z.score = res.score

            newly_confirmed = z.confirm_ts > threshold

            # Trigger 1: a NEW zone confirmed since the scanner started, valid,
            # scoring at/above the alert threshold.
            if (newly_confirmed and valid and res.score >= p.alert_min_score
                    and z.confirm_ts not in self._alerted):
                alerts.append(telegram.format_zone_alert(z, plan, res.score))
                self._alerted.add(z.confirm_ts)
                self.paper.append(PaperTrade.open_from(z, plan, res.score, last.ts))
                continue

            # Trigger 2: price approaching a still-valid zone (fires on any pass).
            atr = z.atr_at_confirm
            if valid and atr > 0 and z.confirm_ts not in self._approached:
                dist = abs(last.close - z.proximal)
                if dist <= p.approach_atr * atr:
                    alerts.append(telegram.format_approach_alert(z, dist / atr))
                    self._approached.add(z.confirm_ts)

        # On warmup, remember every existing zone so it can never later be
        # mistaken for "new" (belt-and-suspenders with the ts guard above).
        if warmup:
            self._alerted.update(z.confirm_ts for z in zones)

        # Trigger 3: resolve open paper trades against the latest closed candle.
        for t in self.paper:
            t.update(last)

        self._last_seen_ts = last.ts
        return alerts


async def scan_once(scanners: Sequence[SymbolScanner], fetch, curve_fetch=None,
                    send: bool = True) -> List[str]:  # pragma: no cover (I/O)
    """One pass over all scanners. ``fetch(symbol, tf)->candles`` and optional
    ``curve_fetch(symbol)->curve_candles`` are injected. Returns emitted alerts."""
    emitted: List[str] = []
    for sc in scanners:
        candles = fetch(sc.symbol, sc.tf)
        if not candles:
            continue
        curve = curve_fetch(sc.symbol) if curve_fetch else None
        for msg in sc.on_new_candles(candles, curve_candles=curve):
            emitted.append(msg)
            if send:
                await telegram.send(msg)
            else:
                print(msg)
    return emitted


async def scan_loop(scanners: Sequence[SymbolScanner], poll_seconds: int = 60,
                    fetch=None, curve_fetch=None, send=True) -> None:  # pragma: no cover
    """Poll on candle close, emit alerts. The first pass warms up each scanner
    (no backlog spam); subsequent passes emit only new confirmations/approaches."""
    if fetch is None:
        return
    while True:
        await scan_once(scanners, fetch, curve_fetch, send)
        await asyncio.sleep(poll_seconds)
