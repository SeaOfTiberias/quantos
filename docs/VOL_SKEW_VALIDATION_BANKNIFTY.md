# BANKNIFTY Option Skew Validation

Methodology: docs/VOL_SKEW_METHODOLOGY.md + docs/VOL_SKEW_METHODOLOGY_BANKNIFTY_ADDENDUM.md. Replayed 611 days (2024-01-31 to 2026-07-24), 591 scored with a valid skew and full forward window.

## Skipped days

- none

## Forward realized vol by skew quintile

(Q1 = lowest/most-negative skew i.e. calls pricier than puts, Q5 = highest skew i.e. puts pricing richest.)

| Bucket | n | Mean skew | Mean fwd 20d RV |
|---|---|---|---|
| Q1 | 118 | +0.00 | 14.91 |
| Q2 | 117 | +0.02 | 12.54 |
| Q3 | 119 | +0.03 | 13.27 |
| Q4 | 118 | +0.04 | 14.24 |
| Q5 | 119 | +0.06 | 18.03 |

## Verdict

- Q5 mean fwd RV (18.03, n=119) vs Q1 (14.91, n=118): gap = +3.11 vol points.
- Full Q1→Q5 sequence monotonically non-decreasing: False.
- Per docs/VOL_SKEW_METHODOLOGY.md's pass bar: FAIL (monotonic AND Q5 > Q1 required).
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and docs/VOL_SPREAD_VALIDATION.md's style.
