# SDZ-Sentinel — findings log

Data source: **Binance public data** (`data-api.binance.vision`), deep history.
Symbols: BTC/ETH/SOL, timeframes 1d/4h/1h, stored in `data/sdz.db`.
Split: **TRAIN 2019-01-01 → 2023-12-31** (calibration), **OOS 2024-01-01 →
2026-06-30** (evaluated once). SOL history begins 2020-08.

---

## P3 — calibration (TRAIN only)

Grid over `base_body_max`, `erc_atr_mult`, `proximal_mode`, `tp_mode`,
`min_score`, scored with the **full pipeline incl. HTF alignment**, ranked by
expectancy with ≥150 trades/set. The top of the table was stable (body proximal,
`min_score` 7–8, expectancy ~+0.39R), i.e. not a knife-edge optimum.

**Chosen params (baked into `config/params.yaml`):**

| param | value | (default was) |
|---|---|---|
| base_body_max | 0.5 | 0.45 |
| erc_atr_mult | 1.2 | 1.3 |
| proximal_mode | body | body |
| tp_mode | fixed_3R | fixed_3R |
| min_score | 8 | 6 |

TRAIN performance at these params: **+0.396 R, PF 1.56, 507 trades.**

## P4 — OOS GO/NO-GO gate (evaluated once)

`python main.py backtest --market crypto --start 2024-01-01 --end 2026-06-30 --gate`

| criterion | threshold | result | pass |
|---|---|---|---|
| expectancy | ≥ +0.15 R | **+0.174 R** | ✅ |
| profit factor | ≥ 1.25 | **1.22** | ❌ |
| trade count | ≥ 100 | **258** | ✅ |

### → VERDICT: **NO-GO** (misses profit factor by 0.03)

Two of three criteria pass; PF falls just short. Per the iron rule, **no real
capital.** But the edge partially survived out-of-sample: expectancy stayed
positive and above the +0.15R bar, on a fully out-of-sample, single-shot test.

## Why it degraded — an honest, regime-driven story

Expectancy fell from **+0.396R (TRAIN) → +0.174R (OOS)** and PF from 1.56 → 1.22.
The drop is concentrated in **one pattern flipping sign across regimes:**

| pattern | TRAIN exp / PF | OOS exp / PF |
|---|---|---|
| DBD (drop-base-drop) | +0.326 / 1.45 | **+0.480 / 1.69** |
| RBD (rally-base-drop) | +0.578 / 1.90 | +0.283 / 1.38 |
| DBR (drop-base-rally) | +0.239 / 1.32 | +0.184 / 1.24 |
| **RBR (rally-base-rally)** | **+0.449 / 1.65** | **−0.071 / 0.92** |

RBR — a continuation-demand setup — was the second-best and largest bucket in
TRAIN, then went **negative** in OOS (102 trades, the biggest OOS bucket). This
is exactly the regime risk the plan flagged (§7.3, "crypto 2019–2023 ≠ 2026").

**Crucially, "just drop RBR" is not a valid fix:** TRAIN says RBR is excellent,
so removing it would be pure post-hoc curve-fitting on the OOS set. The three
supply/reversal-leaning patterns (DBD, RBD, DBR) all held their edge OOS.

By timeframe, 4h remained strongest OOS (+0.260R, PF 1.35).

## Standing engine finding — freshness enhancer is degenerate

Every backtested trade still scores freshness = 2. With a limit resting at the
proximal (near edge of the band), the first candle to reach the band fills while
the zone is fresh, so `prior_tests` is always 0 at fill. The freshness enhancer
does no discriminating work under this fill model — a real design limitation to
revisit (score freshness by prior approaches short of proximal, or model the
zone as "armed" only after price leaves and returns).

## What would make this a GO (hypotheses for future, clean OOS tests)

Do NOT tune these on the used-up OOS window; validate on TRAIN then a fresh
window (e.g. forward paper 2026-07+):
1. Fix the freshness enhancer so it actually gates quality.
2. Smarter targets (partial TP, opposing-zone-aware) to lift PF without cutting
   expectancy.
3. Regime filter on HTF trend strength (RBR only in strong-trend regimes).
4. Forward paper tracking (P5) — the real arbiter of whether +0.174R persists.

---

### Appendix — first exploratory look (superseded)

An earlier quick run used OKX data (2024+ only, no TRAIN available) with default
params: 935 trades, +0.076R, PF 1.09. It established that the odds-enhancer score
ranks quality (6→8 monotone) but could not produce a legitimate P3/P4 split. The
Binance-deep run above supersedes it.
