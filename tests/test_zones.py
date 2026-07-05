"""Zone lifecycle (§2.4), trade plan (§2.6) and odds-enhancer score (§2.5)."""
from __future__ import annotations

from config import Params
from engine.candles import classify
from engine.lifecycle import advance_lifecycle, build_trade_plan
from engine.patterns import detect_zones
from engine.score import score_zone
from engine.zones import ZoneState, ZoneType
from tests import synthetic

P = Params.load()


def _demand_zone():
    cs = synthetic.demand_dbr()
    cl = classify(cs, P)
    z = detect_zones(cl, "TEST", "1h", P)[0]
    return z, cl


def test_trade_plan_demand():
    z, cl = _demand_zone()
    plan = build_trade_plan(z, P)
    assert plan.entry == z.proximal
    assert plan.stop < z.distal                      # stop below distal for demand
    assert plan.r > 0
    assert abs(plan.target_r - 3.0) < 1e-9           # fixed_3R default
    assert plan.target > plan.entry


def test_score_fresh_dbr_is_eight():
    z, cl = _demand_zone()
    res = score_zone(z, cl, P, prior_tests=0, opposing_proximal=None,
                     trade_r=build_trade_plan(z, P).r)
    assert res.breakdown["freshness"] == 2
    assert res.breakdown["time_at_base"] == 2
    assert res.breakdown["profit_margin"] == 2       # open space
    assert res.breakdown["htf_alignment"] == 1       # neutral (no HTF)
    assert res.score == 8


def test_freshness_degrades_with_tests():
    z, cl = _demand_zone()
    r = build_trade_plan(z, P).r
    assert score_zone(z, cl, P, prior_tests=1, trade_r=r).breakdown["freshness"] == 1
    assert score_zone(z, cl, P, prior_tests=3, trade_r=r).breakdown["freshness"] == 0


def test_lifecycle_breaks_on_close_beyond_distal():
    z, cl = _demand_zone()
    # append a candle that closes well below distal -> broken
    last = cl[-1].candle
    broken = last.__class__(last.ts + 3_600_000, 97.0, 97.1, 90.0, 90.5)
    from engine.candles import Classified
    cl = list(cl) + [Classified(broken, atr=1.0, is_erc=False, is_basing=True)]
    z2 = advance_lifecycle(z, cl, P)
    assert z2.state == ZoneState.BROKEN
