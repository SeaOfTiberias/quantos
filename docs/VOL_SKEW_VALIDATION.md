# NIFTY Option Skew Validation

Methodology: docs/VOL_SKEW_METHODOLOGY.md. Replayed 611 days (2024-01-31 to 2026-07-24), 591 scored with a valid skew and full forward window.

## Skipped days

- none

## Forward realized vol by skew quintile

(Q1 = lowest/most-negative skew i.e. calls pricier than puts, Q5 = highest skew i.e. puts pricing richest.)

| Bucket | n | Mean skew | Mean fwd 20d RV |
|---|---|---|---|
| Q1 | 118 | +0.01 | 12.78 |
| Q2 | 115 | +0.03 | 11.53 |
| Q3 | 120 | +0.04 | 11.54 |
| Q4 | 119 | +0.04 | 11.71 |
| Q5 | 119 | +0.07 | 14.82 |

## Verdict

- Q5 mean fwd RV (14.82, n=119) vs Q1 (12.78, n=118): gap = +2.04 vol points.
- Full Q1→Q5 sequence monotonically non-decreasing: False.
- Per docs/VOL_SKEW_METHODOLOGY.md's pass bar: FAIL (monotonic AND Q5 > Q1 required).
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and docs/VOL_SPREAD_VALIDATION.md's style.
