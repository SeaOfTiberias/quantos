---
title: 'Pairs Trading Backtest Results (Candidate 12)'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\PAIRS_TRADING_RESULTS.md'
checksum: 8508574bd771a0d9bc24aec1e6095fe76f132fab6c38247077844cc7cc763525
body_checksum: 6b756188013d289abe10b9b04b030247019a7fa5f10f512cdc6ed414f263244f
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Pairs Trading Backtest Results (Candidate 12)

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\PAIRS_TRADING_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/PAIRS_TRADING_METHODOLOGY.md. 12 sectors qualifying (>=2 futures-listed symbols each), 972 same-sector candidate pairs, 8 walk-forward folds.

## Universe

| Sector | Qualifying symbols |
|---|---|
| niftyauto | 15 |
| niftybank | 14 |
| niftyconsumerdurables | 9 |
| niftyenergy | 25 |
| niftyfmcg | 13 |
| niftyhealthcare | 16 |
| niftyit | 10 |
| niftymetal | 11 |
| niftyoilgas | 8 |
| niftypharma | 13 |
| niftypsubank | 7 |
| niftyrealty | 6 |

## Per-fold breakdown

| Formation | Trading | Pairs tested | Pairs passed | Trades | Net P&L | Profit factor |
|---|---|---|---|---|---|---|
| 2024-01-01 to 2024-07-01 | 2024-07-01 to 2024-10-01 | 504 | 77 | 324 | +865023 | 1.23 |
| 2024-04-01 to 2024-10-01 | 2024-10-01 to 2025-01-01 | 513 | 108 | 573 | +615814 | 1.08 |
| 2024-07-01 to 2025-01-01 | 2025-01-01 to 2025-04-01 | 726 | 145 | 800 | +2205897 | 1.29 |
| 2024-10-01 to 2025-04-01 | 2025-04-01 to 2025-07-01 | 742 | 158 | 732 | +1063424 | 1.15 |
| 2025-01-01 to 2025-07-01 | 2025-07-01 to 2025-10-01 | 832 | 200 | 598 | +556724 | 1.07 |
| 2025-04-01 to 2025-10-01 | 2025-10-01 to 2026-01-01 | 868 | 212 | 625 | -711804 | 0.91 |
| 2025-07-01 to 2026-01-01 | 2026-01-01 to 2026-04-01 | 904 | 213 | 627 | -4448729 | 0.68 |
| 2025-10-01 to 2026-04-01 | 2026-04-01 to 2026-07-01 | 913 | 129 | 426 | -3965642 | 0.62 |

## Pooled result (all folds, net of the F&O futures cost model)

- Trades: 4705
- Win rate: 49.3%
- Total net P&L: Rs -3,819,293
- Profit factor: 0.94
- Sharpe (core/backtest/parser.py convention, %-return basis = combined pair notional): -0.17

## Verdict

Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), computed on the pooled trading-window trades net of costs: **FAIL**.
Per the methodology doc's own disclosed limitation: no multiple-testing correction was applied to the p<0.05 cointegration threshold, and this is only ~8 walk-forward folds -- read the per-fold table above, not just the pooled row, before trusting this.
