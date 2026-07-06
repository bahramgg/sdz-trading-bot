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

## Engine fix — freshness enhancer made live (wick-test / body-fill model)

**Problem (was):** every backtested trade scored freshness = 2. With a limit at
the body proximal and "test" defined on the entry band, the first candle to
reach the band both tests *and* fills, so `prior_tests` was always 0.

**Fix:** the zone now carries a wick-based `test_edge` (base high for demand,
base low for supply) that is the outer edge of a **test band** `[distal,
test_edge]`, distinct from the deeper body `proximal` fill line. A candle that
taps the test band without reaching proximal is a *test, not a fill*, so it ages
freshness. Covered by `tests/test_freshness.py` (first touch → 2; wick-tap then
retest fill → 1).

**Empirical result — freshness still barely varies, and does not move P4:**

| freshness | TRAIN trades | TRAIN exp R |
|---|---|---|
| 2 (fresh) | 256 | +0.408 |
| 1 (retest) | 8 | +0.873 (n=8, noise) |

Only ~3% of fills are retests: the method structurally trades fresh zones, so
even a correct freshness enhancer has little discriminating power here. OOS
re-check with the fix (⚠️ OOS already used — not a clean gate): **152 trades,
+0.171R, PF 1.22 — still NO-GO.** The fix also made the "active while fresh or
tested(1)" rule fire on wick taps, trimming 258→152 trades while holding
per-trade expectancy (~+0.17R) — more selective, same edge.

**Takeaway:** the binding constraint is **profit factor (~1.22), not freshness.**
Lifting it needs exit/target work or a regime filter, not scoring tweaks —
validated on a fresh window, since OOS is now spent.

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
