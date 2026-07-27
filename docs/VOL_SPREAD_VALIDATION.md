# IV-minus-RV Vol Spread Validation

**Replayed 1248 trading days, 1228 scored with a full forward window** (2021-07-13 to 2026-07-24).

## Earned premium by spread quintile

(Q1 = lowest/most-negative spread, Q5 = highest spread. Earned premium = IV_t − forward-20d realized vol; positive means the vol sold at IV_t would have come in cheaper than priced.)

| Bucket | n | Mean spread | Mean IV | Mean fwd 20d RV | Mean earned premium | % premium earned |
|---|---|---|---|---|---|---|
| Q1 | 245 | -2.35 | 16.28 | 13.24 | +3.04 | 82% |
| Q2 | 246 | +1.81 | 14.21 | 11.96 | +2.25 | 85% |
| Q3 | 245 | +3.06 | 14.26 | 11.97 | +2.29 | 80% |
| Q4 | 246 | +4.19 | 14.23 | 11.37 | +2.86 | 87% |
| Q5 | 246 | +6.45 | 16.86 | 14.34 | +2.51 | 76% |

## Verdict

- Q5's mean earned premium (+2.51, n=246) vs Q1's (+3.04, n=245): gap = -0.53 vol points.
- Q5's premium-earned hit rate (76%, n=246) vs Q1's (82%, n=245): gap = -6pp.
Read the gaps above against the sample sizes (`n`) in the table — a few points on a handful of days is noise, not signal. This report presents the numbers; it does not compute a significance test, matching the zero-code, direct-arithmetic style of docs/REGIME_VALIDATION.md.
