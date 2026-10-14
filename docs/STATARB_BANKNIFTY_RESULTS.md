# BankNifty Residual Mean Reversion — Results

Methodology: docs/STATARB_BANKNIFTY_METHODOLOGY.md (pre-registered). Universe (14): AUBANK, AXISBANK, BANKBARODA, CANBK, FEDERALBNK, HDFCBANK, ICICIBANK, IDFCFIRSTB, INDUSINDBK, KOTAKBANK, PNB, SBIN, UNIONBANK, YESBANK. Evaluation 2020-02-25 to 2026-10-12. All figures net of the futures cost model + 2 bps/side slippage; % basis = ₹5L stock-leg notional.

## Verdict (M1, primary)

**FAIL**

| Check | M1 | M2 (info only) |
|---|---|---|
| edge (PF > 1 and Sharpe > 0.5) | FAIL | FAIL |
| PF > 1 first half | pass | pass |
| PF > 1 second half | FAIL | FAIL |
| PF > 1 exits 2025+ | FAIL | FAIL |
| calibration: long bucket > 0 | FAIL | FAIL |
| calibration: short bucket < 0 | FAIL | pass |
| calibration: t > 2 | FAIL | FAIL |

## M1

### Trade summary

| Slice | Trades | Win rate | PF | Sharpe | Net % (sum) | Max DD | Avg days |
|---|---|---|---|---|---|---|---|
| All | 558 | 52.5% | 0.92 | -0.24 | -73.5% | 189.3% | 8.9 |
| First half | 279 | 59.5% | 1.19 | 0.49 | +86.5% | 62.0% | 8.3 |
| Second half | 279 | 45.5% | 0.64 | -1.41 | -159.9% | 179.3% | 9.6 |
| Long only | 282 | 53.5% | 0.84 | -0.35 | -83.1% | 117.8% | 9.9 |
| Short only | 276 | 51.4% | 1.02 | 0.05 | +9.6% | 107.2% | 7.9 |
| 2020 | 68 | 58.8% | 1.45 | 1.16 | +62.8% | 32.0% | 7.8 |
| 2021 | 89 | 55.1% | 0.85 | -0.52 | -23.6% | 51.2% | 8.1 |
| 2022 | 81 | 67.9% | 1.41 | 0.73 | +46.0% | 62.0% | 8.7 |
| 2023 | 87 | 54.0% | 1.14 | 0.42 | +12.0% | 39.3% | 8.9 |
| 2024 | 76 | 46.1% | 0.75 | -0.85 | -32.6% | 40.3% | 9.1 |
| 2025 | 85 | 38.8% | 0.45 | -2.88 | -76.0% | 76.5% | 10.8 |
| 2026 | 72 | 47.2% | 0.56 | -1.83 | -62.1% | 79.7% | 9.0 |

Gross P&L ₹184,870, costs ₹552,240, net ₹-367,370. Open positions: average 3.0, max 10.

### Exit reasons

| Reason | Trades | Net P&L |
|---|---|---|
| reverted | 428 | ₹2,313,881 |
| pre_results | 60 | ₹-891,285 |
| max_hold | 57 | ₹-1,718,703 |
| stop | 7 | ₹-17,316 |
| end_of_data | 6 | ₹-53,947 |

### Per symbol

| Symbol | Trades | Net P&L | PF |
|---|---|---|---|
| AUBANK | 32 | ₹-392,811 | 0.30 |
| AXISBANK | 41 | ₹-39,789 | 0.85 |
| BANKBARODA | 46 | ₹146,182 | 1.50 |
| CANBK | 41 | ₹98,102 | 1.39 |
| FEDERALBNK | 54 | ₹-43,354 | 0.90 |
| HDFCBANK | 37 | ₹63,173 | 1.29 |
| ICICIBANK | 46 | ₹-29,558 | 0.90 |
| IDFCFIRSTB | 51 | ₹-162,907 | 0.70 |
| INDUSINDBK | 46 | ₹-81,608 | 0.85 |
| KOTAKBANK | 47 | ₹93,984 | 1.39 |
| PNB | 55 | ₹68,342 | 1.18 |
| SBIN | 46 | ₹26,538 | 1.10 |
| UNIONBANK | 9 | ₹-25,594 | 0.72 |
| YESBANK | 7 | ₹-88,068 | 0.35 |

### Calibration (10-day forward residual return, non-overlapping, tradeable days)

| s bucket | Samples | Mean fwd residual |
|---|---|---|
| s <= -2 | 24 | +0.43% |
| -2 < s <= -1.25 | 174 | -0.30% |
| -1.25 < s < 1.25 | 1413 | -0.00% |
| 1.25 <= s < 2 | 177 | +0.07% |
| s >= 2 | 20 | -0.26% |

Long bucket (s ≤ −1.25): n=198, mean -0.21%. Short bucket (s ≥ +1.25): n=197, mean +0.04%. Welch t = -0.40.

### Stock-days with no s-score (exclusions)

| Reason | Stock-days |
|---|---|
| missing_data | 3298 |
| corp_action_jump | 991 |
| structural_break | 329 |

## M2

### Trade summary

| Slice | Trades | Win rate | PF | Sharpe | Net % (sum) | Max DD | Avg days |
|---|---|---|---|---|---|---|---|
| All | 561 | 54.7% | 0.89 | -0.30 | -98.5% | 228.5% | 8.8 |
| First half | 280 | 57.9% | 1.22 | 0.53 | +92.3% | 64.0% | 8.1 |
| Second half | 281 | 51.6% | 0.60 | -1.26 | -190.8% | 228.5% | 9.5 |
| Long only | 281 | 54.4% | 0.75 | -0.48 | -132.7% | 168.4% | 9.8 |
| Short only | 280 | 55.0% | 1.09 | 0.20 | +34.2% | 78.8% | 7.8 |
| 2020 | 79 | 60.8% | 1.62 | 1.55 | +82.8% | 43.8% | 7.1 |
| 2021 | 86 | 51.2% | 0.92 | -0.26 | -10.8% | 36.2% | 8.2 |
| 2022 | 75 | 64.0% | 1.00 | -0.01 | -0.4% | 64.0% | 9.5 |
| 2023 | 89 | 60.7% | 1.34 | 0.93 | +27.3% | 28.6% | 8.6 |
| 2024 | 78 | 55.1% | 1.05 | 0.14 | +4.9% | 25.9% | 8.5 |
| 2025 | 86 | 45.4% | 0.29 | -2.08 | -123.9% | 128.0% | 10.3 |
| 2026 | 68 | 45.6% | 0.48 | -2.23 | -78.5% | 87.8% | 9.6 |

Gross P&L ₹98,734, costs ₹591,187, net ₹-492,453. Open positions: average 3.0, max 10.

### Exit reasons

| Reason | Trades | Net P&L |
|---|---|---|
| reverted | 436 | ₹2,058,390 |
| max_hold | 56 | ₹-1,635,041 |
| pre_results | 54 | ₹-711,717 |
| end_of_data | 8 | ₹-65,952 |
| stop | 7 | ₹-138,133 |

### Per symbol

| Symbol | Trades | Net P&L | PF |
|---|---|---|---|
| AUBANK | 33 | ₹-423,579 | 0.28 |
| AXISBANK | 45 | ₹14,061 | 1.07 |
| BANKBARODA | 49 | ₹182,927 | 1.86 |
| CANBK | 40 | ₹198,010 | 1.90 |
| FEDERALBNK | 59 | ₹-163,150 | 0.70 |
| HDFCBANK | 36 | ₹-113,432 | 0.71 |
| ICICIBANK | 55 | ₹16,077 | 1.06 |
| IDFCFIRSTB | 46 | ₹-228,877 | 0.56 |
| INDUSINDBK | 47 | ₹-192,538 | 0.69 |
| KOTAKBANK | 41 | ₹-15,273 | 0.94 |
| PNB | 50 | ₹147,868 | 1.46 |
| SBIN | 44 | ₹64,469 | 1.32 |
| UNIONBANK | 8 | ₹44,216 | 2.47 |
| YESBANK | 8 | ₹-23,232 | 0.83 |

### Calibration (10-day forward residual return, non-overlapping, tradeable days)

| s bucket | Samples | Mean fwd residual |
|---|---|---|
| s <= -2 | 24 | -0.34% |
| -2 < s <= -1.25 | 168 | -0.59% |
| -1.25 < s < 1.25 | 1426 | +0.02% |
| 1.25 <= s < 2 | 165 | -0.19% |
| s >= 2 | 25 | -1.13% |

Long bucket (s ≤ −1.25): n=192, mean -0.56%. Short bucket (s ≥ +1.25): n=190, mean -0.32%. Welch t = -0.41.

### Stock-days with no s-score (exclusions)

| Reason | Stock-days |
|---|---|
| missing_data | 3298 |
| corp_action_jump | 991 |
| structural_break | 329 |

## Disclosed limitations

- Current constituent list applied to the whole history (no point-in-time membership).
- Results blackout uses actual results dates as if known in advance (board-meeting notice is normally given days ahead).
- Every signal taken with no capital limit: this measures the signal, not a portfolio.
- Hedge P&L uses the leave-one-out peer basket; a live hedge would be one BANKNIFTY future (tracking error not modelled). M2's 13-stock hedge is costed as one instrument (understated).
- Results dates: NSE's filing-metadata API returns almost nothing after ~2025-02, which left the blackout mostly off for 2025-26 in the first run. Fixed (data, not rules) by merging NSE results board-meeting dates (date only; meeting day = reaction day). The first run's verdict was also FAIL (M1 PF 0.78, calibration t -0.40).
- The paper's speed filter (1/(-ln b) < 30 days on 60 observations) is weak: the AR(1) slope is biased down on short samples, and about 65% of simulated pure random walks pass it (tests/unit/test_statarb.py). Kept as pre-registered.
