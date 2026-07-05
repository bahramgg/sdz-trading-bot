"""Backtester determinism, cost application, and the intrabar ambiguity rule."""
from __future__ import annotations

from config import Params
from engine.zones import ZoneType
from backtest.metrics import compute
from backtest.simulator import (SimConfig, _resolve_ambiguity, simulate_symbol)
from engine.lifecycle import TradePlan
from tests import synthetic

P = Params.load()


def test_demand_trade_is_a_win():
    trades, zones = simulate_symbol(synthetic.demand_dbr(),
                                    SimConfig("crypto", "BTC/USDT", "1h"), P)
    assert len(trades) == 1
    t = trades[0]
    assert t.outcome == "WIN"
    assert t.score == 8
    assert t.gross_r == 3.0
    assert t.cost_r > 0                        # costs actually applied
    assert 2.5 < t.realized_r < 3.0            # win minus costs


def test_determinism_same_input_same_trades():
    cfg = SimConfig("crypto", "BTC/USDT", "1h")
    a, _ = simulate_symbol(synthetic.demand_dbr(), cfg, P)
    b, _ = simulate_symbol(synthetic.demand_dbr(), cfg, P)
    assert [(t.entry_index, t.exit_index, t.outcome, round(t.realized_r, 6)) for t in a] \
        == [(t.entry_index, t.exit_index, t.outcome, round(t.realized_r, 6)) for t in b]


def test_min_score_filter_blocks_low_scores():
    strict = P.override(min_score=10)          # our zone scores 8 -> filtered out
    trades, _ = simulate_symbol(synthetic.demand_dbr(),
                                SimConfig("crypto", "BTC/USDT", "1h"), strict)
    assert trades == []


def test_intrabar_ambiguity_defaults_to_loss():
    plan = TradePlan(ZoneType.DEMAND, entry=100.0, stop=99.0, target=103.0,
                     r=1.0, target_r=3.0)
    from engine.candles import Candle
    both = Candle(0, 100.0, 103.5, 98.5, 100.0)   # touches both TP and SL
    assert _resolve_ambiguity(ZoneType.DEMAND, both, plan, lower_tf=None) == "LOSS"


def test_metrics_expectancy():
    trades, _ = simulate_symbol(synthetic.demand_dbr(),
                                SimConfig("crypto", "BTC/USDT", "1h"), P)
    m = compute(trades)
    assert m.trades == 1
    assert m.win_rate == 1.0
    assert m.expectancy_r == trades[0].realized_r
