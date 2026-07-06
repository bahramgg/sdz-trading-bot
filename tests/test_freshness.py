"""Freshness enhancer must actually vary (§2.5).

Regression guard for the wick-test / body-fill model: a zone filled on the
first touch scores fresh (2); a zone whose test band was tapped before the fill
scores as a retest (1). Before this model every trade was fresh = 2.
"""
from __future__ import annotations

from config import Params
from engine.candles import classify
from engine.patterns import detect_zones
from backtest.simulator import SimConfig, simulate_symbol
from tests import synthetic

# min_score=1 so both setups trade regardless of the freshness point they lose.
P = Params.load().override(min_score=1)


def _fresh(candles):
    trades, _ = simulate_symbol(candles, SimConfig("crypto", "BTC/USDT", "1h"), P)
    assert trades, "expected a trade"
    return trades[0]


def test_first_touch_is_fresh():
    t = _fresh(synthetic.demand_dbr())
    assert t.freshness == 2
    assert t.outcome == "WIN"


def test_wick_test_then_fill_is_retest():
    t = _fresh(synthetic.demand_dbr_retest())
    assert t.freshness == 1                 # the pre-fill wick tap aged the zone
    assert t.outcome == "WIN"
    # one fewer point than the fresh version -> score differs by exactly 1
    fresh = _fresh(synthetic.demand_dbr())
    assert fresh.score - t.score == 1


def test_test_edge_is_wick_not_body():
    z = detect_zones(classify(synthetic.demand_dbr(), P), "T", "1h", P)[0]
    assert z.test_edge == 98.6              # base high (wick)
    assert z.proximal == 98.3               # body high (deeper entry line)
    assert z.test_edge != z.proximal
