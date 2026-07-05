"""Pattern + zone-boundary detection (master plan §2.2, §2.3)."""
from __future__ import annotations

from config import Params
from engine.candles import classify
from engine.patterns import detect_zones
from engine.zones import Pattern, ZoneType
from tests import synthetic

P = Params.load()


def test_demand_dbr_detected():
    cs = synthetic.demand_dbr()
    zones = detect_zones(classify(cs, P), "TEST", "1h", P)
    assert len(zones) == 1
    z = zones[0]
    assert z.ztype == ZoneType.DEMAND
    assert z.pattern == Pattern.DBR
    assert z.proximal == 98.3            # body-based proximal
    assert z.distal == 97.8              # base low
    assert z.base_len == 2


def test_supply_rbd_detected():
    cs = synthetic.supply_rbd()
    zones = detect_zones(classify(cs, P), "TEST", "1h", P)
    assert len(zones) == 1
    z = zones[0]
    assert z.ztype == ZoneType.SUPPLY
    assert z.pattern == Pattern.RBD
    assert z.distal == 102.2             # base high
    assert z.base_len == 2


def test_flat_series_has_no_zones():
    cs = synthetic.flat_no_zone()
    zones = detect_zones(classify(cs, P), "TEST", "1h", P)
    assert zones == []


def test_leg_out_must_leave_base():
    # leg-out that does not close beyond the base extreme is rejected.
    cs = synthetic.demand_dbr()
    # neuter the leg-out close so it stays inside the base high (98.6)
    lo = cs[21]
    cs[21] = lo.__class__(lo.ts, lo.open, 98.55, lo.low, 98.4)
    zones = detect_zones(classify(cs, P), "TEST", "1h", P)
    assert all(z.leg_out_index != 21 for z in zones)


def test_oversized_zone_discarded():
    cs = synthetic.demand_dbr()
    # widen the base low massively so height > ZONE_MAX_ATR * atr
    b = cs[19]
    cs[19] = b.__class__(b.ts, b.open, b.high, 90.0, b.close)
    zones = detect_zones(classify(cs, P), "TEST", "1h", P)
    assert zones == []
