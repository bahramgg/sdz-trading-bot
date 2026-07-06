"""Forward paper-trade tracking (master plan §4, P5 — the iron-rule gate).

Runs the *exact* backtest pipeline on freshly fetched closed candles, so forward
results can never diverge from backtest logic. Only setups that confirm at or
after the tracking start are recorded; each resolved trade is persisted (keyed by
symbol/tf/confirm_ts) to a git-committed JSON file so the record survives the
ephemeral container and accumulates across scheduled runs.

The comparison that matters (P5 acceptance): forward expectancy within ±0.15R of
the backtest expectation.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Callable, Dict, List, Optional, Sequence

from config import Params
from backtest.metrics import compute
from backtest.simulator import SimConfig, simulate_symbol
from engine.candles import Candle

_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "forward", "forward_log.json")


def _key(symbol: str, tf: str, confirm_ts: int) -> str:
    return f"{symbol}|{tf}|{confirm_ts}"


class ForwardTracker:
    def __init__(self, params: Params, path: str = _LOG_PATH):
        self.params = params
        self.path = path
        self.meta: Dict = {"tracking_start_ts": None, "updated_ts": None}
        self.trades: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.meta = data.get("meta", self.meta)
            self.trades = data.get("trades", {})

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"meta": self.meta, "trades": self.trades}, fh, indent=2,
                      sort_keys=True)

    def start(self, now_ts: int) -> None:
        """Bootstrap: begin tracking setups that confirm from now on."""
        if self.meta.get("tracking_start_ts") is None:
            self.meta["tracking_start_ts"] = now_ts

    def step(self, market: str, symbols: Sequence[str], tfs: Sequence[str],
             curve_tf: str, fetch: Callable[[str, str], List[Candle]],
             now_ts: int) -> int:
        """One pass: simulate each stream on fresh candles, record newly-resolved
        trades that confirmed at/after tracking_start. Returns #new records."""
        self.start(now_ts)
        start_ts = self.meta["tracking_start_ts"]
        added = 0
        for sym in symbols:
            curve = fetch(sym, curve_tf)
            for tf in tfs:
                candles = fetch(sym, tf)
                if len(candles) < self.params.atr_period + 5:
                    continue
                cfg = SimConfig(market, sym, tf, tf_is_curve=(tf == curve_tf))
                trades, _ = simulate_symbol(
                    candles, cfg, self.params,
                    curve_candles=(curve if tf != curve_tf else None))
                for t in trades:
                    if t.zone.confirm_ts < start_ts:
                        continue  # setup predates tracking -> not a forward trade
                    k = _key(sym, tf, t.zone.confirm_ts)
                    if k in self.trades:
                        continue
                    self.trades[k] = {
                        "symbol": sym, "tf": tf, "market": market,
                        "pattern": t.zone.pattern.value, "score": t.score,
                        "confirm_ts": t.zone.confirm_ts,
                        "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
                        "entry": round(t.entry, 6), "stop": round(t.plan.stop, 6),
                        "target": round(t.plan.target, 6),
                        "outcome": t.outcome, "gross_r": round(t.gross_r, 4),
                        "realized_r": round(t.realized_r, 4),
                    }
                    added += 1
        self.meta["updated_ts"] = now_ts
        return added

    def summary(self) -> dict:
        recs = list(self.trades.values())
        if not recs:
            return {"trades": 0, "expectancy_r": 0.0, "win_rate": 0.0,
                    "profit_factor": 0.0}
        rs = [r["realized_r"] for r in recs]
        wins = [r for r in rs if r > 0]
        gl = -sum(r for r in rs if r <= 0)
        gw = sum(wins)
        return {
            "trades": len(recs),
            "expectancy_r": sum(rs) / len(rs),
            "win_rate": len(wins) / len(recs),
            "profit_factor": (gw / gl) if gl > 0 else float("inf"),
        }
