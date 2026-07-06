# SDZ-Sentinel

Sam Seiden Supply & Demand, mechanized: a deterministic zone engine + honest
backtester + live scanner with Telegram alerts, for **crypto and forex**.

> **Prime directive:** measure real expectancy from data *before* trusting the
> method. Backtest first, alerts second, real money only after the P4 gate passes.

This repo is the codification of a **discretionary** method into a zero-ambiguity
rule set. See [Honest Caveats](#honest-caveats) — any result measures *this rule
set*, not Seiden himself.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                                   # engine + backtester unit tests

# 1. fetch history into SQLite (data/sdz.db)
python main.py fetch --market crypto --since 2019-01-01

# 2. backtest a window and write a bucketed report
python main.py backtest --market crypto --start 2024-01-01 --end 2026-06-30 --gate

# 3. calibrate on the TRAIN window only (never touches OOS)
python main.py calibrate --market crypto

# 4. live scan (needs .env with Telegram creds)
python main.py scan --market crypto --dry-run
```

All tunable constants live in `config/params.yaml`; symbols in
`config/watchlist.yaml`; costs in `config/costs.yaml`.

---

## Architecture

```
config/     params.yaml, watchlist.yaml, costs.yaml   — every magic number
config.py   typed loader; Params is immutable & override()-able for sweeps
data/       ccxt_fetch, yf_fetch, duka_fetch, store (SQLite)
engine/     candles → patterns → zones → score → lifecycle   (pure, deterministic)
backtest/   simulator, costs, metrics, report, calibrate
live/       scanner (Sentinel loop), telegram, tracker (forward paper trades)
tests/      patterns, zones, no_lookahead, backtest, store, live + synthetic fixtures
main.py     CLI: fetch | backtest | calibrate | scan
```

The `engine/` layer is a pure function of **closed candles only**. Classification
of candle *i* reads nothing past *i*; a zone is born at its leg-out close; a trade
decision at fill index reads no future candle. The lookahead audit
(`tests/test_no_lookahead.py`) enforces this by shifting data one bar and
asserting zero change, and by truncating data after the fill and asserting the
trade is identical.

## The mechanical rules (implemented)

| § | Rule | Where |
|---|---|---|
| 2.1 | ERC / basing classification, Wilder ATR(14) | `engine/candles.py` |
| 2.2 | Base + DBR/RBR/RBD/DBD detection, leg-out-must-leave | `engine/patterns.py` |
| 2.3 | Body/wick proximal, distal, oversized-zone discard | `engine/patterns.py` |
| 2.4 | fresh → tested(n) → broken / consumed / expired | `engine/lifecycle.py` |
| 2.5 | Odds Enhancer 0–10 (freshness, departure, base time, margin, HTF) | `engine/score.py` |
| 2.6 | Entry@proximal, stop beyond distal, TP modes, intrabar ambiguity → LOSS | `engine/lifecycle.py`, `backtest/simulator.py` |
| 3 | Costs, bucketed metrics, deterministic reruns, lookahead audit | `backtest/` |
| 4 | Candle-close scanner, 3 alert triggers, Level-1 format, paper tracker | `live/` |

## Build phases & gates (master plan §6)

| Phase | Deliverable | Gate | Status |
|---|---|---|---|
| P0 | Repo + fetchers + SQLite store | 2y OHLCV stored & idempotent | ✅ real Binance/OKX data 2019–2026 |
| P1 | Zone engine + unit tests | ≥90% vs hand-labeled zones; lookahead green | engine + tests ✅ |
| P2 | Backtester + cost model | deterministic; ambiguity rule verified; report | ✅ |
| P3 | Calibration sweep on TRAIN | grid; expectancy-ranked | ✅ crypto (TRAIN +0.396R) |
| P4 | **OOS GO/NO-GO** | exp ≥ +0.15R **and** PF ≥ 1.25 **and** ≥100 trades | crypto ❌ NO-GO · **forex ✅ GO** |
| P5 | Live scanner + 30d forward paper | forward within ±0.15R; uptime ≥99% | ✅ functional (live OKX/Duka fetch, HTF, warmup, paper tracker); 30d run pending |

**Iron rule:** no real capital before P4 = GO **and** P5's 30-day forward run confirms it.

**Verdicts** (full story + caveats in [`docs/FINDINGS.md`](docs/FINDINGS.md)).
Walk-forward = rolling re-calibration, the most stringent test. Scale-out exit
(default) takes 50% at +1R, stop to breakeven, runner to target.

| test | crypto | forex |
|---|---|---|
| Single split (static, set-and-forget) | ❌ NO-GO (+0.174R, PF 1.22) | ✅ GO (+0.253R, PF 1.33) |
| Walk-forward, set-and-forget | ✅ GO (+0.408R, PF 1.58) | ❌ NO-GO (+0.076R, PF 1.09) |
| **Walk-forward, scale-out** | ✅ **GO (+0.339R, PF 2.08, all 11 folds +)** | ❌ NO-GO by 0.003R (+0.147R, PF 1.39) |

**Crypto is a robust GO under the most stringent test** (every rolling fold
2021→2026 positive, PF 2.08, drawdown just 9.4R). **Forex sits right on the
threshold** — scale-out lifted its walk-forward from clearly NO-GO to a razor-thin
expectancy miss with PF now passing. Protocol-independent truths: the Odds
Enhancer score ranks quality everywhere (validating Seiden's core claim), 4h is
consistently best, and scale-out converts the marginal raw edge into a
~70%-win-rate, low-drawdown profile. Reproduce: `python main.py walkforward --market crypto`.

## Honest Caveats

1. What we test is **our codification** of Seiden's method. His is discretionary;
   any result (good or bad) measures this rule set, not the man.
2. Limit-fill simulation without tick data is optimistic; the conservative
   intrabar ambiguity rule (same-candle SL+TP counts as a LOSS) partially offsets
   this. **Treat backtest expectancy as an upper bound.**
3. Regime risk: crypto 2019–2023 ≠ 2026. That's exactly why the OOS gate and
   forward tracking exist.
4. A NO-GO is a valid, valuable result — publishable either way ("we mechanized
   Seiden S&D and here's what the data says").

## Deploy

VPS + systemd — see `deploy/sdz-sentinel.service`. Copy `.env.example` to `.env`
and set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.
