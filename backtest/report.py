"""Run outputs: trade CSV, report.md, equity-curve PNG (master plan §3).

matplotlib is optional — if unavailable the PNG is skipped and the rest of the
report still generates (headless/minimal environments).
"""
from __future__ import annotations

import csv
import os
from typing import Dict, Sequence

from backtest.metrics import (Metrics, by_freshness, by_market, by_pattern,
                              by_score, by_tf, compute)
from backtest.simulator import Trade


def write_trades_csv(trades: Sequence[Trade], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "tf", "market", "pattern", "score", "freshness",
                    "entry_ts", "exit_ts", "entry", "stop", "target",
                    "exit_price", "outcome", "gross_r", "cost_r", "realized_r"])
        for t in trades:
            w.writerow([t.zone.symbol, t.zone.tf, t.market, t.zone.pattern.value,
                        t.score, t.freshness, t.entry_ts, t.exit_ts,
                        f"{t.entry:.6f}", f"{t.plan.stop:.6f}", f"{t.plan.target:.6f}",
                        f"{t.exit_price:.6f}", t.outcome,
                        f"{t.gross_r:.4f}", f"{t.cost_r:.4f}", f"{t.realized_r:.4f}"])


def _table(title: str, buckets: Dict[object, Metrics]) -> str:
    lines = ["", f"### {title}", "",
             "| bucket | trades | win% | expectancy R | PF | avg win R | avg loss R | maxDD R |",
             "|---|---|---|---|---|---|---|---|"]
    for k, m in buckets.items():
        pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
        lines.append(
            f"| {k} | {m.trades} | {m.win_rate*100:.1f} | {m.expectancy_r:+.3f} | "
            f"{pf} | {m.avg_win_r:.2f} | {m.avg_loss_r:.2f} | {m.max_drawdown_r:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report_md(trades: Sequence[Trade], path: str, title: str = "SDZ Backtest",
                    notes: str = "") -> Metrics:
    overall = compute(trades)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# {title}\n\n")
        if notes:
            fh.write(notes + "\n\n")
        pf = "inf" if overall.profit_factor == float("inf") else f"{overall.profit_factor:.2f}"
        fh.write("## Overall\n\n")
        fh.write(f"- trades: **{overall.trades}**\n")
        fh.write(f"- win rate: **{overall.win_rate*100:.1f}%**\n")
        fh.write(f"- expectancy: **{overall.expectancy_r:+.3f} R**\n")
        fh.write(f"- profit factor: **{pf}**\n")
        fh.write(f"- avg win: {overall.avg_win_r:.2f} R | avg loss: {overall.avg_loss_r:.2f} R\n")
        fh.write(f"- max drawdown: {overall.max_drawdown_r:.2f} R | total: {overall.total_r:+.2f} R\n\n")
        fh.write(_table("By score", by_score(trades)))
        fh.write(_table("By pattern", by_pattern(trades)))
        fh.write(_table("By timeframe", by_tf(trades)))
        fh.write(_table("By market", by_market(trades)))
        fh.write(_table("By freshness", by_freshness(trades)))
    return overall


def write_equity_png(trades: Sequence[Trade], path: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    ordered = sorted(trades, key=lambda t: t.exit_ts)
    equity, cum = [], 0.0
    for t in ordered:
        cum += t.realized_r
        equity.append(cum)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range(len(equity)), equity, lw=1.2)
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_title("Equity curve (cumulative R)")
    ax.set_xlabel("trade #"); ax.set_ylabel("cumulative R")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return True
