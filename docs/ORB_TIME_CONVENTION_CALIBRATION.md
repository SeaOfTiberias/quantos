# ORB option-pricing time convention — calibration

Method and pre-registered rule: `scripts/calibrate_orb_time_convention.py` docstring (committed before this run). 472 real intraday mid quotes over 38 days (2026-07-29 to 2026-09-30); train < 2026-09-10, holdout from 2026-09-10.

Weights are calendar-day-equivalents of decay per session / weeknight / weekend; k scales India VIX per index.

## Train-fitted conventions, scored on the untouched holdout

| Convention | session | weeknight | weekend | k NIFTY | k BANKNIFTY | Train MSE | Holdout MSE |
|---|---|---|---|---|---|---|---|
| fitted | 1.45 | 0.10 | 1.70 | 0.73 | 0.91 | 0.0153 | 0.0218 |
| calendar | 0.26 | 0.74 | 2.74 | 0.86 | 1.04 | 0.0183 | 0.0865 |
| trading_252 | 1.45 | 0.00 | 0.00 | 0.84 | 1.02 | 0.0178 | 0.0197 |
| fable_bhavcopy_fit | 0.80 | 0.29 | 0.60 | 0.95 | 1.14 | 0.0211 | 0.0286 |

Fitted beats calendar on the holdout: **YES** (pre-registered validation condition).

## Frozen convention (full-sample fit) — used by the backtest

```json
{
  "session": 1.85,
  "weeknight": 0.0,
  "weekend": 0.4,
  "k_nifty": 0.74,
  "k_banknifty": 0.91,
  "mse": 0.016
}
```

Residuals of the frozen convention (negative = model too cheap):

| Slice | N | Mean log error (model - market) |
|---|---|---|
| 09:35 IST | 160 | +0.014 |
| 12:00 IST | 156 | +0.005 |
| 15:15 IST | 156 | -0.023 |
| NIFTY | 236 | -0.006 |
| BANKNIFTY | 236 | +0.004 |

Limitation (stated before running): few quotes under 4 days to expiry; BANKNIFTY month-end 1-3 DTE trades are extrapolated.
