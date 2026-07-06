"""Forward tracker: records post-start resolved trades, dedups, persists."""
from __future__ import annotations

import os

from config import Params
from live.forward import ForwardTracker
from tests import synthetic

P = Params.load()
# demand_dbr's leg-out confirms at ts = base + 21*1h
_CONFIRM = 1_600_000_000_000 + 21 * 3_600_000


def _fetch(symbol, tf):
    return synthetic.demand_dbr()


def test_records_and_dedups(tmp_path):
    t = ForwardTracker(P, path=os.path.join(tmp_path, "fwd.json"))
    now = 1_600_000_000_000            # before the setup confirms -> it counts as forward
    added = t.step("crypto", ["BTC/USDT"], ["1h"], "1d", _fetch, now)
    assert added == 1
    assert t.step("crypto", ["BTC/USDT"], ["1h"], "1d", _fetch, now) == 0  # dedup
    s = t.summary()
    assert s["trades"] == 1
    assert s["expectancy_r"] > 0        # demand_dbr is a winner


def test_setups_before_start_are_ignored(tmp_path):
    t = ForwardTracker(P, path=os.path.join(tmp_path, "fwd.json"))
    now = _CONFIRM + 10 * 3_600_000     # tracking starts AFTER the setup confirmed
    assert t.step("crypto", ["BTC/USDT"], ["1h"], "1d", _fetch, now) == 0


def test_persistence_roundtrip(tmp_path):
    path = os.path.join(tmp_path, "fwd.json")
    t = ForwardTracker(P, path=path)
    t.step("crypto", ["BTC/USDT"], ["1h"], "1d", _fetch, 1_600_000_000_000)
    t.save()
    t2 = ForwardTracker(P, path=path)   # reload
    assert t2.summary()["trades"] == 1
    assert t2.meta["tracking_start_ts"] == 1_600_000_000_000
