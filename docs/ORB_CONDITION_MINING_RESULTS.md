# ORB Condition-Mining — Results

Methodology: docs/ORB_CONDITION_MINING_METHODOLOGY.md. Every row below reports the pre-registered three-step pass bar (min sample size, mining-set improvement, holdout confirmation) -- an 'Informative: no' row is a legitimate, reportable result, not an error.

## NIFTY

1049 trades total. Mining set: 839 trades (2022-06-01 onward). Holdout set: 210 trades (2025-11-17 onward).

| Condition | Mining n | Mining PF | Mining Sharpe | Holdout n | Holdout PF | Holdout Sharpe | Informative | Reason |
|---|---|---|---|---|---|---|---|---|
| stage2 | 41 | 1.34 | 1.82 | 30 | 1.00 | -0.05 | no | passed the mining set but the holdout set did not confirm it — step 3 of 3, this is the check that actually matters |
| monday_or_friday | 331 | 1.38 | 1.46 | 84 | 1.22 | 1.62 | YES | cleared sample size, mining-set improvement, and holdout confirmation |
| wide_range | 176 | 1.61 | 1.63 | 42 | 0.63 | -1.97 | no | passed the mining set but the holdout set did not confirm it — step 3 of 3, this is the check that actually matters |
| narrow_range | 248 | 1.26 | 0.92 | 61 | 1.29 | 1.14 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| big_gap | 342 | 1.30 | 0.69 | 87 | 1.05 | -0.07 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| dte_0_1 | 14 | 0.98 | 0.98 | 4 | 1.90 | 2.77 | no | sample too small (mining n=14, holdout n=4, need >=30 each) — step 1 of 3 |
| dte_10_plus | 0 | 0.00 | 0.00 | 0 | 0.00 | 0.00 | no | sample too small (mining n=0, holdout n=0, need >=30 each) — step 1 of 3 |

## BANKNIFTY

1280 trades total. Mining set: 1024 trades (2021-06-01 onward). Holdout set: 256 trades (2025-08-26 onward).

| Condition | Mining n | Mining PF | Mining Sharpe | Holdout n | Holdout PF | Holdout Sharpe | Informative | Reason |
|---|---|---|---|---|---|---|---|---|
| stage2 | 37 | 0.71 | -1.94 | 112 | 0.96 | -0.14 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| monday_or_friday | 407 | 1.07 | 0.60 | 101 | 1.73 | 2.80 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| wide_range | 210 | 1.52 | 2.06 | 52 | 1.14 | 1.54 | no | passed the mining set but the holdout set did not confirm it — step 3 of 3, this is the check that actually matters |
| narrow_range | 278 | 0.90 | -0.19 | 69 | 1.31 | 1.03 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |
| big_gap | 531 | 1.17 | 0.99 | 110 | 1.53 | 2.18 | YES | cleared sample size, mining-set improvement, and holdout confirmation |
| dte_0_1 | 94 | 2.09 | 3.21 | 23 | 1.30 | 0.28 | no | sample too small (mining n=94, holdout n=23, need >=30 each) — step 1 of 3 |
| dte_10_plus | 643 | 1.06 | 0.13 | 173 | 1.11 | 0.56 | no | did not clear has_positive_edge with a margin over the mining-set baseline — step 2 of 3 |

