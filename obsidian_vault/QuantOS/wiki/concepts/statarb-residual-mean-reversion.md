---
title: StatArb Residual Mean Reversion ("Straying Duckling")
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: statarb-residual-mean-reversion
candidate: "22"
family: stat-arb
instrument: stock-futures
status: closed
verdict: FAIL
first_tested: 2026-10-13
verdict_date: 2026-10-13
profit_factor: 0.86
sharpe: -0.76
trades: 2245
bar: "PF > 1 and Sharpe > 0.5; PF > 1 in both halves and in exits from 2024 and 2025; calibration t > 2. Numbers are the Nifty 50 PCA5 run (BankNifty M1: PF 0.92, Sharpe −0.24)"
headline: "Avellaneda–Lee residual s-scores did not predict reversion on BankNifty or Nifty 50 stock futures; gross edge about zero against costs; residual/pairs mean reversion on NSE futures retired."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-statistical-arbitrage-via-eigen-factor-residual-mean-reversi, 2026-10-13-banknifty-straying-duckling-residual-mean-reversion-methodol, 2026-10-13-banknifty-residual-mean-reversion-results, 2026-10-13-nifty-50-eigen-factor-residual-mean-reversion-methodology-pr, 2026-10-13-nifty-50-residual-mean-reversion-results
---

# StatArb Residual Mean Reversion ("Straying Duckling")

> [!abstract] Compiled page
> Written from `[[2026-10-13-statistical-arbitrage-via-eigen-factor-residual-mean-reversi]]`, `[[2026-10-13-banknifty-straying-duckling-residual-mean-reversion-methodol]]`, `[[2026-10-13-banknifty-residual-mean-reversion-results]]`, `[[2026-10-13-nifty-50-eigen-factor-residual-mean-reversion-methodology-pr]]` and `[[2026-10-13-nifty-50-residual-mean-reversion-results]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

The user's spec, based on a video of Avellaneda & Lee's statistical-arbitrage research, frames it as ducklings straying from the mother duck. Stocks in a sector move together on shared factors. When one strays beyond its usual volatility allowance without news, buy the straggler (or short the runaway) and hedge the family, expecting the gap to close `[[2026-10-13-statistical-arbitrage-via-eigen-factor-residual-mean-reversi]]`. Two pre-registered tests: BankNifty as a narrow test bed, then Nifty 50 as the fair test of the multi-factor, multi-sector design the spec describes.

## Mechanics

- **Residual**: each stock's last 60 daily returns regressed on a leave-one-out family factor. BankNifty: M1, the equal-weighted peers (primary), and M2, 2 PCA factors. Nifty 50: PCA5, 5 eigenportfolios from a 252-day correlation matrix (primary), and MKT_SECTOR, market plus own-sector peers.
- **s-score**: AR(1)/Ornstein–Uhlenbeck fit of the cumulative residual, s = (X − m)/σ_eq. Speed filter: mean-reversion time < 30 trading days.
- **Rules**: open at |s| ≥ 1.25, close long at s ≥ −0.50 and short at s ≤ +0.75 (the paper's exits), stop at |s| ≥ 3 (from the spec), max hold 20 days, fills at the next close, results blackout ±5 trading days.
- **Instruments and costs**: near-month stock futures (no overnight cash shorts in India), ₹5L per stock leg, a two-instrument futures cost model, plus 2 bps a side.
- **Deviations from the spec, disclosed**: 1–5 factors instead of 15 (you cannot extract 15 from 14 stocks); a leave-one-out family, because HDFCBANK and ICICIBANK are about half of BankNifty.

`[[2026-10-13-banknifty-straying-duckling-residual-mean-reversion-methodol]]` `[[2026-10-13-nifty-50-eigen-factor-residual-mean-reversion-methodology-pr]]`

## Verdict

**FAIL, both universes, both models** (evaluation 2020-02-25 to 2026-10-12):

| Run | Trades | PF | Sharpe | Gross P&L | Costs | Calibration t |
|---|---|---|---|---|---|---|
| BankNifty M1 (primary) | 558 | 0.92 | −0.24 | +₹1.8L | ₹5.5L | −0.40 |
| BankNifty M2 | 561 | 0.89 | −0.30 | +₹1.0L | ₹5.9L | −0.41 |
| **Nifty 50 PCA5 (primary)** | 2245 | 0.86 | −0.76 | +₹2.0L | ₹29.5L | −1.23 |
| Nifty 50 MKT_SECTOR | 1716 | 0.94 | −0.32 | +₹10.0L | ₹18.4L | −0.12 |

`[[2026-10-13-banknifty-residual-mean-reversion-results]]` `[[2026-10-13-nifty-50-residual-mean-reversion-results]]`

- **No calibration**: stocks flagged as lagging did not catch up over the next 10 days. In Nifty 50 PCA5 the extreme buckets *continued* (s ≥ 2: +0.90% further; s ≤ −2: −0.52%). That leans toward residual momentum, but it is not significant and was noticed after the fact.
- **Typical failure**: trades that reverted made +₹68L (Nifty 50 PCA5). Those hitting the 20-day limit lost −₹65L and those closed before results −₹22L. Strays were mostly lasting re-ratings, not noise.
- **Breadth**: Nifty 50 averaged 12.5 open positions (max 24), not the 30–50 the spec relies on.
- **Speed filter**: the paper's filter is weak at 60 observations. About 65% of simulated random walks pass it.
- **Only some years were profitable**: BankNifty M1 2020 and 2022–23; Nifty 50 PCA5 2020 and 2025.

## Relation to other concepts

- The stock-versus-family counterpart to stock-versus-stock [[pairs-trading-candidate-12]] and [[pairs-trading-v2-candidate-17]]. Both pairs runs lost in each of their last three folds (2025-10 to 2026-07), and BankNifty M1 lost every year from 2024. Together, the four runs retire mean reversion on NSE stock futures in this project.
- Uses the roll-adjusted futures series and cost model built for [[pairs-trading-v2-candidate-17]].
