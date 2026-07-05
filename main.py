#!/usr/bin/env python3
"""SDZ-Sentinel CLI: fetch | backtest | calibrate | scan (master plan §5).

Examples:
  python main.py fetch --market crypto --since 2019-01-01
  python main.py backtest --market crypto --start 2024-01-01 --end 2026-06-30
  python main.py calibrate --market crypto
  python main.py scan --market crypto
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import List, Optional

from config import Params, validation_window, watchlist
from data.store import Store


def _ms(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _market_of(symbol: str) -> str:
    return "crypto" if "/" in symbol else "forex"


def _curve_tf(market: str) -> str:
    return "1d" if market == "crypto" else "4h"


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #
def cmd_fetch(args) -> int:
    wl = watchlist()
    store = Store(args.db)
    since = _ms(args.since)
    until = _ms(args.until) if args.until else _now_ms()
    markets = [args.market] if args.market else ["crypto", "forex"]

    for market in markets:
        cfg = wl[market]
        for symbol in cfg["symbols"]:
            for tf in cfg["timeframes"]:
                try:
                    rows = _fetch_rows(market, symbol, tf, since, until)
                except Exception as exc:
                    print(f"  ! {market} {symbol} {tf}: {exc}", file=sys.stderr)
                    continue
                n = store.upsert_ohlcv(symbol, tf, rows)
                lo, hi, total = store.ohlcv_span(symbol, tf)
                print(f"  {market} {symbol} {tf}: +{n} rows (total {total})")
    store.close()
    return 0


def _fetch_rows(market: str, symbol: str, tf: str, since: int, until: int) -> List[list]:
    if market == "crypto":
        # Binance public data has the deepest history (back to listing); ccxt
        # (OKX/Bybit) is the live-scan source. Fall back to ccxt on error.
        try:
            from data import binance_vision
            rows = binance_vision.fetch_ohlcv(symbol, tf, since, until)
            if rows:
                return rows
        except Exception:
            pass
        from data import ccxt_fetch
        return ccxt_fetch.fetch_ohlcv(symbol, tf, since, until)
    else:
        from data import yf_fetch
        return yf_fetch.fetch_ohlcv(symbol, tf)


# --------------------------------------------------------------------------- #
# backtest
# --------------------------------------------------------------------------- #
def cmd_backtest(args) -> int:
    from backtest.simulator import SimConfig, simulate_symbol
    from backtest.report import write_report_md, write_trades_csv, write_equity_png

    params = Params.load()
    wl = watchlist()
    store = Store(args.db)
    start = _ms(args.start) if args.start else None
    end = _ms(args.end) if args.end else None
    markets = [args.market] if args.market else ["crypto", "forex"]

    all_trades = []
    for market in markets:
        cfg = wl[market]
        curve_tf = _curve_tf(market)
        for symbol in cfg["symbols"]:
            curve = store.load_candles(symbol, curve_tf, start, end)
            for tf in cfg["timeframes"]:
                candles = store.load_candles(symbol, tf, start, end)
                if len(candles) < params.atr_period + 5:
                    continue
                sc = SimConfig(market=market, symbol=symbol, tf=tf,
                               tf_is_curve=(tf == curve_tf))
                trades, zones = simulate_symbol(
                    candles, sc, params,
                    curve_candles=curve if tf != curve_tf else None)
                all_trades.extend(trades)
                print(f"  {market} {symbol} {tf}: {len(trades)} trades / {len(zones)} zones")
    store.close()

    outdir = args.out
    write_trades_csv(all_trades, f"{outdir}/trades.csv")
    overall = write_report_md(all_trades, f"{outdir}/report.md",
                              title="SDZ-Sentinel Backtest")
    png_ok = write_equity_png(all_trades, f"{outdir}/equity.png")
    print(f"\nOverall: {overall.trades} trades | expectancy {overall.expectancy_r:+.3f}R "
          f"| PF {overall.profit_factor:.2f}")
    print(f"Report: {outdir}/report.md" + ("" if png_ok else " (equity.png skipped: no matplotlib)"))

    if args.gate:
        _print_p4_gate(overall)
    return 0


def _print_p4_gate(m) -> None:
    ok = (m.expectancy_r >= 0.15 and m.profit_factor >= 1.25 and m.trades >= 100)
    verdict = "GO" if ok else "NO-GO"
    print(f"\n=== P4 OOS GATE: {verdict} ===")
    print(f"  expectancy >= +0.15R : {m.expectancy_r:+.3f}  [{'ok' if m.expectancy_r>=0.15 else 'fail'}]")
    print(f"  profit factor >= 1.25: {m.profit_factor:.2f}  [{'ok' if m.profit_factor>=1.25 else 'fail'}]")
    print(f"  trade count >= 100   : {m.trades}  [{'ok' if m.trades>=100 else 'fail'}]")


# --------------------------------------------------------------------------- #
# calibrate (TRAIN only)
# --------------------------------------------------------------------------- #
def cmd_calibrate(args) -> int:
    from backtest.simulator import SimConfig
    from backtest.calibrate import sweep

    params = Params.load()
    wl = watchlist()
    store = Store(args.db)
    v = validation_window()
    start, end = _ms(v["train_start"]), _ms(v["train_end"])   # TRAIN window is sacred
    markets = [args.market] if args.market else ["crypto", "forex"]

    datasets = []
    for market in markets:
        curve_tf = _curve_tf(market)
        for symbol in wl[market]["symbols"]:
            curve = store.load_candles(symbol, curve_tf, start, end)
            for tf in wl[market]["timeframes"]:
                candles = store.load_candles(symbol, tf, start, end)
                if len(candles) < params.atr_period + 5:
                    continue
                cfg = SimConfig(market, symbol, tf, tf_is_curve=(tf == curve_tf))
                datasets.append((candles, cfg, curve if tf != curve_tf else None))
    store.close()

    results = sweep(datasets, params, min_trades=args.min_trades)
    print(f"Top parameter sets (TRAIN {v['train_start']}..{v['train_end']}):\n")
    for r in results[:10]:
        m = r.metrics
        print(f"  exp {m.expectancy_r:+.3f}R  PF {m.profit_factor:.2f}  "
              f"n={m.trades}  {json.dumps(r.params)}")
    return 0


# --------------------------------------------------------------------------- #
# scan (live)
# --------------------------------------------------------------------------- #
def cmd_scan(args) -> int:
    from live.scanner import SymbolScanner, scan_loop
    from data import ccxt_fetch

    params = Params.load()
    wl = watchlist()
    market = args.market or "crypto"
    scanners = []
    for symbol in wl[market]["symbols"]:
        for tf in wl[market]["timeframes"]:
            if tf == _curve_tf(market):
                continue  # scan entry TFs only
            scanners.append(SymbolScanner(symbol, tf, market, params))

    # Wire the live data source to the scan loop. ccxt fetch of recent closed
    # candles per (symbol, tf); returns Candle objects for on_new_candles().
    def fetch(symbol, tf):
        from data import ccxt_fetch
        from engine.candles import Candle
        since = _now_ms() - 1500 * ccxt_fetch._TF_MS[tf]
        rows = ccxt_fetch.fetch_ohlcv(symbol, tf, since)
        return [Candle(r[0], r[1], r[2], r[3], r[4], r[5] if len(r) > 5 else 0.0)
                for r in rows]

    print(f"Scanning {len(scanners)} (symbol,tf) streams for {market}. "
          f"Alert min score={params.alert_min_score}. Ctrl-C to stop.")
    try:
        asyncio.run(scan_loop(scanners, poll_seconds=args.poll,
                              fetch=fetch, send=not args.dry_run))
    except KeyboardInterrupt:
        print("stopped.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sdz", description="SDZ-Sentinel CLI")
    p.add_argument("--db", default="data/sdz.db", help="SQLite path")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch & store OHLCV")
    f.add_argument("--market", choices=["crypto", "forex"])
    f.add_argument("--since", default="2019-01-01")
    f.add_argument("--until", default=None)
    f.set_defaults(func=cmd_fetch)

    b = sub.add_parser("backtest", help="run backtest & write report")
    b.add_argument("--market", choices=["crypto", "forex"])
    b.add_argument("--start", default=None)
    b.add_argument("--end", default=None)
    b.add_argument("--out", default="runs/latest")
    b.add_argument("--gate", action="store_true", help="print P4 GO/NO-GO verdict")
    b.set_defaults(func=cmd_backtest)

    c = sub.add_parser("calibrate", help="TRAIN-window parameter sweep")
    c.add_argument("--market", choices=["crypto", "forex"])
    c.add_argument("--min-trades", type=int, default=200, dest="min_trades")
    c.set_defaults(func=cmd_calibrate)

    s = sub.add_parser("scan", help="live scanner + Telegram alerts")
    s.add_argument("--market", choices=["crypto", "forex"])
    s.add_argument("--poll", type=int, default=60)
    s.add_argument("--dry-run", action="store_true", help="print alerts, don't send")
    s.set_defaults(func=cmd_scan)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
