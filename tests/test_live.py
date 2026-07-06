"""Live scanner: alert formatting, one-alert-per-zone, paper resolution (§4)."""
from __future__ import annotations

from config import Params
from engine.lifecycle import build_trade_plan
from engine.candles import classify
from engine.patterns import detect_zones
from live.scanner import SymbolScanner
from live.telegram import format_zone_alert
from live.tracker import PaperTrade, summary
from tests import synthetic

P = Params.load()


def test_alert_format_matches_spec_shape():
    cs = synthetic.demand_dbr()
    z = detect_zones(classify(cs, P), "BTC/USDT", "1h", P)[0]
    plan = build_trade_plan(z, P)
    msg = format_zone_alert(z, plan, score=8)
    assert msg.startswith("[SDZ] BTCUSDT 1H DEMAND fresh s8 |")
    assert "prox" in msg and "SL" in msg and "TP" in msg and "DBR" in msg
    assert "3.0R" in msg


def test_warmup_suppresses_backlog():
    # Zone confirmed mid-history, price now far away: a cold start must NOT dump
    # the historical zone as a "new" alert.
    sc = SymbolScanner("BTC/USDT", "1h", "crypto", P.override(alert_min_score=6))
    out = sc.on_new_candles(synthetic.demand_dbr())
    assert not any(a.startswith("[SDZ] BTCUSDT") for a in out)


def test_new_zone_alerts_once():
    cs = synthetic.demand_dbr()
    sc = SymbolScanner("BTC/USDT", "1h", "crypto", P.override(alert_min_score=6))
    assert sc.on_new_candles(cs[:21]) == []          # warmup, before confirm
    a = sc.on_new_candles(cs[:22])                    # confirm bar -> one new-zone alert
    assert len([x for x in a if x.startswith("[SDZ] BTCUSDT")]) == 1
    assert len(sc.paper) == 1
    b = sc.on_new_candles(cs[:23])                    # next bar -> no repeat new-zone alert
    assert not any(x.startswith("[SDZ] BTCUSDT") for x in b)


def test_paper_trade_resolves_win():
    cs = synthetic.demand_dbr()
    z = detect_zones(classify(cs, P), "BTC/USDT", "1h", P)[0]
    plan = build_trade_plan(z, P)
    pt = PaperTrade.open_from(z, plan, 8, entry_ts=z.confirm_ts)
    # feed a candle that reaches target
    from engine.candles import Candle
    tp_candle = Candle(z.confirm_ts + 1, plan.entry, plan.target + 0.5, plan.entry, plan.target)
    assert pt.update(tp_candle) is True
    assert pt.outcome == "WIN"
    assert summary([pt])["win_rate"] == 1.0
