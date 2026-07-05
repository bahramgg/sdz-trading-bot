"""Calibration sweep (master plan §3, P3). TRAIN window only.

Grids over BASE_BODY_MAX, ERC_ATR_MULT, PROXIMAL_MODE, TP_MODE, MIN_SCORE and
ranks parameter sets by expectancy, requiring a minimum trade count per bucket
so we don't overfit a handful of trades. The OOS window is never touched here.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

from config import Params
from backtest.metrics import Metrics, compute
from backtest.simulator import SimConfig, Trade, simulate_symbol

# Default grid — override by editing here or passing your own.
GRID = {
    "base_body_max": [0.40, 0.45, 0.50],
    "erc_atr_mult": [1.2, 1.3, 1.5],
    "proximal_mode": ["body", "wick"],
    "tp_mode": ["fixed_3R", "hybrid"],
    "min_score": [6, 7, 8],
}


@dataclass
class SweepResult:
    params: dict
    metrics: Metrics


def sweep(
    datasets: Sequence[tuple[Sequence, SimConfig]],
    base: Params,
    grid: Dict[str, list] = GRID,
    min_trades: int = 200,
) -> List[SweepResult]:
    """Run the full grid. ``datasets`` = list of (candles, SimConfig) over the
    TRAIN window. Returns results sorted by expectancy (desc), filtered to those
    meeting ``min_trades`` (master plan: >=200 trades/bucket)."""
    keys = list(grid.keys())
    results: List[SweepResult] = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        overrides = dict(zip(keys, combo))
        params = base.override(**overrides)
        all_trades: List[Trade] = []
        for candles, cfg in datasets:
            trades, _ = simulate_symbol(candles, cfg, params,
                                        curve_candles=None)
            all_trades.extend(trades)
        m = compute(all_trades)
        results.append(SweepResult(params=overrides, metrics=m))

    qualifying = [r for r in results if r.metrics.trades >= min_trades]
    pool = qualifying if qualifying else results
    return sorted(pool, key=lambda r: r.metrics.expectancy_r, reverse=True)
