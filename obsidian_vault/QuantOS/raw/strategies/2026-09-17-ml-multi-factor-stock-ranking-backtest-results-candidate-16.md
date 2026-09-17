---
title: 'ML Multi-Factor Stock Ranking — Backtest Results (Candidate 16)'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\ML_FACTOR_COMBINATION_RESULTS.md'
checksum: f2425b949fce850d024db59a6c5d286b1bbc3b46602fd3d7a6448d1930eb8787
body_checksum: 658ae76fa98b6a10fa6b03d04d2f7e30c92529b9548c7597c8329e601e8e5972
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# ML Multi-Factor Stock Ranking — Backtest Results (Candidate 16)

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\ML_FACTOR_COMBINATION_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/ML_FACTOR_COMBINATION_METHODOLOGY.md. Nifty 500 universe, 610/648 symbols had enough history to ever be scored. Split date: 2025-06-29 (train before, test on/after). Train rows: 49646, test rows: 26783. Selected C=1.0. Train AUC: 0.552, Test AUC: 0.538.

## Turnover/cost check (added after Fable's review of the first cut of this candidate) — is the net gap below a real signal, or a turnover-cost artifact?

| | ML | Baseline |
|---|---|---|
| Trades (test period) | 236 | 656 |
| Real transaction costs paid (NET run) | ₹41,128 | ₹132,713 |
| Total return, NET of costs | 4.4% | -2.1% |
| Total return, GROSS (zero-cost re-run) | 8.3% | 10.6% |

NET gap (ML − baseline): +6.5pts. GROSS gap (ML − baseline, zero-cost): -2.3pts. **The gap DOES NOT SURVIVE removing transaction costs entirely** — the ML strategy only "wins" once its lower turnover is rewarded by the cost model -- with costs removed, the single-factor baseline is AT LEAST AS GOOD, meaning the whole net-of-cost "win" in this report is a turnover artifact, not evidence of a real predictive edge.

## ML-ranked strategy (test period only, fresh capital-tracked run)

## ML model

- Final equity: ₹1,044,254
- Total return: 4.4%
- CAGR: 4.1%
- Sharpe: 0.29
- Max drawdown: 23.7%
- Trades: 236
- Total transaction costs paid: ₹41,128

## Single-factor-momentum baseline (test period only, fresh run, same harness)

## Baseline (rank_universe)

- Final equity: ₹979,046
- Total return: -2.1%
- CAGR: -1.9%
- Sharpe: -0.06
- Max drawdown: 14.8%
- Trades: 656
- Total transaction costs paid: ₹132,713

## vs. Nifty 500 buy-and-hold (test period)

- Final equity: ₹940,299
- Total return: -6.0%
- CAGR: -5.6%
- Sharpe: -0.39
- Max drawdown: 15.2%
- Alpha vs this benchmark: total return +10.4pts, CAGR +9.7pts, beats it: Yes

## vs. Nifty Alpha 50 buy-and-hold (test period)

- Final equity: ₹994,864
- Total return: -0.5%
- CAGR: -0.5%
- Sharpe: 0.07
- Max drawdown: 17.5%
- Alpha vs this benchmark: total return +4.9pts, CAGR +4.6pts, beats it: Yes

## Verdict

Per docs/ML_FACTOR_COMBINATION_METHODOLOGY.md's bar — ALL FOUR required, test period only:
1. CAGR>0% and Sharpe>0.5: FAIL (CAGR 4.1%, Sharpe 0.29)
2. Beats Nifty 500 buy-and-hold: PASS
3. Beats Nifty Alpha 50 buy-and-hold: PASS
4. Beats single-factor-momentum baseline (4.4% vs -2.1%): PASS — **but see the turnover/cost check above before trusting this criterion**: the gap DOES NOT survive at zero cost, i.e. this PASS is a turnover artifact, not a stock-selection edge.

**Overall: FAIL** (all four required, mechanical bar only — and criterion 4 above is disclosed as untrustworthy regardless of this mechanical result — read the turnover/cost check, not just this line).

Single held-out test period, not a distribution — no confidence interval on any of the above. Treat as one realization, not an expected value, same caveat S8-3's own equity-curve report carries.
