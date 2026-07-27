# NIFTY ATM IV Term Structure Validation

Methodology: docs/VOL_TERM_STRUCTURE_METHODOLOGY.md. Replayed 612 days (2024-01-31 to 2026-07-27), 592 scored with a valid spread and full forward window.

## Skipped days

- none

## Forward realized vol by term-structure-spread quintile

(Q1 = most negative spread i.e. deepest contango/calm shape, Q5 = most positive spread i.e. deepest backwardation/stress shape.)

| Bucket | n | Mean spread | Mean fwd 20d RV |
|---|---|---|---|
| Q1 | 118 | -0.02 | 12.46 |
| Q2 | 118 | -0.01 | 11.82 |
| Q3 | 117 | -0.00 | 11.10 |
| Q4 | 120 | +0.00 | 12.41 |
| Q5 | 119 | +0.02 | 14.57 |

## Verdict

- Q5 mean fwd RV (14.57, n=119) vs Q1 (12.46, n=118): gap = +2.11 vol points.
- Full Q1→Q5 sequence monotonically non-decreasing: False.
- Per docs/VOL_TERM_STRUCTURE_METHODOLOGY.md's pass bar: FAIL (monotonic AND Q5 > Q1 required).
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and every prior vol-conditioning report.
