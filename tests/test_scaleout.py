"""Scale-out exit management (profit-factor lever).

With exit_mode=scaleout, scale_fraction=0.5, scale_tp1_r=1.0 and a fixed_3R
runner, the R outcomes are:
  - full winner (runner reaches target): 0.5*1 + 0.5*3 = +2.0R
  - taps TP1 then back to breakeven:      0.5*1 + 0.5*0 = +0.5R (a small WIN)
  - stops out before TP1:                 -1.0R
"""
from __future__ import annotations

from config import Params
from backtest.simulator import SimConfig, simulate_symbol
from tests import synthetic

SO = Params.load().override(exit_mode="scaleout", scale_fraction=0.5,
                            scale_tp1_r=1.0, min_score=1)
SF = Params.load().override(exit_mode="setforget", min_score=1)


def _one(candles, params):
    trades, _ = simulate_symbol(candles, SimConfig("crypto", "BTC/USDT", "1h"), params)
    assert trades, "expected a trade"
    return trades[0]


def test_scaleout_full_winner_is_two_r():
    t = _one(synthetic.demand_dbr(), SO)
    assert t.outcome == "WIN"
    assert abs(t.gross_r - 2.0) < 1e-9        # 0.5 partial + 1.5 runner
    # set-and-forget on the same setup is the full 3R
    assert abs(_one(synthetic.demand_dbr(), SF).gross_r - 3.0) < 1e-9


def test_scaleout_tp1_then_breakeven_is_small_win():
    t = _one(synthetic.demand_dbr_scaleout_be(), SO)
    assert t.outcome == "WIN"
    assert abs(t.gross_r - 0.5) < 1e-9        # partial only, runner scratched at BE


def test_scaleout_trade_plan_has_tp1():
    from engine.candles import classify
    from engine.patterns import detect_zones
    from engine.lifecycle import build_trade_plan
    z = detect_zones(classify(synthetic.demand_dbr(), SO), "T", "1h", SO)[0]
    plan = build_trade_plan(z, SO)
    assert plan.tp1 is not None
    assert plan.tp1 == z.proximal + 1.0 * plan.r    # demand: entry + tp1_r * R
    # set-and-forget builds no TP1
    assert build_trade_plan(z, SF).tp1 is None
