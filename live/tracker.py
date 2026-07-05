"""Forward paper-trade tracking (master plan §4, P5).

Every alerted setup is logged as a paper trade and resolved automatically as
new candles close, so forward expectancy can be compared against the backtest
(the P5 acceptance gate: forward within +/-0.15R of backtest).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from engine.candles import Candle
from engine.lifecycle import TradePlan
from engine.zones import Zone, ZoneType


@dataclass
class PaperTrade:
    symbol: str
    tf: str
    pattern: str
    score: int
    entry_ts: int
    entry: float
    stop: float
    target: float
    target_r: float
    ztype: ZoneType
    outcome: Optional[str] = None   # None while open, else WIN/LOSS
    exit_ts: Optional[int] = None
    realized_r: Optional[float] = None

    @classmethod
    def open_from(cls, zone: Zone, plan: TradePlan, score: int, entry_ts: int) -> "PaperTrade":
        return cls(symbol=zone.symbol, tf=zone.tf, pattern=zone.pattern.value,
                   score=score, entry_ts=entry_ts, entry=plan.entry,
                   stop=plan.stop, target=plan.target, target_r=plan.target_r,
                   ztype=zone.ztype)

    def update(self, c: Candle) -> bool:
        """Resolve against a newly closed candle. Returns True when it resolves.

        Conservative same-candle rule mirrors the backtester: SL+TP -> LOSS.
        """
        if self.outcome is not None:
            return False
        if self.ztype == ZoneType.DEMAND:
            sl, tp = c.low <= self.stop, c.high >= self.target
        else:
            sl, tp = c.high >= self.stop, c.low <= self.target
        if sl and tp:
            self.outcome, self.realized_r = "LOSS", -1.0
        elif sl:
            self.outcome, self.realized_r = "LOSS", -1.0
        elif tp:
            self.outcome, self.realized_r = "WIN", self.target_r
        else:
            return False
        self.exit_ts = c.ts
        return True


def summary(trades: Sequence[PaperTrade]) -> dict:
    """Weekly-summary stats (win rate + expectancy) over resolved paper trades."""
    resolved = [t for t in trades if t.outcome is not None]
    if not resolved:
        return {"trades": 0, "win_rate": 0.0, "expectancy_r": 0.0}
    rs = [t.realized_r for t in resolved]
    wins = [r for r in rs if r > 0]
    return {
        "trades": len(resolved),
        "win_rate": len(wins) / len(resolved),
        "expectancy_r": sum(rs) / len(resolved),
    }
