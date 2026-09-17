---
title: Dow Theory / Market Structure Trend Following (Candidate 14)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-dow-theory-market-structure-trend-following-nifty-methodolog, 2026-09-17-dow-theory-market-structure-trend-following-backtest-results
---

# Dow Theory / Market Structure Trend Following (Candidate 14)

> [!abstract] Compiled page
> Written from `[[2026-09-17-dow-theory-market-structure-trend-following-nifty-methodolog]]` and `[[2026-09-17-dow-theory-market-structure-trend-following-backtest-results]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

An unsourced retail intraday-trading idea (swing-structure breakout with staged profit-taking), traded on NIFTY spot as a proxy for NIFTY futures (near-1:1 tracking, judged acceptable since this strategy's payoff is linear in the underlying, unlike option-based candidates).

## Mechanics

- **Swing points**: a 5-bar Williams fractal (K=2) on 5-minute candles, confirmed with a 10-minute lag. Session-reset daily.
- **Entry**: close breaks above the most recent confirmed swing high → long; below swing low → short. Executes at the next bar's open. Multiple trades/day allowed.
- **Exit**: initial stop at the triggering swing level; at 1R favorable, scale out 50% and move the remaining stop to breakeven; the remaining 50% trails to each new higher swing low (never loosens); hard flatten 15:20 IST.
- **Sizing**: 2 lots/trade (the minimum whole-lot size that makes the 50% scale-out mechanic literal).
- **Cost model**: reused futures cost function from the pairs-trading candidate.

## Verdict

**FAIL, despite a superficially strong Sharpe** — this is the textbook case this project's own reporting convention exists to catch `[[2026-09-17-dow-theory-market-structure-trend-following-backtest-results]]`:

| Period | Trades | Win rate | Profit factor | Sharpe | Net P&L % |
|---|---|---|---|---|---|
| Overall | 3650 | 57.6% | **0.88** | **2.23** | +184.9% |
| 2022 | 571 | 55.7% | 0.79 | 1.64 | +22.4% |
| 2024 | 808 | 60.0% | **1.05** | 2.89 | +59.5% |

Profit factor stays below 1.0 in every single year except 2024 — a real net loss in real rupee terms — while the Sharpe and summed net-P&L-% figures look strong throughout, because those are computed as an uncompounded, non-capital-weighted sum of each trade's own percentage return, not a real account balance. A `has_positive_edge` read that only looked at Sharpe would have wrongly called this a pass.

## Relation to other concepts

The measurement trap this candidate exposed — a real rupee loss sitting next to a large positive summed-percentage headline — was later cited explicitly as the reason to read `net_profit_pct`/`max_drawdown_pct` with caution on [[breakout-1010-banknifty-candidate-15]]'s own results, which shares the same reporting convention.
