# First real backtest — findings log

> Data: **OKX** public OHLCV, BTC/ETH/SOL, fetched into `data/sdz.db`.
> Window: 2024-01-01 → 2026-06-30. Params: **defaults** (no calibration yet).
> Reproduce: `python main.py backtest --market crypto --start 2024-01-01 --end 2026-06-30 --out runs/oos --gate`

## Headline (default params, all TFs, MIN_SCORE=6)

| metric | value |
|---|---|
| trades | 935 |
| win rate | 31.8% |
| expectancy | **+0.076 R** |
| profit factor | 1.09 |
| avg win / avg loss | +2.80 R / −1.19 R |
| **P4 gate** | **NO-GO** (needs ≥+0.15R, PF ≥1.25, ≥100 trades) |

The mechanized method is **marginally positive but does not clear the GO gate**
with default parameters. Per master plan §7.4, a NO-GO is a valid result — and
the buckets show *why*, and where the edge actually lives.

## Does the Odds Enhancer score rank quality? (the §3 question)

**Yes, up to score 8** — expectancy rises monotonically with score:

| score | trades | expectancy R | PF |
|---|---|---|---|
| 6 | 504 | +0.013 | 1.02 |
| 7 | 182 | +0.141 | 1.18 |
| 8 | 226 | **+0.175** | 1.23 |
| 9 | 23 | −0.011 | 0.99 (only 23 trades — noise) |

Seiden's core claim — that the enhancers separate good setups from bad — **holds
in this data** across the meaningful buckets (6→8). Score 9 has too few samples
to read.

## Where the edge concentrates

- **By timeframe:** 4h is the standout (**+0.356 R, PF 1.51**); 1h is flat
  (+0.018); 1d loses (−0.306, but only 49 trades).
- **By pattern:** continuation patterns win in this trending regime —
  DBD **+0.220** (PF 1.28), RBR +0.143; reversal patterns lose — DBR −0.100,
  RBD −0.041.

## Exploratory filters (⚠️ NOT a validated result)

These were chosen *after* looking at the OOS buckets, so they are in-sample-
contaminated and must not be reported as a GO:

| filter | trades | expectancy R | PF |
|---|---|---|---|
| MIN_SCORE=7 (all TF) | 431 | +0.150 | 1.19 |
| MIN_SCORE=8 (all TF) | 249 | +0.157 | 1.20 |
| 4h only + score≥7 | 121 | **+0.393** | **1.57** |

The last row *would* clear the P4 gate — but choosing it by peeking at OOS is
exactly the overfitting the "OOS is sacred, evaluated once" rule forbids.

## Known limitation surfaced by the data

**Freshness enhancer is currently degenerate.** Every backtested trade scored
freshness = 2 (fresh). With a limit order resting *at the proximal* (the near
edge of the band), the first candle to reach the band fills it while the zone is
still fresh, so `prior_tests` is always 0 at fill. The freshness bucket does no
discriminating work in the backtest — a design finding to revisit (e.g. score
freshness by prior approaches that stopped short of proximal, or model partial
fills).

## Honest methodology note

We only have OKX history back to ~2023-06 (4h) / 2024-01 (1h), so the plan's
**TRAIN window (2019–2023) could not be assembled for crypto at entry TFs.**
That means:
1. No proper P3 calibration was run.
2. This backtest overlaps the sacred OOS window and has now been "looked at" with
   default params — so a future formal P4 verdict for crypto should use a
   *fresh, untouched* window (e.g. forward data from 2026-07 onward) or a deeper
   history source (Dukascopy for forex; a longer crypto archive).

The correct next step is **P3 on a real TRAIN set** (deeper history or forex via
Dukascopy), then a single P4 evaluation on data never used for tuning.
