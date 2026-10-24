---
title: Surge Bull Put Credit Spread (IV Rank Gate)
compiled: 2026-10-25
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: surge-bull-put-credit
candidate: "New tracks A (spec 2.2b)"
family: momentum
instrument: stock-options
status: closed
verdict: FAIL
first_tested: 2026-10-24
verdict_date: 2026-10-25
profit_factor: 1.01
sharpe: 0.01
trades: 128
bar: "Stage 1: PF > 1.2, Sharpe > 0.8, win > 50%, PF > 1 in each half, week-bootstrap 2.5% > 0, n >= 100 (Stressed costs); Stage 2: quarter-Kelly NAV, max DD < 20%, zero lot-lockouts"
headline: "Selling ~35-delta put spreads on non-52-week-high surges with IV rank >= 0.70 broke even after costs: 77% of trades won, but stops cost more than the wins made, and the first half lost."
next_gate: "None this round. A failed test is not re-tuned."
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd
---

# Surge Bull Put Credit Spread (IV Rank Gate)

> [!abstract] Compiled page
> Written from `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]` on 2026-10-25. Context and retrieval only — rules in this layer never execute.

## Definition

A defined-risk bullish options trade on the surge days that [[surge-spread-candidate-23]] found keep going: +5% F&O stock surges that are not fresh 52-week highs. It sells a put spread when option prices are rich (IV rank ≥ 0.70) instead of buying a call spread `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]`.

## Mechanics

- **Events**: candidate 23's 2,571 non-52-week-high surges, 2020-03-02 to 2026-09-24.
- **IV rank**: the stock's daily ATM IV (Black-76 on bhavcopy closes, nearest expiry with ≥ 5 trading days) against its prior 252 sessions; gate ≥ 0.70.
- **Structure**: in the nearest expiry with ≥ 10 trading days, sell the put nearest 0.35 delta (band 0.30–0.40) and buy the put nearest 0.125 delta (band 0.10–0.15) below it, at the surge-day close.
- **Exits** on daily closes: take profit when the spread is worth ≤ 50% of the credit; stop at a loss of 1.5 × credit; otherwise out on the last trading day before expiry.
- **Costs**: candidate 23's statutory table plus bid-ask max(2% × price, ₹0.05) per leg per side (Stressed, gating) `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]`.

## Result

| | Stressed (gating) | Base 1% (reference) |
|---|---|---|
| Trades | 128 | 128 |
| Profit factor | 1.01 | 1.08 |
| Sharpe | 0.01 | 0.11 |
| Won | 77% | 77% |
| Mean return on max loss | +0.10% | +1.03% |
| PF by half (2020–23 / 2023–26) | 0.58 / 1.28 | 0.63 / 1.37 |
| Week-bootstrap 2.5% bound | −7.84% | −6.71% |

- Only 232 of 2,571 events cleared the IV-rank gate; 104 more had no strikes in the delta bands. Exits: 96 take profit, 24 stop, 8 time.
- **Stage 2** took no trades: the trailing Kelly fraction was ≤ 0 on 64 signals, and under one lot on 33 more (lot-lockouts at every tier) `[[2026-10-24-new-tracks-surge-bull-put-credit-spreads-and-eur-usdgbp-usd]]`.
- Fails 4 of 6 Stage 1 checks. A high win rate with a stop at 1.5 × credit nets out to roughly zero.

## Relation to other concepts

- Uses the direction that [[surge-spread-candidate-23]] found (surges continue), with a credit structure in place of that candidate's bull call spreads. Both lost to costs.
- [[surge-spread-forward-23b]] remains the only live test of surge follow-through (forward paper).
