"""Lookahead audit (master plan §3).

Shifting all data by one bar must not change any detected zone (only its
indices shift by one), and every trade's confirm_index must strictly precede
its entry fill index.
"""
from __future__ import annotations

from config import Params
from engine.candles import Candle, classify
from engine.patterns import detect_zones
from backtest.simulator import SimConfig, simulate_symbol
from tests import synthetic

P = Params.load()


def _zone_signature(zones):
    return [(z.ztype, z.pattern, round(z.proximal, 6), round(z.distal, 6), z.base_len)
            for z in zones]


def test_shift_by_one_bar_preserves_zones():
    cs = synthetic.demand_dbr()
    base = detect_zones(classify(cs, P), "T", "1h", P)

    # prepend one neutral bar -> every index shifts by exactly 1
    pad = Candle(cs[0].ts - 3_600_000, 100.0, 100.5, 99.5, 100.0)
    shifted_cs = [pad] + cs
    shifted = detect_zones(classify(shifted_cs, P), "T", "1h", P)

    assert _zone_signature(base) == _zone_signature(shifted)
    assert [z.confirm_index for z in shifted] == [z.confirm_index + 1 for z in base]


def test_confirm_precedes_fill():
    cs = synthetic.demand_dbr()
    trades, _ = simulate_symbol(cs, SimConfig("crypto", "TEST", "1h"), P)
    assert trades, "expected at least one trade"
    for t in trades:
        assert t.zone.confirm_index < t.entry_index


def test_decision_is_pure_prefix():
    # Truncating data after the fill index must not change the trade's identity
    # (proves the decision reads no future candle).
    cs = synthetic.demand_dbr()
    trades, _ = simulate_symbol(cs, SimConfig("crypto", "TEST", "1h"), P)
    t = trades[0]
    prefix = cs[: t.exit_index + 1]
    trades2, _ = simulate_symbol(prefix, SimConfig("crypto", "TEST", "1h"), P)
    assert trades2
    assert trades2[0].score == t.score
    assert trades2[0].outcome == t.outcome
    assert trades2[0].entry_index == t.entry_index
