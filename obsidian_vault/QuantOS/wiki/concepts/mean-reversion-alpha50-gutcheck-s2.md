---
title: Mean-Reversion on Nifty Alpha 50 (Strategy 2, Gut-Check)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/weak
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-mean-reversion-nifty-alpha-50-gut-check
---

# Mean-Reversion on Nifty Alpha 50 (Strategy 2, Gut-Check)

> [!abstract] Compiled page
> Written from `[[2026-09-17-mean-reversion-nifty-alpha-50-gut-check]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The second of three fully-specified strategy proposals brought in the same session as [[regime-filtered-dual-momentum-s1]]. A descriptive gut-check only — no costs, no position sizing, no threshold tuning — of whether an RSI/sector-trend-based mean-reversion signal on Nifty Alpha 50 constituents shows a real forward-return edge over baseline, before committing to a full backtest.

## Mechanics

38,520 observed days (1,159 signal days, 37,361 baseline days). A real, disclosed limitation of the signal's own implementation: stocks with no matching real NSE sectoral index fall back to using NIFTY 50's own trend, a deviation from the strategy as originally specified. Signal-day observations cluster heavily — 1,159 signal-days fall on only 394 distinct calendar dates (2.9 stocks/date average), meaning the effective number of independent events is much closer to 394 than to 1,159.

## Verdict

**Weak — a small, inconsistent gap that shrinks or reverses once market-adjusted.**

| Horizon | Signal mean % | Baseline mean % | Gap | Market-adjusted gap |
|---|---|---|---|---|
| 5d | +0.85 | +0.67 | +0.19 | +0.19 |
| 10d | +1.99 | +1.56 | +0.43 | +0.43 |
| 20d | +3.43 | +3.36 | **+0.06** | **+0.06** |

The 5- and 10-day gaps are small but present; the 20-day gap all but disappears (+0.06pp), and the sector-mapped-only cut (real sectoral index, not the NIFTY-50 fallback) shows a *negative* 20-day gap (-0.18pp) once market-adjusted — the opposite of the fallback-only subset's own positive reading. Given the clustering (394 effective events, not 1,159) and this inconsistency across horizons and subsets, the gut-check did not clear the bar for a full backtest, and none was built. This is one of two of the three same-session proposals not carried forward (the third, an earnings-beat breakout, was rejected outright as PEAD's already-shelved anomaly with a new execution layer).

## Relation to other concepts

Same "cheap descriptive check first, full backtest only if it clears a bar" sequencing as [[expiry-day-effect-gutcheck-candidate-13]] and [[candle-confirm-momentum-gutcheck-candidate-19]] — none of the three reached a full pre-registered backtest.
