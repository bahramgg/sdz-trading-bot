"""Metrics + bucketing (master plan §3).

Expectancy (R) is the headline number the P4 gate reads. Everything is in R so
results are comparable across symbols and account sizes.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Sequence

from backtest.simulator import Trade


@dataclass
class Metrics:
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float
    profit_factor: float
    max_drawdown_r: float
    total_r: float

    def as_row(self) -> dict:
        return asdict(self)


def compute(trades: Sequence[Trade]) -> Metrics:
    n = len(trades)
    if n == 0:
        return Metrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    rs = [t.realized_r for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)  # positive magnitude
    total = sum(rs)
    expectancy = total / n
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    # max drawdown on the cumulative-R equity curve (trades in chrono order)
    ordered = sorted(trades, key=lambda t: t.exit_ts)
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for t in ordered:
        equity += t.realized_r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return Metrics(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / n,
        avg_win_r=(gross_win / len(wins)) if wins else 0.0,
        avg_loss_r=(sum(losses) / len(losses)) if losses else 0.0,
        expectancy_r=expectancy,
        profit_factor=pf,
        max_drawdown_r=max_dd,
        total_r=total,
    )


def bucket(trades: Sequence[Trade], key: Callable[[Trade], object]) -> Dict[object, Metrics]:
    groups: Dict[object, List[Trade]] = {}
    for t in trades:
        groups.setdefault(key(t), []).append(t)
    return {k: compute(v) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}


# Standard bucket dimensions from §3.
def by_score(trades):   return bucket(trades, lambda t: t.score)
def by_pattern(trades): return bucket(trades, lambda t: t.zone.pattern.value)
def by_tf(trades):      return bucket(trades, lambda t: t.zone.tf)
def by_market(trades):  return bucket(trades, lambda t: t.market)
def by_freshness(trades): return bucket(trades, lambda t: t.freshness)
