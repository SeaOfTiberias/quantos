# Mean-Reversion (Nifty Alpha 50) Gut-Check

**38520 total observed days** across the universe (1159 signal days, 37361 baseline days).

NOT a backtest — no costs, no position sizing, no threshold tuning. See core/meanreversion/gutcheck.py's module docstring for the remaining flagged deviation from the strategy as specified (NIFTY 50 fallback trend for stocks with no matching real sectoral index).

## Signal clustering

**1159 signal-day observations fall on only 394 distinct calendar dates** (2.9 stocks/date on average, largest single-date cluster: 15 stocks). If this ratio is well above 1, the effective number of independent events is closer to the distinct-date count than to the raw signal-day count — read the `n` in the tables below with that in mind.

## Forward return: signal vs baseline (full sample)

| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |
|---|---|---|---|---|---|---|---|
| 5 | 1159 | +0.85 | 56% | 37361 | +0.67 | 54% | +0.19 |
| 10 | 1145 | +1.99 | 60% | 37121 | +1.56 | 57% | +0.43 |
| 20 | 1127 | +3.43 | 63% | 36642 | +3.36 | 62% | +0.06 |

### Forward return: signal vs baseline (full sample) — market-adjusted (demeaned by this sample's own cross-sectional mean per horizon, signal+baseline combined)

| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |
|---|---|---|---|---|---|---|---|
| 5 | 1159 | +0.18 | 51% | 37361 | -0.01 | 48% | +0.19 |
| 10 | 1145 | +0.42 | 49% | 37121 | -0.01 | 47% | +0.43 |
| 20 | 1127 | +0.06 | 46% | 36642 | -0.00 | 47% | +0.06 |

## Sector-mapped stocks only (real NSE sectoral index, not NIFTY 50 fallback)

| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |
|---|---|---|---|---|---|---|---|
| 5 | 666 | +0.73 | 56% | 19613 | +0.63 | 54% | +0.10 |
| 10 | 662 | +2.00 | 61% | 19486 | +1.48 | 57% | +0.52 |
| 20 | 654 | +3.05 | 61% | 19237 | +3.23 | 62% | -0.18 |

### Sector-mapped stocks only (real NSE sectoral index, not NIFTY 50 fallback) — market-adjusted (demeaned by this sample's own cross-sectional mean per horizon, signal+baseline combined)

| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |
|---|---|---|---|---|---|---|---|
| 5 | 666 | +0.10 | 52% | 19613 | -0.00 | 48% | +0.10 |
| 10 | 662 | +0.50 | 52% | 19486 | -0.02 | 48% | +0.52 |
| 20 | 654 | -0.17 | 46% | 19237 | +0.01 | 46% | -0.18 |

## NIFTY-50-fallback stocks only (no matching real sectoral index)

| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |
|---|---|---|---|---|---|---|---|
| 5 | 493 | +1.02 | 56% | 17748 | +0.71 | 54% | +0.31 |
| 10 | 483 | +1.98 | 59% | 17635 | +1.64 | 56% | +0.34 |
| 20 | 473 | +3.95 | 66% | 17405 | +3.52 | 61% | +0.43 |

### NIFTY-50-fallback stocks only (no matching real sectoral index) — market-adjusted (demeaned by this sample's own cross-sectional mean per horizon, signal+baseline combined)

| Horizon | Signal n | Signal mean % | Signal win% | Baseline n | Baseline mean % | Baseline win% | Gap (signal − baseline) |
|---|---|---|---|---|---|---|---|
| 5 | 493 | +0.30 | 50% | 17748 | -0.01 | 48% | +0.31 |
| 10 | 483 | +0.33 | 45% | 17635 | -0.01 | 47% | +0.34 |
| 20 | 473 | +0.42 | 46% | 17405 | -0.01 | 47% | +0.43 |

## Verdict

Read the gaps above against the sample sizes (`n`) in the tables — a few points on a handful of days is noise, not signal, and the clustering count above matters more than the raw signal-day `n`. This report presents the numbers; it does not compute a significance test, matching the zero-code, direct-arithmetic style of docs/REGIME_VALIDATION.md and the PEAD gut-check.
