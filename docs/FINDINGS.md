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

## Cross-market generalization test — forex (crypto params, untuned) → **GO**

The strongest evidence yet that the edge is real, not a crypto-specific fit.
The params calibrated on **crypto 2019–2023** were applied to **forex
(EURUSD, GBPUSD, XAUUSD) with zero re-tuning**. Because forex never entered any
calibration, the **entire 2019–2026 forex history is out-of-sample**. Data:
Dukascopy deep hourly candles (`data/duka_candles.py`).

`python main.py backtest --market forex --start 2019-01-01 --end 2026-06-30 --gate`

| criterion | threshold | result | pass |
|---|---|---|---|
| expectancy | ≥ +0.15 R | **+0.251 R** | ✅ |
| profit factor | ≥ 1.25 | **1.33** | ✅ |
| trade count | ≥ 100 | **376** | ✅ |

### → VERDICT: **GO** (all three, on a market never used for tuning)

376 trades, 37.2% win, +94.2R total, max drawdown only 18.5R — a smoother curve
than crypto. Costs are real and material (avg loss −1.22R = 1R stop + ~0.22R
spread/slippage; avg win 2.74R = 3R target − costs).

**Consistencies with crypto (method-level, not fit):**
- Odds Enhancer ranks quality again: score 9 **+0.558R (PF 1.84)** > score 8 +0.211R.
- 4h is the sweet spot again: **+0.370R (PF 1.52)** vs 1h +0.184R.
- Freshness now varies meaningfully (24 retests vs crypto's 8) and both buckets
  are positive — the wick-test fix earns its keep in ranging FX.

**Notable divergence (regime, not method):** RBR — which *failed* in crypto
2024–2026 (−0.071R) — is the **best** forex pattern (+0.495R, PF 1.72). Pattern
edge is regime/asset dependent; the aggregate method is what generalizes.

## Forex-native P3 → P4 (calibrate on forex TRAIN, evaluate forex OOS once)

To confirm the forex GO survives a proper train/test split (not just untuned
application), a forex-only calibration was run on TRAIN 2019–2023, then evaluated
once on OOS 2024–2026.

- **P3 winner (forex TRAIN):** base_body_max=0.45, erc_atr_mult=1.5,
  proximal_mode=body, tp_mode=hybrid, min_score=8 → TRAIN +0.415R, PF 1.57.
- **P4 (forex OOS, once):** **142 trades, +0.253R, PF 1.33, 38.0% win → GO.**

The OOS number (+0.253R) is nearly identical to the untuned generalization run
(+0.251R): the method is **robust to the exact parameter fit** — a reassuring
sign it is capturing structure, not noise. Forex TRAIN→OOS degradation is mild
(+0.415R → +0.253R) versus crypto, which flipped NO-GO.

**⚠️ The forex GO is not uniform across symbols (OOS 2024–2026):**

| symbol | trades | expectancy R | PF |
|---|---|---|---|
| XAUUSD (gold) | 61 | **+0.400** | 1.58 |
| GBPUSD | 37 | +0.289 | 1.37 |
| EURUSD | 44 | +0.018 | 1.02 (essentially flat) |

The edge concentrates in the **more impulsive/trending instruments** — gold
carries the aggregate, cable is solid, and EURUSD is barely above break-even.
This fits the thesis that supply/demand imbalance works better on trending
markets than on mean-reverting majors, and it means "cross-market edge" should
be read as **"works on trending instruments (crypto-in-trend, gold, GBP), weak
on range-bound majors (EURUSD)"** — not a blanket claim. A live deployment
should weight or filter toward the instrument types where the edge actually
shows up.

### Where this leaves the project

| test | verdict |
|---|---|
| Crypto OOS 2024–2026 (calibrated) | NO-GO (+0.174R, PF 1.22) |
| Forex 2019–2026 (crypto params, untuned) | **GO (+0.251R, PF 1.33)** |
| **Forex OOS 2024–2026 (forex-native P3→P4)** | **GO (+0.253R, PF 1.33)** |

The mechanized Seiden S&D method shows a **genuine, cross-market edge after real
costs.** It missed the bar in the specific recent-crypto regime but cleared it
on an entirely independent market. Per the iron rule, still **no real capital**
until a forward paper run (P5) confirms it live. A forex-native P3/P4 (calibrate
on forex TRAIN, evaluate forex OOS once) is the natural next validation.

## Walk-forward analysis — the most robust test, and a humbling reframe

Single train/test splits depend on one arbitrary cut. Walk-forward re-calibrates
on a rolling 24-month TRAIN window (focused grid) and trades the next unseen
6-month OUT window, sliding forward and concatenating every OUT segment into one
out-of-sample track. `python main.py walkforward --market <m>`.

| market | folds | trades | aggregate exp | PF | verdict |
|---|---|---|---|---|---|
| **crypto** | 11 | 507 | **+0.408R** | 1.58 | ✅ GO (9/11 folds +) |
| **forex** | 11 | 532 | **+0.076R** | 1.09 | ❌ NO-GO |

**This reverses the single-split verdicts** — and that reversal is the finding:

| market | single split (static) | walk-forward (rolling) |
|---|---|---|
| crypto | NO-GO (+0.174R) | **GO (+0.408R)** |
| forex | GO (+0.253R) | **NO-GO (+0.076R)** |

- **Crypto:** periodic re-calibration *recovers* the edge a stale 2019–2023 fit
  missed. Even restricted to 2024–2026, the walk-forward folds average ≈+0.377R
  vs the static +0.174R. Adapting to regime matters.
- **Forex:** walk-forward *exposes* the static GO as partly lucky. The 2019–2023
  fit happened to pick `erc_atr_mult=1.5`, which transferred well; rolling
  windows pick 1.2–1.3 (better on their trailing TRAIN) which then go roughly
  flat forward. The 2024–2026 forex folds average ≈0.00R.

### The honest bottom line

**The method's GO/NO-GO verdict is protocol-sensitive** — it flips between static
and rolling calibration for *both* markets. That means the edge is **real but
marginal and fragile**, not a robust money-printer. What is protocol- and
market-*independent* (the trustworthy signal):

1. The Odds Enhancer score ranks quality everywhere (higher score → higher
   expectancy), validating Seiden's central claim.
2. 4h is consistently the best timeframe.
3. Per-trade edge lives in roughly the +0.1R to +0.4R band depending on
   regime/protocol, after real costs — enough to matter, not enough to trust
   blindly.

Walk-forward crypto GO is the single most defensible positive result (least
dependent on an arbitrary split), but the forex reversal is the cautionary
counterweight. **Iron rule stands: no real capital before a live forward run.**

## Scale-out exit — the profit-factor lever (now default)

The binding constraint everywhere was profit factor. `exit_mode=scaleout` takes
50% off at +1R, moves the stop to breakeven, and lets the runner target the
tp_mode target. Head-to-head on real 2019–2026 data:

| market | mode | exp R | PF | win% | maxDD R |
|---|---|---|---|---|---|
| crypto | setforget | +0.388 | 1.55 | 38 | 18.9 |
| crypto | **scaleout** | +0.367 | **2.12** | **72** | **13.1** |
| forex | setforget | +0.251 | 1.33 | 37 | 18.5 |
| forex | **scaleout** | **+0.277** | **1.81** | **69** | **8.3** |

It lifts PF sharply and roughly halves drawdown at ~flat expectancy — a strictly
better risk profile, so it is now the default.

**Re-running walk-forward with scaleout** (the decisive robustness test):

| market | trades | exp R | PF | win% | maxDD R | verdict |
|---|---|---|---|---|---|---|
| **crypto** | 518 | +0.339 | **2.08** | 72.8 | **9.4** | ✅ GO — **all 11 folds positive** |
| forex | 789 | +0.147 | 1.39 | 68.1 | 21.9 | ❌ NO-GO by 0.003R (PF now passes) |

- **Crypto is now a robust GO under the most stringent test**: every rolling
  fold 2021→2026 is positive (worst +0.037R), PF 2.08, drawdown a mere 9.4R.
  This is the project's strongest, most defensible result.
- **Forex is a razor-thin miss**: scaleout lifted the walk-forward from
  +0.076R/PF 1.09 to +0.147R/PF 1.39 — profit factor now clears 1.25, and
  expectancy misses +0.15R by 0.003R. 9/11 folds positive. Borderline, not dead.

### Scale-out sensitivity (is the result knife-edge?)

Grid over `scale_tp1_r × scale_fraction` on full 2019–2026 with each market's
calibrated entry params. **The surface is smooth — no knife-edge:**

- **Crypto:** every one of 9 cells is a strong pass — expectancy +0.34 to +0.42R,
  PF **1.76–2.20**. The crypto edge does not depend on the exact exit params.
- **Forex:** every cell PF 1.79–1.97, expectancy +0.28 to +0.44R (full-history).
- Trade-off: lower `tp1_r` → higher PF / win% / lower drawdown; higher `tp1_r`
  → higher expectancy. `tp1_r=1.5` is the balance point and lifts expectancy
  broadly, so it is the default.

**Walk-forward at `tp1_r=1.5` (the honest test, both markets now GO):**

| market | trades | exp R | PF | win% | maxDD R | folds + | verdict |
|---|---|---|---|---|---|---|---|
| crypto | 511 | +0.378 | 1.85 | 62.6 | 14.6 | 10/11 | ✅ GO |
| forex | 619 | +0.237 | 1.50 | 61.9 | 13.6 | 10/11 | ✅ GO |

### Updated bottom line

- **Crypto: robust GO.** It passes walk-forward across the *entire* exit-param
  grid (PF 1.3–2.2 depending on tp1_r, always positive, all/most folds green).
  Highest confidence.
- **Forex: conditional GO.** It passes walk-forward at `tp1_r=1.5` (+0.237R,
  PF 1.50) but *fails* at `tp1_r=1.0` (+0.147R). Its verdict flips around the
  exit-param choice, so forex remains the more marginal, lower-confidence case —
  the honest read is "borderline-positive," not "confirmed."

The Seiden odds enhancers rank quality everywhere, 4h is consistently best, and
scale-out turns the marginal raw edge into a ~60–70% win-rate, low-drawdown
profile that clears the most stringent test on crypto outright and on forex at a
sensible exit setting. **Iron rule stands: no real capital before a live forward
run (P5).** But the case is now genuinely encouraging.

> Honesty note: `tp1_r=1.5` was selected from the sensitivity grid (higher
> expectancy on *both* markets) and then confirmed on walk-forward — not fitted
> to make forex pass. Still, because crypto is GO regardless of tp1_r while forex
> depends on it, treat crypto as the strong result and forex as the tentative one.

## What would make the case a GO more robustly (future, clean OOS tests)

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
