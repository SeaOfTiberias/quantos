# Candidate 18 under the calibrated time convention

Frozen convention from `docs\ORB_TIME_CONVENTION_CALIBRATION.md`: session 1.85, weeknight 0.0, weekend 0.4 (calendar-day-equivalents); VIX scale NIFTY 0.74, BANKNIFTY 0.91. Holdout-validated: **YES**. Stratified costs, 1 lot, BANKNIFTY expiry day skipped. Method and rule: `scripts/backtest_orb_time_convention.py` docstring (committed before this run).

## NIFTY

| Convention | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |
|---|---|---|---|---|---|---|
| frozen (calibrated) | 1056 | 43% | 0.85 | -1.14 | -181,838 | FAIL |
| calendar (fix-2 B/D) | 1056 | 47% | 1.12 | 0.68 | 135,978 | PASS |
| 252 trading days | 1056 | 42% | 0.73 | -2.17 | -370,538 | FAIL |

## BANKNIFTY

| Convention | N | Win | PF | Sharpe | Net Rs (1 lot) | Bar |
|---|---|---|---|---|---|---|
| frozen (calibrated) | 1223 | 42% | 0.82 | -1.30 | -371,312 | FAIL |
| calendar (fix-2 B/D) | 1223 | 46% | 1.07 | 0.62 | 132,535 | PASS |
| 252 trading days | 1223 | 42% | 0.84 | -1.13 | -323,442 | FAIL |

## Verdict (pre-registered rule)

NIFTY FAIL, BANKNIFTY FAIL under the frozen convention -> candidate 18 **FAILS**. Recommendation: close candidate 18 (the user decides).

