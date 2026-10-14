---
title: 'Candidate 18 — fix 2 results (BANKNIFTY expiry day + entry lag)'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\ORB_FIX2_RESULTS.md'
checksum: ee1663b8965eff056ac241475656c8342f1d7f5cfc1fde635e64474a395b173a
body_checksum: 13197dd85bf385e51ae90eae6ad980191535ce0e68885cb46168d06026071ad6
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Candidate 18 — fix 2 results (BANKNIFTY expiry day + entry lag)

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\ORB_FIX2_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Data fetched 2026-09-30T14:28:21.255175+00:00. Stratified costs, 1 lot per trade. Bar = PF > 1.0 and Sharpe > 0.5. Method, runs and the decision rule: `scripts/backtest_orb_fix2.py` docstring (committed before this run).

## NIFTY

| Run | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |
|---|---|---|---|---|---|---|
| A locked-final (old pricing) | 1056 | 48% | 1.23 | 1.19 | 245,437 | PASS |
| B corrected pricing | 1056 | 47% | 1.12 | 0.68 | 135,978 | PASS |
| E corrected + 1-candle lag | 1056 | 46% | 1.15 | 0.74 | 155,632 | PASS |

## BANKNIFTY

| Run | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |
|---|---|---|---|---|---|---|
| A locked-final (old pricing) | 1287 | 46% | 1.16 | 1.27 | 282,583 | PASS |
| B corrected pricing | 1287 | 44% | 1.09 | 0.91 | 158,799 | PASS |
| C corrected + BN roll | 1287 | 46% | 1.06 | 0.58 | 116,213 | PASS |
| D corrected + BN skip | 1223 | 46% | 1.07 | 0.62 | 132,535 | PASS |
| E corrected + 1-candle lag | 1285 | 43% | 1.07 | 0.85 | 118,393 | PASS |

## BANKNIFTY expiry-day trades only (A vs B)

| Run | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |
|---|---|---|---|---|---|---|
| A old pricing | 64 | 33% | 1.73 | 0.70 | 37,567 | PASS |
| B corrected pricing | 64 | 19% | 1.83 | 0.68 | 26,264 | PASS |

## Pre-registered BANKNIFTY decision

roll PF 1.06 vs skip PF 1.07 (tie band 0.05) -> **skip**. To be brought to the user before any live rule change.
