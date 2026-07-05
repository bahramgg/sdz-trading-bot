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
        self._alerted: set[int] = set()          # confirm_ts of already-alerted zones
        self.paper: List[PaperTrade] = []

    def on_new_candles(self, candles: Sequence[Candle],
                       curve_candles: Optional[Sequence[Candle]] = None) -> List[str]:
        """Recompute zones on closed candles and return any new alert strings.

        Idempotent per zone: a given confirmed zone alerts at most once.
        """
        p = self.params
        classified = classify(candles, p)
        zones = detect_zones(classified, self.symbol, self.tf, p)
        alerts: List[str] = []
        last = candles[-1]

        for z in zones:
            if z.confirm_ts in self._alerted:
                continue
            plan = build_trade_plan(z, p)
            if plan is None:
                continue
            htf = None  # curve context wiring lives in the orchestrator
            res = score_zone(z, classified, p, prior_tests=z.test_count,
                             trade_r=plan.r, htf=htf,
                             decision_index=len(classified))
            z.score = res.score

            # Trigger 1: new zone confirmed with score >= ALERT_MIN_SCORE
            if res.score >= p.alert_min_score:
                alerts.append(telegram.format_zone_alert(z, plan, res.score))
                self._alerted.add(z.confirm_ts)
                self.paper.append(PaperTrade.open_from(z, plan, res.score, last.ts))
                continue

            # Trigger 2: price approaching a valid zone
            atr = z.atr_at_confirm
            if atr > 0:
                dist = abs(last.close - z.proximal)
                if dist <= p.approach_atr * atr:
                    alerts.append(telegram.format_approach_alert(z, dist / atr))
                    self._alerted.add(z.confirm_ts)

        # Trigger 3: resolve open paper trades against the latest closed candle
        for t in self.paper:
            t.update(last)
        return alerts


async def scan_loop(scanners: Sequence[SymbolScanner], poll_seconds: int = 60,
                    fetch=None, send=True) -> None:  # pragma: no cover (I/O loop)
    """Poll on candle close, emit alerts. ``fetch(symbol, tf)->candles`` injected
    for testability; the VPS deploy wires it to the live data source."""
    while True:
        for sc in scanners:
            if fetch is None:
                break
            candles = fetch(sc.symbol, sc.tf)
            for msg in sc.on_new_candles(candles):
                if send:
                    await telegram.send(msg)
                else:
                    print(msg)
        await asyncio.sleep(poll_seconds)
