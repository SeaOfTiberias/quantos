---
title: NIFTY / BankNifty Option Skew
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
  - vol-conditioning
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-nifty-option-skew-methodology-pre-committed-2026-07-25-befor, 2026-09-17-nifty-option-skew-banknifty-addendum-pre-committed-2026-07-2, 2026-09-17-nifty-option-skew-validation, 2026-09-17-banknifty-option-skew-validation
---

# NIFTY / BankNifty Option Skew

> [!abstract] Compiled page
> Written from `[[2026-09-17-nifty-option-skew-methodology-pre-committed-2026-07-25-befor]]`, `[[2026-09-17-nifty-option-skew-banknifty-addendum-pre-committed-2026-07-2]]`, `[[2026-09-17-nifty-option-skew-validation]]`, and `[[2026-09-17-banknifty-option-skew-validation]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The third vol-conditioning attempt, and the first to use a genuinely different data source than VIX: the gap between OTM put and OTM call implied vol, computed from real per-strike NSE settlement prices. Asks whether the market pricing downside moves richer than upside moves (positive skew) predicts elevated forward volatility — the textbook "skew as fear gauge" claim.

## Mechanics

`Skew_t = IV_put(5% OTM) − IV_call(5% OTM)`, both legs' IV solved via Black-Scholes bisection from real settlement prices. Quintile-bucketed against forward 20-day realized vol, 2024-01-01 through latest cached bhavcopy (~2.5 years — shorter than the VIX-based signals' 5-year window, since per-strike settlement data is only in the new bhavcopy format). Run identically and independently for NIFTY and BankNifty, never pooled.

## Verdict

**FAIL, both underlyings** — non-monotonic in both cases, despite a real gap at the endpoints:

| | NIFTY | BankNifty |
|---|---|---|
| Q1 mean fwd RV (n) | 12.78 (118) | 14.91 (118) |
| Q5 mean fwd RV (n) | 14.82 (119) | 18.03 (119) |
| Q5−Q1 gap | +2.04 | +3.11 |
| Monotonic Q1→Q5? | **No** | **No** |

The pre-registered bar required BOTH a positive Q5-vs-Q1 gap AND a monotonically non-decreasing sequence across all 5 buckets — both underlyings show the gap but neither shows the monotonic sequence (`[[2026-09-17-nifty-option-skew-validation]]`, `[[2026-09-17-banknifty-option-skew-validation]]`), the same "smile"-shaped non-monotonic pattern the whole vol-conditioning line kept reproducing.

## Relation to other concepts

Attempt 3 of 5 in the [[strategy-search|vol-conditioning search]]; see [[regime-classifier-s8-1]] for the full line and [[atm-iv-term-structure]] for the next (and closing) attempt.
