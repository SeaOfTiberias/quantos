---
title: NIFTY / BankNifty ATM IV Term Structure
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
  - vol-conditioning
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-nifty-banknifty-atm-iv-term-structure-methodology-pre-commit, 2026-09-17-nifty-atm-iv-term-structure-validation, 2026-09-17-banknifty-atm-iv-term-structure-validation
---

# NIFTY / BankNifty ATM IV Term Structure

> [!abstract] Compiled page
> Written from `[[2026-09-17-nifty-banknifty-atm-iv-term-structure-methodology-pre-commit]]`, `[[2026-09-17-nifty-atm-iv-term-structure-validation]]`, and `[[2026-09-17-banknifty-atm-iv-term-structure-validation]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The fourth and, per the prior review's own recommendation, intended-to-be-final vol-conditioning attempt: the shape of the volatility curve across expiries (front-month vs back-month ATM IV) rather than a single-expiry or single-number read. Backwardation (front pricier than back) is the textbook "stress" shape; contango is the "calm" shape.

## Mechanics

`Spread_t = ATM_IV_front,t − ATM_IV_back,t` (mean of call+put IV at each expiry's nearest-to-spot strike, both legs solved via Black-Scholes bisection from real settlement prices). Front/back = the two nearest listed expiries with ≥3 days to trade date. Quintile-bucketed against forward 20-day realized vol, 2024-01-01 through latest cached bhavcopy, NIFTY and BankNifty run independently.

## Verdict

**FAIL, both underlyings, non-monotonic** — the same "smile" shape as the two prior vol-conditioning attempts:

| | NIFTY | BankNifty |
|---|---|---|
| Q1 mean fwd RV (n) | 12.46 (118) | 15.13 (118) |
| Q5 mean fwd RV (n) | 14.57 (119) | 18.54 (119) |
| Q5−Q1 gap | +2.11 | +3.41 |
| Monotonic Q1→Q5? | **No** | **No** |

A real gap at the endpoints on both underlyings, but the required full monotonic Q1→Q5 sequence fails on both (`[[2026-09-17-nifty-atm-iv-term-structure-validation]]`, `[[2026-09-17-banknifty-atm-iv-term-structure-validation]]`) — the fourth of four continuous-statistic vol-conditioning constructions to reproduce this same non-monotonic shape.

## Relation to other concepts

Closes the continuous-statistic vol-conditioning line at 4-for-4 ([[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], this page) — an independent review recommended no 5th construction of the same kind. [[event-proximity-vol]] is the 5th and final attempt in this broader search, deliberately different in kind (a binary calendar flag, not an inferred continuous statistic).
