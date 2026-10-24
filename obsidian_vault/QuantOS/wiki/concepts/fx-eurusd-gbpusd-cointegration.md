---
title: EUR/USD vs GBP/USD Cointegration
compiled: 2026-10-25
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: fx-eurusd-gbpusd-cointegration
candidate: "New tracks B (spec 1.1)"
family: stat-arb
instrument: mixed
status: closed
verdict: FAIL
first_tested: 2026-10-24
verdict_date: 2026-10-25
profit_factor: 0.71
sharpe: -0.20
trades: 100
bar: "Stage 1: PF > 1.2, Sharpe > 0.8, win > 50%, PF > 1 in each half, week-bootstrap 2.5% > 0, n >= 30 (Stressed 4 pips); Stage 2: quarter-Kelly NAV, max DD < 20%, zero lot-lockouts"
headline: "A rolling Johansen/ADF/half-life pair trade on EUR/USD and GBP/USD lost money over 2000–2026, even at 1-pip costs."
next_gate: "None this round. A failed test is not re-tuned."
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd
---

# EUR/USD vs GBP/USD Cointegration

> [!abstract] Compiled page
> Written from `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]` on 2026-10-25. Context and retrieval only — rules in this layer never execute.

## Definition

A mean-reversion trade on the log spread between EUR/USD and GBP/USD, taken only while a rolling window says the pair is cointegrated. These are the only non-INR pairs (with USD/JPY) that Indian residents may trade, on NSE's cross-currency futures. The spec's AUD/USD, CAD/USD and USD/CAD versions were left out because residents can't legally trade them `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]`.

## Mechanics

- **Data**: FRED daily fixes (DEXUSEU, DEXUSUK, DEXINUS) and policy rates (DFF, ECBDFR, SONIA), 2000-01-03 to 2026-10-16.
- **Each day**, over the last 252 observations: Johansen trace test rejects r = 0 at 95% (the hedge ratio b comes from the first eigenvector), ADF on the spread p < 0.05, and AR(1) half-life between 1 and 126 days. All three are needed to enter.
- **Entry**: |z| > 1.5 over a lookback of the half-life (5–126 days); b and the lookback freeze at entry.
- **Exit**: z crosses 0, or after 4 half-lives.
- **P&L**: one unit = $10,000 in EUR against b × $10,000 in GBP, carry from the rate differentials, in INR. Margin 3.5% of gross notional. Costs: 4 pips per leg per side (Stressed, gating) or 1 pip (Base) `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]`.

## Result

| | Stressed 4 pips (gating) | Base 1 pip (reference) |
|---|---|---|
| Trades | 100 | 100 |
| Profit factor | 0.71 | 0.89 |
| Sharpe | −0.20 | −0.07 |
| Won | 58% | 60% |
| Mean return on margin | −2.02% | −0.69% |
| PF by half (2000–13 / 2013–26) | 0.51 / 0.98 | 0.63 / 1.25 |

- 439 of 6,717 days passed all three tests while flat; 100 trades followed.
- **Stage 2** took no trades: the trailing Kelly fraction was ≤ 0 on all 70 post-warm-up signals `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]`.

## Relation to other concepts

- The currency analogue of [[pairs-trading-v2-candidate-17]] and [[statarb-residual-mean-reversion]]: the same "spread reverts" idea, which also failed on NSE stock futures.
