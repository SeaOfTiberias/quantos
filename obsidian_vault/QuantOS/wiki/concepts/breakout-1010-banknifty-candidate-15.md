---
title: 10:10 Breakout on BankNifty Options (Candidate 15)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/mixed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-10-10-breakout-on-banknifty-options-methodology-pre-committe, 2026-09-17-10-10-breakout-on-banknifty-options-backtest-results-candida, 2026-09-17-candidate-15-10-10-breakout-option-intraday-data-feasibility
---

# 10:10 Breakout on BankNifty Options (Candidate 15)

> [!abstract] Compiled page
> Written from `[[2026-09-17-10-10-breakout-on-banknifty-options-methodology-pre-committe]]`, `[[2026-09-17-10-10-breakout-on-banknifty-options-backtest-results-candida]]`, and `[[2026-09-17-candidate-15-10-10-breakout-option-intraday-data-feasibility]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

An unsourced retail day-trading idea keyed to the 12th 5-minute candle of the session (opens 10:10 IST) as a breakout reference, traded on BankNifty options. A feasibility probe first confirmed Fyers serves no historical intraday data for any expired option contract, at any age down to 6 days — every premium in this backtest is therefore a Black-Scholes theoretical price from the real index level plus an India-VIX-derived IV input, not a real traded price.

## Mechanics

- **Reference candle**: the 10:10–10:15 IST candle's `(high, low)`.
- **Entry**: close above the reference high → CALL; below reference low → PUT. First occurrence only, one trade/day, executes at the next candle's open.
- **Stop/target**: stop capped at 40 index points or the reference candle's own range (whichever smaller); target fixed at 200 index points. Stop wins if both trigger the same candle.
- **Contract**: nearest calendar-month BankNifty (monthly-only since Nov-2024; this backtest uses monthly for the whole window, a disclosed simplification), ATM strike at entry.
- **Cost model**: options buy-to-open/sell-to-close, composed from the same time-varying F&O rate schedules used elsewhere in this project.

## Verdict

**Technically PASSES the mechanical bar, on synthetic pricing only** `[[2026-09-17-10-10-breakout-on-banknifty-options-backtest-results-candida]]`:

| Period | Trades | Win rate | Profit factor | Sharpe | Net P&L % |
|---|---|---|---|---|---|
| Overall | 1273 | 18.1% | **1.11** | **0.65** | +1144.0% |
| 2025 | 248 | 16.5% | 0.94 | -0.54 | -125.3% |
| 2026 | 139 | 15.8% | 0.86 | -0.03 | -3.2% |

The real-INR aggregate is a net gain of **₹68,687** across 1273 trades — an average of **₹54/trade**. Per-year results are inconsistent (2022 and 2024 strong, 2021/2025/2026 negative or flat), and the win rate (18.1%) is low even where profit factor clears 1.0, meaning the edge depends on a small number of large winners.

**The central caveat, disclosed before this result existed**: every premium is theoretical, not traded — real bid-ask spread, skew, and slippage are unmeasured. A ₹54/trade average edge is exactly the size of gap a realistic option spread can consume entirely; this is disclosed in the methodology doc as the specific risk that would need checking against real, current option-chain quotes before any live-capital step, and as of this writing that follow-up check has not been recorded in a wiki-citable source.

## Relation to other concepts

Structurally the same risk that later played out decisively on [[goodnight-scalper-candidate-20]]: a real backtested edge on frictionless/synthetic pricing that a realistic real-world spread can erase. [[orb-options-scalping-candidate-18]] is the same instrument family (BankNifty options) that survived the equivalent scrutiny where this candidate's small per-trade edge is a live open question.
