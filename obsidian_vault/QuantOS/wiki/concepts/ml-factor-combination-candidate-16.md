---
title: ML Multi-Factor Stock Ranking (Candidate 16)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-ml-multi-factor-stock-ranking-methodology-pre-committed-2026, 2026-09-17-ml-multi-factor-stock-ranking-backtest-results-candidate-16
---

# ML Multi-Factor Stock Ranking (Candidate 16)

> [!abstract] Compiled page
> Written from `[[2026-09-17-ml-multi-factor-stock-ranking-methodology-pre-committed-2026]]` and `[[2026-09-17-ml-multi-factor-stock-ranking-backtest-results-candidate-16]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The first departure in this project's search from "one rule-based signal alone" — after 15 single-factor candidates each failed standalone, this combines four already-tested factor pipelines (52-week momentum, dual-momentum composite, mean-reversion signal, days-since-reconstitution) into one logistic-regression model ranking the Nifty 500. Held to a stricter bar than any prior candidate: it must beat not just a positive Sharpe, but Nifty 500, Nifty Alpha 50, AND [[rs-momentum-rotation-s8-3]]'s own single-factor baseline, all four required, on a genuinely held-out final-12-months test period.

## Mechanics

3-year window, first 24 months TRAIN (fitting + CV hyperparameter selection only), final 12 months TEST (touched once). Label = binary, top-quintile forward performer. One model, decided in advance: L2-regularized logistic regression, no model-shopping. Same `CostModel`/`top_n`/point-in-time-universe conventions as the momentum baseline, for a clean comparison.

## Verdict

**FAIL on the mechanical bar, and criterion 4's apparent PASS is a turnover-cost artifact, not a real edge** `[[2026-09-17-ml-multi-factor-stock-ranking-backtest-results-candidate-16]]`:

1. CAGR>0%/Sharpe>0.5: FAIL (CAGR 4.1%, Sharpe 0.29).
2. Beats Nifty 500: PASS.
3. Beats Nifty Alpha 50: PASS.
4. Beats the single-factor baseline: PASS on the net numbers (4.4% vs -2.1%) — **but this does not survive removing costs**:

| | ML (net) | Baseline (net) | ML (gross) | Baseline (gross) |
|---|---|---|---|---|
| Trades | 236 | 656 | — | — |
| Return | 4.4% | -2.1% | 8.3% | 10.6% |
| Real costs paid | ₹41,128 | ₹132,713 | — | — |

The NET gap favors ML by +6.5pts; the GROSS (zero-cost) gap favors the baseline by -2.3pts. The ML model trades less often (236 vs 656 trades) and its apparent win is entirely a reward for lower turnover under the cost model, not evidence the model's stock selection is actually better — with costs stripped out, the single-factor baseline is at least as good.

Since all four criteria are required and criterion 4 is disclosed as untrustworthy regardless of its mechanical pass, the overall verdict is **FAIL**.

## Relation to other concepts

Both this candidate and [[momentum-turnover-candidate-11]] are attempts to close [[rs-momentum-rotation-s8-3]]'s gap to Nifty Alpha 50 — this one by combining factors, that one by reducing turnover. The turnover-cost-artifact finding here is a direct instance of the same phenomenon [[momentum-turnover-candidate-11]] deliberately isolates as its own subject rather than an accidental confound.
