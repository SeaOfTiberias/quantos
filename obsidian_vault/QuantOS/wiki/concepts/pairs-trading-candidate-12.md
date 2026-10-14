---
title: Sector-Cointegrated Stock-Futures Pairs Trading (Candidate 12)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: pairs-trading-candidate-12
candidate: 12
family: stat-arb
instrument: stock-futures
status: closed
verdict: FAIL
first_tested: 2026-07-25
verdict_date: 2026-07-26
profit_factor: 0.94
sharpe: -0.17
trades: 4705
bar: "PF > 1 and Sharpe > 0.5 pooled over 8 walk-forward folds"
headline: "Same-sector cointegrated stock-futures pairs: folds 1–5 profitable, folds 6–8 collapse, net −₹38.2L."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-sector-cointegrated-stock-futures-pairs-trading-methodology, 2026-09-17-pairs-trading-backtest-results-candidate-12
---

# Sector-Cointegrated Stock-Futures Pairs Trading (Candidate 12)

> [!abstract] Compiled page
> Written from `[[2026-09-17-sector-cointegrated-stock-futures-pairs-trading-methodology]]` and `[[2026-09-17-pairs-trading-backtest-results-candidate-12]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A classic statistical-arbitrage pairs trade, using single-stock futures (not cash equity) for both legs specifically to get a legal overnight short — the constraint that had already killed the index-reconstitution candidate's short leg. Backed by real NSE-specific academic papers finding same-sector pairs (Auto and Realty strongest) cointegrate and produce positive risk-adjusted returns.

## Mechanics

- **Universe**: stocks with a listed near-month future AND membership in one of 13 NSE sectoral indices — pairs formed only within the same sector, never cross-sector (972 candidate pairs across 12 qualifying sectors).
- **Cointegration**: Engle-Granger test (OLS hedge ratio on log prices, ADF on the residual spread), pass bar ADF p<0.05 — no multiple-testing correction applied, a disclosed limitation given ~200-300 tests per formation window.
- **Walk-forward**: 6-month formation window (test), 3-month trading window (trade), frozen hedge ratio/spread mean/std throughout the trading window — 8 non-overlapping quarterly folds, 2024-01-01 to latest cached bhavcopy.
- **Entry/exit**: enter when `|z|` crosses 2.0 (short the spread if z>+2, long if z<-2); exit at z=0.0, or 20 trading days elapsed, or 3 days before near-month expiry (force-close, no roll — no back-adjusted continuous series is built).
- **Cost model**: new, futures-specific — time-varying STT (0.0125%→0.02%→0.05%), ₹1.73/lakh exchange charge, 0.002% stamp duty, time-varying GST-on-SEBI cutover.

## Verdict

**FAIL.** Pooled across all 8 folds, 4705 trades: profit factor 0.94, Sharpe -0.17, net P&L **-₹3,819,293** `[[2026-09-17-pairs-trading-backtest-results-candidate-12]]`. The per-fold picture shows real early strength collapsing later — folds 1–5 all profitable (PF 1.07–1.29), folds 6–8 all losing (PF 0.91, 0.68, 0.62) and large enough in magnitude to erase the earlier gains.

## Relation to other concepts

A later independent review found two real, previously undisclosed construction bugs (unadjusted corporate-action jumps, unadjusted futures-roll splicing) — see [[pairs-trading-v2-candidate-17]] for the bug-fixed re-run and whether fixing them changed this verdict.
- [[statarb-residual-mean-reversion]] tested the stock-versus-family version (a residual against a factor basket, not one partner stock) on the same futures data and cost model. It also failed, retiring mean reversion on NSE stock futures.
