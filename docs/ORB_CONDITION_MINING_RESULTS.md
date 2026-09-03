# ORB Condition-Mining — Results

Methodology: docs/ORB_CONDITION_MINING_METHODOLOGY.md. Every row below reports the pre-registered three-step pass bar (min sample size, mining-set improvement, holdout confirmation) -- an 'Informative: no' row is a legitimate, reportable result, not an error.

## NIFTY

1037 trades total. Mining set: 830 trades (2022-06-01 onward). Holdout set: 207 trades (2025-11-03 onward).

| Condition | Mining n | Mining PF | Mining Sharpe | Holdout n | Holdout PF | Holdout Sharpe | Informative | Reason |
|---|---|---|---|---|---|---|---|---|
| stage2 | 32 | 1.75 | 3.24 | 39 | 0.84 | -1.02 | no | passed the mining set but the holdout set did not confirm it — step 3 of 3, this is the check that actually matters |
| monday_or_friday | 327 | 1.41 | 1.54 | 83 | 1.14 | 1.14 | YES | cleared sample size, mining-set improvement, and holdout confirmation |
| wide_range | 174 | 1.65 | 1.72 | 41 | 0.54 | -3.29 | no | passed the mining set but the holdout set did not confirm it — step 3 of 3, this is the check that actually matters |
| narrow_range | 246 | 1.29 | 1.02 | 61 | 1.19 | 0.64 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| big_gap | 340 | 1.32 | 0.74 | 85 | 0.94 | -0.97 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| dte_0_1 | 14 | 0.98 | 0.98 | 5 | 1.11 | -1.25 | no | sample too small (mining n=14, holdout n=5, need >=30 each) — step 1 of 3 |
| dte_10_plus | 0 | 0.00 | 0.00 | 0 | 0.00 | 0.00 | no | sample too small (mining n=0, holdout n=0, need >=30 each) — step 1 of 3 |

## BANKNIFTY

1269 trades total. Mining set: 1015 trades (2021-06-01 onward). Holdout set: 254 trades (2025-08-11 onward).

| Condition | Mining n | Mining PF | Mining Sharpe | Holdout n | Holdout PF | Holdout Sharpe | Informative | Reason |
|---|---|---|---|---|---|---|---|---|
| stage2 | 28 | 0.74 | -2.01 | 121 | 0.94 | -0.27 | no | sample too small (mining n=28, holdout n=121, need >=30 each) — step 1 of 3 |
| monday_or_friday | 403 | 1.07 | 0.59 | 100 | 1.71 | 2.71 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| wide_range | 209 | 1.51 | 2.04 | 51 | 1.11 | 1.06 | no | passed the mining set but the holdout set did not confirm it — step 3 of 3, this is the check that actually matters |
| narrow_range | 278 | 0.90 | -0.19 | 67 | 1.33 | 1.17 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| big_gap | 528 | 1.19 | 1.04 | 109 | 1.44 | 1.62 | YES | cleared sample size, mining-set improvement, and holdout confirmation |
| dte_0_1 | 94 | 2.09 | 3.21 | 24 | 1.21 | -0.10 | no | sample too small (mining n=94, holdout n=24, need >=30 each) — step 1 of 3 |
| dte_10_plus | 638 | 1.06 | 0.16 | 167 | 1.10 | 0.41 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |

