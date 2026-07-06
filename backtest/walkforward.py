"""Walk-forward analysis (master plan §3, P3 "walk-forward optional").

Rolling anchored windows: calibrate on a TRAIN window, then trade the next OUT
window with the winning params — which that window never saw — and slide
forward. Concatenating every OUT segment yields one fully out-of-sample track
record, immune to a single lucky train/test split. This is the honest robustness
test: does re-calibrating and stepping forward keep the edge?
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from config import Params
from backtest.calibrate import sweep
from backtest.metrics import Metrics, compute
from backtest.simulator import SimConfig, Trade, simulate_symbol

# Focused grid for per-fold calibration (proximal_mode=body always won the full
# sweeps; keep the levers that actually moved expectancy so folds stay fast).
WF_GRID = {
    "erc_atr_mult": [1.2, 1.3, 1.5],
    "tp_mode": ["fixed_3R", "hybrid"],
    "min_score": [7, 8],
}


def _ms(d: dt.datetime) -> int:
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def _add_months(d: dt.datetime, n: int) -> dt.datetime:
    m = d.month - 1 + n
    return dt.datetime(d.year + m // 12, m % 12 + 1, 1)


@dataclass
class Fold:
    train_start: str
    train_end: str
    out_start: str
    out_end: str
    params: dict
    train_metrics: Metrics
    out_metrics: Metrics


def _datasets(store, market: str, symbols, tfs, curve_tf, start_ms, end_ms,
              min_bars: int):
    out = []
    for sym in symbols:
        curve = store.load_candles(sym, curve_tf, start_ms, end_ms)
        for tf in tfs:
            cs = store.load_candles(sym, tf, start_ms, end_ms)
            if len(cs) < min_bars:
                continue
            cfg = SimConfig(market, sym, tf, tf_is_curve=(tf == curve_tf))
            out.append((cs, cfg, curve if tf != curve_tf else None))
    return out


def walk_forward(
    store, market: str, symbols: Sequence[str], tfs: Sequence[str], curve_tf: str,
    base: Params, first_train: dt.datetime, last: dt.datetime,
    train_months: int = 24, out_months: int = 6, step_months: int = 6,
    grid: Dict[str, list] = WF_GRID, fold_min_trades: int = 40,
) -> tuple[List[Fold], List[Trade]]:
    """Run anchored-forward folds. Returns (folds, all_out_of_sample_trades)."""
    folds: List[Fold] = []
    oos_trades: List[Trade] = []
    min_bars = base.atr_period + 5

    train_start = first_train
    while True:
        train_end = _add_months(train_start, train_months)
        out_end = _add_months(train_end, out_months)
        if out_end > last:
            break

        train_ds = _datasets(store, market, symbols, tfs, curve_tf,
                             _ms(train_start), _ms(train_end), min_bars)
        if not train_ds:
            train_start = _add_months(train_start, step_months)
            continue
        ranked = sweep(train_ds, base, grid=grid, min_trades=fold_min_trades)
        best = ranked[0]
        params = base.override(**best.params)

        out_ds = _datasets(store, market, symbols, tfs, curve_tf,
                          _ms(train_end), _ms(out_end), min_bars)
        fold_trades: List[Trade] = []
        for cs, cfg, curve in out_ds:
            tr, _ = simulate_symbol(cs, cfg, params, curve_candles=curve)
            fold_trades.extend(tr)
        oos_trades.extend(fold_trades)

        folds.append(Fold(
            train_start=train_start.date().isoformat(),
            train_end=train_end.date().isoformat(),
            out_start=train_end.date().isoformat(),
            out_end=out_end.date().isoformat(),
            params=best.params,
            train_metrics=best.metrics,
            out_metrics=compute(fold_trades),
        ))
        train_start = _add_months(train_start, step_months)

    return folds, oos_trades
