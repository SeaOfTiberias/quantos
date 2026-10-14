---
title: EMA-8 Slope, Second Trade of the Day
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: ema8-second-trade
candidate: "—"
family: intraday-options
instrument: index-futures
status: closed
verdict: FAIL
first_tested: 2026-10-01
verdict_date: 2026-10-01
profit_factor:
sharpe:
trades: 1313
bar: "Trade 2 beats trade 1 on BankNifty (one-sided p ≤ 0.05) AND trade 2 alone clears costs as futures"
headline: "The NIFTY pattern from a TradingView run (second trade of the day beats the first) held statistically on BankNifty but lost ₹487/trade after futures costs."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-ema-8-slope-second-trade-of-the-day-vs-the-first
---

# EMA-8 Slope, Second Trade of the Day

> [!abstract] Compiled page
> Written from `[[2026-10-13-ema-8-slope-second-trade-of-the-day-vs-the-first]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

A check of whether a pattern the user saw in a TradingView EMA-8-slope strategy on NIFTY carries over to BankNifty. On NIFTY, the second trade of the day did better than the first. Rules: index points in the trade's direction, a 1.5 × ATR(14) trail, at most 2 trades a day, and the 20-EMA filter on, matching the user's TradingView run `[[2026-10-13-ema-8-slope-second-trade-of-the-day-vs-the-first]]`.

## Mechanics

**Step 0, parity with TradingView (NIFTY).** The Python replica matched 84.9% of TradingView's 2,139 trades by entry time and direction (gate 80%). It reproduced trade 1 at −1.05 pts (TradingView −1.52) and trade 2 at +2.84 pts (t 2.37; TradingView +3.06).

**The test (BankNifty)**: trade 1, n=1321, −6.87 pts (t −2.48); trade 2, n=1313, −0.32 pts (t −0.11).

`[[2026-10-13-ema-8-slope-second-trade-of-the-day-vs-the-first]]`

## Verdict

**CLOSED (FAIL).** The statistical half holds: trade 2 minus trade 1 = +6.55 pts, one-sided p = 0.050. The economic half does not: trade 2 alone, as futures, nets **−₹487 a trade (t −5.67)**. Trade 2 is only "better" because trade 1 loses more `[[2026-10-13-ema-8-slope-second-trade-of-the-day-vs-the-first]]`.

## Relation to other concepts

Tested the same day and on the same futures-cost basis as [[trend-day-filter-candidate-21]]. Like it, and like [[orb-options-scalping-candidate-18]]'s exit study, it shows an intraday index pattern that can pass a significance test and still fail against costs.
