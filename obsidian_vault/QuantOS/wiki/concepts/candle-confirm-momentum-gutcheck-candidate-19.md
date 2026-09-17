---
title: Candle-Confirm Momentum (Candidate 19, Gut-Check)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/no-edge
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-candle-confirm-momentum-gut-check-methodology-candidate-19, 2026-09-17-candle-confirm-momentum-gut-check-results-candidate-19
---

# Candle-Confirm Momentum (Candidate 19, Gut-Check)

> [!abstract] Compiled page
> Written from `[[2026-09-17-candle-confirm-momentum-gut-check-methodology-candidate-19]]` and `[[2026-09-17-candle-confirm-momentum-gut-check-results-candidate-19]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A gut-check of the raw claim that NIFTY/BankNifty "usually follow the direction indicated by the first or second 1-minute candle for at least the next 10 minutes" — checked on the index itself, no options, no costs, no position sizing, before any full backtest.

## Mechanics

Direction from candle 1 (09:15–09:16 IST: green → CALL bias, red → PUT bias, doji → no signal); confirmed only if candle 2 doesn't oppose it. Entry at candle index 2's open, primary forward horizon 10 minutes, with 5/15-minute readouts for robustness. Compared against an unconditional baseline (mean forward-10-min return over ALL trading days, no signal filter) — critical, since this is the most volatile part of the session and a signal-conditioned number with no baseline could look impressive purely from ambient opening-range noise.

## Verdict

**No edge over baseline.** Both NIFTY and BankNifty, both bias directions, 2022/2021-onward `[[2026-09-17-candle-confirm-momentum-gut-check-results-candidate-19]]`:

| | Win rate (10min) | Mean return % | Baseline mean % |
|---|---|---|---|
| NIFTY CALL (n=221) | 52.0% | -0.002% | +0.004% |
| NIFTY PUT (n=270) | 51.9% | +0.002% | +0.004% |
| BankNifty CALL (n=306) | 53.3% | +0.011% | +0.007% |
| BankNifty PUT (n=336) | 49.4% | +0.010% | +0.007% |

Win rates sit close to 50% across the board and signal-conditioned mean returns are statistically indistinguishable from the unconditional baseline — the candle-agreement pattern is not adding information beyond ordinary opening-range volatility that happens in either direction regardless. This is a spot-index result; even a real spot edge could still be erased by ATM option spread/theta/slippage, but there is no spot edge here to test further.

## Relation to other concepts

Did not clear the bar to proceed to a full options backtest, the same sequencing discipline every gut-check candidate in this project follows ([[expiry-day-effect-gutcheck-candidate-13]], [[mean-reversion-alpha50-gutcheck-s2]]).
