# Trend-day filter (candidate 21) — stage 1, index points

Rules and the pre-registered bar: `scripts/backtest_trend_day_filter.py` docstring, committed before this run. 1 lot of index futures; costs = scripts/backtest_orb_exits.futures_cost. Holdout = entries from 2025-01-01.

## NIFTY — verdict: **FAIL**

| Rule | N | Gross pts/trade | t (pts) | Win (net) | PF (net) | Net Rs/trade | t (net) | Holdout net Rs/trade |
|---|---|---|---|---|---|---|---|---|
| **PRIMARY** trend day, 2xATR trail | 224 | +4.0 | 0.98 | 34% | 0.81 | -295 | -1.12 | -545 (n=82) |
| all days (no filter), 2xATR trail | 619 | +2.2 | 1.04 | 32% | 0.72 | -410 | -3.01 | -581 (n=240) |
| trend day, hold to 15:20 | 224 | +5.0 | 0.60 | 49% | 0.93 | -226 | -0.41 | -503 (n=82) |
| trend day + VIX rising | 157 | +2.0 | 0.46 | 32% | 0.72 | -422 | -1.49 | -149 (n=57) |
| trend day + unfilled gap | 46 | +8.4 | 0.81 | 26% | 1.01 | +8 | 0.01 | -237 (n=16) |

Primary exits: trailing_stop 221, session_flatten 3

Primary by year: 2022: -5.8 pts (n=31), 2023: -6.0 pts (n=48), 2024: +20.6 pts (n=63), 2025: -2.4 pts (n=50), 2026: +5.7 pts (n=32)

## BANKNIFTY — verdict: **FAIL**

| Rule | N | Gross pts/trade | t (pts) | Win (net) | PF (net) | Net Rs/trade | t (net) | Holdout net Rs/trade |
|---|---|---|---|---|---|---|---|---|
| **PRIMARY** trend day, 2xATR trail | 276 | -8.1 | -0.85 | 33% | 0.68 | -718 | -2.51 | -586 (n=84) |
| all days (no filter), 2xATR trail | 690 | -3.2 | -0.57 | 33% | 0.71 | -572 | -3.38 | -645 (n=219) |
| trend day, hold to 15:20 | 276 | -3.5 | -0.16 | 50% | 0.86 | -579 | -0.88 | +886 (n=84) |
| trend day + VIX rising | 184 | -8.8 | -0.80 | 33% | 0.66 | -736 | -2.24 | -827 (n=54) |
| trend day + unfilled gap | 76 | -14.4 | -0.79 | 32% | 0.63 | -900 | -1.64 | -1,809 (n=21) |

Primary exits: trailing_stop 276

Primary by year: 2021: -0.3 pts (n=32), 2022: -19.8 pts (n=60), 2023: -16.8 pts (n=42), 2024: -3.9 pts (n=58), 2025: +10.0 pts (n=49), 2026: -17.2 pts (n=35)

