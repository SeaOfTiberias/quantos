# Pairs Trading v2 Backtest Results (Candidate 17)

Methodology: docs/PAIRS_TRADING_V2_METHODOLOGY.md (bug-fix re-run of candidate 12, docs/PAIRS_TRADING_METHODOLOGY.md). 12 sectors qualifying, 972 same-sector candidate pairs, 8 walk-forward folds -- identical universe/schedule/cost-model to candidate 12.

## New-fix disclosures

- Pairs excluded (either leg, either window) by the corporate-action jump guard, summed across all folds: 405.
- Symbols with at least one futures-roll seam left UNADJUSTED (missing a same-day next-month price at that roll): 0, 0 seams total.

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

## Per-fold breakdown, v2 vs v1

| Formation | Trading | Pairs tested | Pairs passed | Corp-action excluded | Trades | Net P&L | PF (v2) | PF (v1) |
|---|---|---|---|---|---|---|---|---|
| 2024-01-01 to 2024-07-01 | 2024-07-01 to 2024-10-01 | 455 | 73 | 50 | 334 | +561641 | 1.14 | 1.23 |
| 2024-04-01 to 2024-10-01 | 2024-10-01 to 2025-01-01 | 441 | 94 | 72 | 468 | +324033 | 1.05 | 1.08 |
| 2024-07-01 to 2025-01-01 | 2025-01-01 to 2025-04-01 | 685 | 144 | 41 | 837 | +2745102 | 1.38 | 1.29 |
| 2024-10-01 to 2025-04-01 | 2025-04-01 to 2025-07-01 | 694 | 163 | 49 | 765 | +623218 | 1.09 | 1.15 |
| 2025-01-01 to 2025-07-01 | 2025-07-01 to 2025-10-01 | 777 | 195 | 55 | 570 | +1948076 | 1.32 | 1.07 |
| 2025-04-01 to 2025-10-01 | 2025-10-01 to 2026-01-01 | 813 | 202 | 55 | 552 | -781518 | 0.88 | 0.91 |
| 2025-07-01 to 2026-01-01 | 2026-01-01 to 2026-04-01 | 844 | 180 | 60 | 540 | -1841476 | 0.83 | 0.68 |
| 2025-10-01 to 2026-04-01 | 2026-04-01 to 2026-07-01 | 890 | 142 | 23 | 469 | -1229568 | 0.87 | 0.62 |

## Pooled result, v2 vs v1 (net of the same F&O futures cost model)

| | v2 (this run) | v1 (candidate 12, original) |
|---|---|---|
| Trades | 4535 | 4705 |
| Win rate | 50.2% | - |
| Total net P&L | Rs +2,349,508 | Rs -3,819,293 |
| Profit factor | 1.04 | 0.94 |
| Sharpe | 0.14 | -0.17 |

## Verdict

Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), computed on the pooled trading-window trades net of costs: **FAIL**.

Both fixes are confirmed real construction bugs per Fable's 2026-07-26 review -- this re-run answers whether fixing them changes the verdict, not whether they were worth fixing (they were, independent of this outcome). Read the per-fold PF columns above, especially folds 6-8 (candidate 12's original collapse: PF 0.91, 0.68, 0.62), before trusting the pooled row alone -- same discipline candidate 12's own report used.
