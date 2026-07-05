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


def test_scanner_alerts_once_per_zone():
    cs = synthetic.demand_dbr()
    sc = SymbolScanner("BTC/USDT", "1h", "crypto", P.override(alert_min_score=6))
    first = sc.on_new_candles(cs)
    second = sc.on_new_candles(cs)          # same data -> no new alerts
    assert len(first) == 1
    assert second == []


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
