---
title: Trend-Day Filter (Candidate 21)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: trend-day-filter-candidate-21
candidate: "21"
family: intraday-options
instrument: index-futures
status: closed
verdict: FAIL
first_tested: 2026-10-01
verdict_date: 2026-10-01
profit_factor: 0.81
sharpe:
trades: 224
bar: "Stage 1, index points: primary rule must show a net edge on 1 lot of index futures, with holdout from 2025-01-01; numbers are NIFTY primary (BankNifty PF 0.68)"
headline: "Trading only 'trend days' with a 2×ATR trail lost money after futures costs on both indices (NIFTY −₹295/trade, BankNifty −₹718/trade)."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-trend-day-filter-candidate-21-stage-1-index-points
---

# Trend-Day Filter (Candidate 21)

> [!abstract] Compiled page
> Written from `[[2026-10-13-trend-day-filter-candidate-21-stage-1-index-points]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

An intraday index trade taken only on days classified as trend days, exited with a 2×ATR trailing stop. It was tested at stage 1 in index points on 1 lot of index futures, before any option pricing, so that a gross edge must exist before premium modelling can flatter it. The full rules sit in `scripts/backtest_trend_day_filter.py`'s docstring, committed before the run. The results doc does not restate the trend-day classification itself `[[2026-10-13-trend-day-filter-candidate-21-stage-1-index-points]]`.

## Verdict

**FAIL on both indices.** Holdout = entries from 2025-01-01 `[[2026-10-13-trend-day-filter-candidate-21-stage-1-index-points]]`:

| Rule | NIFTY n, gross pts, PF (net), net ₹/trade | BankNifty n, gross pts, PF (net), net ₹/trade |
|---|---|---|
| **Primary**: trend day, 2×ATR trail | 224, +4.0, 0.81, −295 | 276, −8.1, 0.68, −718 |
| All days, 2×ATR trail | 619, +2.2, 0.72, −410 | 690, −3.2, 0.71, −572 |
| Trend day, hold to 15:20 | 224, +5.0, 0.93, −226 | 276, −3.5, 0.86, −579 |
| Trend day + VIX rising | 157, +2.0, 0.72, −422 | 184, −8.8, 0.66, −736 |
| Trend day + unfilled gap | 46, +8.4, 1.01, +8 | 76, −14.4, 0.63, −900 |

The filter improves NIFTY's gross points over trading every day (+4.0 vs +2.2), but not enough to cover costs. By year, the NIFTY primary rule was positive only in 2024 (+20.6 pts) and 2026 (+5.7).

## Relation to other concepts

Runs on the same index-points-plus-futures-cost machinery as the exit-policy study that closed [[orb-options-scalping-candidate-18]]. Same lesson: the intraday index signals tested here have a gross edge of a few points against a round-trip cost of similar size. [[ema8-second-trade]] was tested the same day on the same basis.
