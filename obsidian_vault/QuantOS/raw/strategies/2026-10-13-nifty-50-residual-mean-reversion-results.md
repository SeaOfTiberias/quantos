---
title: 'Nifty 50 Residual Mean Reversion — Results'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\STATARB_NIFTY50_RESULTS.md'
checksum: 45255c1798a6c0a2146e85287d02aeac2dc815c6b4398d2c206f3ab1c44ee64a
body_checksum: 8ef51d2b6712f636af70bbe45862e181aae75ccd1026cf1d2f124b1a6622069b
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Nifty 50 Residual Mean Reversion — Results

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\STATARB_NIFTY50_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/STATARB_NIFTY50_METHODOLOGY.md (pre-registered). Universe (50): ADANIENT, ADANIPORTS, APOLLOHOSP, ASIANPAINT, AXISBANK, BAJAJ-AUTO, BAJAJFINSV, BAJFINANCE, BEL, BHARTIARTL, BSE, CIPLA, COALINDIA, DRREDDY, EICHERMOT, ETERNAL, GRASIM, HCLTECH, HDFCBANK, HDFCLIFE, HINDALCO, HINDUNILVR, ICICIBANK, INDIGO, INFY, ITC, JIOFIN, JSWSTEEL, KOTAKBANK, LT, M&M, MARUTI, MAXHEALTH, NESTLEIND, NTPC, ONGC, POWERGRID, RELIANCE, SBILIFE, SBIN, SHRIRAMFIN, SUNPHARMA, TATACONSUM, TATASTEEL, TCS, TECHM, TITAN, TMPV, TRENT, ULTRACEMCO. Evaluation 2020-02-25 to 2026-10-12. All figures net of the futures cost model + 2 bps/side slippage; % basis = ₹5L stock-leg notional.

## Verdict (PCA5, primary)

**FAIL**

| Check | PCA5 | MKT_SECTOR (info only) |
|---|---|---|
| edge (PF > 1 and Sharpe > 0.5) | FAIL | FAIL |
| PF > 1 first half | FAIL | FAIL |
| PF > 1 second half | FAIL | FAIL |
| PF > 1 exits 2024+ | FAIL | FAIL |
| PF > 1 exits 2025+ | FAIL | FAIL |
| calibration: long bucket > 0 | FAIL | pass |
| calibration: short bucket < 0 | FAIL | FAIL |
| calibration: t > 2 | FAIL | FAIL |

## PCA5

### Trade summary

| Slice | Trades | Win rate | PF | Sharpe | Net % (sum) | Max DD | Avg days |
|---|---|---|---|---|---|---|---|
| All | 2245 | 52.4% | 0.86 | -0.76 | -550.3% | 791.6% | 9.1 |
| First half | 1122 | 52.8% | 0.88 | -0.66 | -264.6% | 560.2% | 9.0 |
| Second half | 1123 | 52.1% | 0.84 | -0.87 | -285.7% | 286.0% | 9.2 |
| Long only | 1074 | 51.8% | 0.96 | -0.14 | -67.5% | 273.4% | 10.1 |
| Short only | 1171 | 53.0% | 0.78 | -0.88 | -482.8% | 631.0% | 8.2 |
| 2020 | 269 | 55.8% | 1.07 | 0.35 | +43.3% | 206.6% | 8.7 |
| 2021 | 325 | 52.9% | 0.69 | -2.04 | -214.2% | 273.1% | 9.0 |
| 2022 | 351 | 51.8% | 0.95 | -0.26 | -26.9% | 126.8% | 9.0 |
| 2023 | 320 | 49.1% | 0.76 | -1.28 | -138.7% | 168.0% | 9.1 |
| 2024 | 335 | 51.9% | 0.77 | -1.52 | -137.2% | 175.6% | 9.6 |
| 2025 | 342 | 55.3% | 1.10 | 0.35 | +48.4% | 156.7% | 9.3 |
| 2026 | 303 | 50.5% | 0.75 | -1.88 | -125.1% | 134.4% | 9.0 |

Gross P&L ₹200,006, costs ₹2,951,571, net ₹-2,751,565. Open positions: average 12.5, max 24.

### Exit reasons

| Reason | Trades | Net P&L |
|---|---|---|
| reverted | 1761 | ₹6,808,239 |
| max_hold | 226 | ₹-6,508,524 |
| pre_results | 208 | ₹-2,233,129 |
| stop | 27 | ₹-476,780 |
| end_of_data | 23 | ₹-341,371 |

### Per sector (info only)

| Sector | Trades | Net P&L | PF |
|---|---|---|---|
| auto | 208 | ₹-518,309 | 0.74 |
| bank | 232 | ₹-125,174 | 0.93 |
| consumer_durables | 51 | ₹267,409 | 2.10 |
| energy | 262 | ₹-526,046 | 0.78 |
| finance | 202 | ₹-178,845 | 0.91 |
| fmcg | 210 | ₹-545,313 | 0.69 |
| health | 196 | ₹-223,231 | 0.86 |
| it | 187 | ₹-91,751 | 0.92 |
| metal | 219 | ₹-561,000 | 0.81 |
| unassigned | 478 | ₹-249,307 | 0.94 |

### Per symbol

| Symbol | Trades | Net P&L | PF |
|---|---|---|---|
| ADANIENT | 54 | ₹-112,318 | 0.90 |
| ADANIPORTS | 55 | ₹-118,719 | 0.82 |
| APOLLOHOSP | 53 | ₹55,984 | 1.14 |
| ASIANPAINT | 62 | ₹-68,510 | 0.85 |
| AXISBANK | 54 | ₹-171,216 | 0.59 |
| BAJAJ-AUTO | 56 | ₹-171,551 | 0.65 |
| BAJAJFINSV | 48 | ₹-413,879 | 0.38 |
| BAJFINANCE | 44 | ₹264,626 | 1.52 |
| BEL | 44 | ₹240,101 | 1.44 |
| BHARTIARTL | 62 | ₹86,138 | 1.23 |
| BSE | 6 | ₹-42,143 | 0.44 |
| CIPLA | 41 | ₹-186,589 | 0.60 |
| COALINDIA | 46 | ₹-232,383 | 0.60 |
| DRREDDY | 46 | ₹-38,349 | 0.88 |
| EICHERMOT | 41 | ₹-48,662 | 0.88 |
| ETERNAL | 7 | ₹-108,877 | 0.18 |
| GRASIM | 58 | ₹-120,770 | 0.75 |
| HCLTECH | 42 | ₹-164,232 | 0.50 |
| HDFCBANK | 37 | ₹-150,426 | 0.66 |
| HDFCLIFE | 49 | ₹29,603 | 1.08 |
| HINDALCO | 64 | ₹-94,709 | 0.83 |
| HINDUNILVR | 47 | ₹-68,075 | 0.80 |
| ICICIBANK | 44 | ₹117,827 | 1.87 |
| INDIGO | 47 | ₹-259,160 | 0.66 |
| INFY | 49 | ₹52,970 | 1.17 |
| ITC | 52 | ₹-241,641 | 0.53 |
| JIOFIN | 4 | ₹-43,798 | 0.34 |
| JSWSTEEL | 64 | ₹-355,559 | 0.56 |
| KOTAKBANK | 42 | ₹7,952 | 1.02 |
| LT | 54 | ₹-71,643 | 0.79 |
| M&M | 48 | ₹-155,223 | 0.67 |
| MARUTI | 63 | ₹-142,873 | 0.77 |
| MAXHEALTH | 7 | ₹3,569 | 1.07 |
| NESTLEIND | 50 | ₹-278,476 | 0.48 |
| NTPC | 50 | ₹-227,768 | 0.50 |
| ONGC | 56 | ₹-118,298 | 0.81 |
| POWERGRID | 55 | ₹141,674 | 1.37 |
| RELIANCE | 55 | ₹-89,269 | 0.78 |
| SBILIFE | 40 | ₹28,586 | 1.11 |
| SBIN | 55 | ₹70,690 | 1.19 |
| SHRIRAMFIN | 11 | ₹-1,839 | 0.97 |
| SUNPHARMA | 49 | ₹-57,847 | 0.85 |
| TATACONSUM | 61 | ₹42,879 | 1.10 |
| TATASTEEL | 37 | ₹1,587 | 1.00 |
| TCS | 49 | ₹-26,797 | 0.87 |
| TECHM | 47 | ₹46,308 | 1.15 |
| TITAN | 51 | ₹267,409 | 2.10 |
| TRENT | 36 | ₹282,290 | 2.31 |
| ULTRACEMCO | 53 | ₹-110,157 | 0.68 |

### Calibration (10-day forward residual return, non-overlapping, tradeable days)

| s bucket | Samples | Mean fwd residual |
|---|---|---|
| s <= -2 | 81 | -0.52% |
| -2 < s <= -1.25 | 651 | -0.05% |
| -1.25 < s < 1.25 | 5329 | -0.04% |
| 1.25 <= s < 2 | 662 | +0.27% |
| s >= 2 | 99 | +0.90% |

Long bucket (s ≤ −1.25): n=732, mean -0.10%. Short bucket (s ≥ +1.25): n=761, mean +0.35%. Welch t = -1.23.

### Stock-days with no s-score (exclusions)

| Reason | Stock-days |
|---|---|
| missing_data | 9352 |
| corp_action_jump | 3015 |
| structural_break | 329 |

## MKT_SECTOR

### Trade summary

| Slice | Trades | Win rate | PF | Sharpe | Net % (sum) | Max DD | Avg days |
|---|---|---|---|---|---|---|---|
| All | 1716 | 56.4% | 0.94 | -0.32 | -167.1% | 330.7% | 9.1 |
| First half | 858 | 57.6% | 0.96 | -0.20 | -58.1% | 260.1% | 9.1 |
| Second half | 858 | 55.1% | 0.91 | -0.48 | -109.0% | 111.0% | 9.1 |
| Long only | 821 | 55.4% | 1.11 | 0.36 | +131.8% | 111.3% | 10.2 |
| Short only | 895 | 57.2% | 0.79 | -0.80 | -299.0% | 395.9% | 8.1 |
| 2020 | 203 | 58.6% | 1.19 | 0.91 | +81.5% | 97.2% | 8.7 |
| 2021 | 255 | 57.2% | 0.87 | -0.68 | -53.6% | 82.2% | 9.3 |
| 2022 | 276 | 56.9% | 0.87 | -0.78 | -60.0% | 122.6% | 9.1 |
| 2023 | 241 | 58.1% | 0.87 | -0.57 | -46.4% | 88.8% | 8.9 |
| 2024 | 267 | 56.9% | 0.94 | -0.33 | -25.4% | 85.9% | 9.1 |
| 2025 | 255 | 54.5% | 0.95 | -0.20 | -14.3% | 65.9% | 9.2 |
| 2026 | 219 | 52.0% | 0.84 | -0.94 | -48.9% | 89.0% | 9.2 |

Gross P&L ₹1,002,456, costs ₹1,838,028, net ₹-835,572. Open positions: average 9.5, max 19.

### Exit reasons

| Reason | Trades | Net P&L |
|---|---|---|
| reverted | 1353 | ₹6,574,944 |
| max_hold | 189 | ₹-5,213,839 |
| pre_results | 144 | ₹-1,604,274 |
| stop | 17 | ₹-302,381 |
| end_of_data | 13 | ₹-290,021 |

### Per sector (info only)

| Sector | Trades | Net P&L | PF |
|---|---|---|---|
| auto | 215 | ₹-141,949 | 0.92 |
| bank | 231 | ₹344,103 | 1.30 |
| energy | 271 | ₹-155,093 | 0.92 |
| finance | 186 | ₹66,608 | 1.05 |
| fmcg | 201 | ₹-464,099 | 0.71 |
| health | 200 | ₹237,975 | 1.18 |
| it | 196 | ₹-4,497 | 1.00 |
| metal | 216 | ₹-718,619 | 0.74 |

### Per symbol

| Symbol | Trades | Net P&L | PF |
|---|---|---|---|
| ADANIENT | 49 | ₹-447,937 | 0.65 |
| APOLLOHOSP | 52 | ₹-107,877 | 0.78 |
| AXISBANK | 43 | ₹-30,259 | 0.88 |
| BAJAJ-AUTO | 56 | ₹-89,425 | 0.83 |
| BAJAJFINSV | 43 | ₹-207,282 | 0.54 |
| BAJFINANCE | 39 | ₹142,252 | 1.50 |
| BSE | 4 | ₹-66,497 | 0.34 |
| CIPLA | 52 | ₹45,446 | 1.12 |
| COALINDIA | 53 | ₹-217,760 | 0.59 |
| DRREDDY | 43 | ₹113,708 | 1.45 |
| EICHERMOT | 47 | ₹31,301 | 1.09 |
| HCLTECH | 39 | ₹-77,204 | 0.68 |
| HDFCBANK | 35 | ₹77,417 | 1.42 |
| HDFCLIFE | 45 | ₹49,524 | 1.14 |
| HINDALCO | 58 | ₹-177,262 | 0.72 |
| HINDUNILVR | 45 | ₹-78,985 | 0.74 |
| ICICIBANK | 56 | ₹221,472 | 3.32 |
| INFY | 50 | ₹-57,264 | 0.82 |
| ITC | 50 | ₹10,059 | 1.03 |
| JIOFIN | 4 | ₹12,394 | 1.31 |
| JSWSTEEL | 63 | ₹-30,204 | 0.94 |
| KOTAKBANK | 51 | ₹134,156 | 1.54 |
| M&M | 51 | ₹106,306 | 1.29 |
| MARUTI | 61 | ₹-190,130 | 0.71 |
| MAXHEALTH | 6 | ₹78,000 | 11.56 |
| NESTLEIND | 43 | ₹-338,962 | 0.36 |
| NTPC | 53 | ₹13,279 | 1.04 |
| ONGC | 56 | ₹-121,535 | 0.75 |
| POWERGRID | 54 | ₹118,819 | 1.31 |
| RELIANCE | 55 | ₹52,104 | 1.17 |
| SBILIFE | 41 | ₹86,029 | 1.53 |
| SBIN | 46 | ₹-58,683 | 0.83 |
| SHRIRAMFIN | 10 | ₹50,188 | 1.84 |
| SUNPHARMA | 47 | ₹108,699 | 1.48 |
| TATACONSUM | 63 | ₹-56,210 | 0.87 |
| TATASTEEL | 46 | ₹-63,217 | 0.82 |
| TCS | 46 | ₹-9,643 | 0.96 |
| TECHM | 61 | ₹139,614 | 1.49 |

### Calibration (10-day forward residual return, non-overlapping, tradeable days)

| s bucket | Samples | Mean fwd residual |
|---|---|---|
| s <= -2 | 56 | +0.95% |
| -2 < s <= -1.25 | 491 | +0.43% |
| -1.25 < s < 1.25 | 4068 | -0.28% |
| 1.25 <= s < 2 | 518 | +0.43% |
| s >= 2 | 81 | +1.13% |

Long bucket (s ≤ −1.25): n=547, mean +0.48%. Short bucket (s ≥ +1.25): n=599, mean +0.53%. Welch t = -0.12.

### Stock-days with no s-score (exclusions)

| Reason | Stock-days |
|---|---|
| no_sector_peers | 16334 |
| missing_data | 9352 |
| corp_action_jump | 3015 |
| structural_break | 329 |

## Disclosed limitations

- Current constituent list applied to the whole history (no point-in-time membership).
- Results blackout uses actual results dates as if known in advance (board-meeting notice is normally given days ahead).
- Every signal taken with no capital limit: this measures the signal, not a portfolio.
- PCA5's hedge spans up to 49 stocks; each trade is costed as ONE futures-equivalent leg of notional N x sum|h| (understates instrument count, ignores netting across the book).
- Results dates from NSE board-meeting dates only (date, no time; meeting day = reaction day).
- Recent listings / demergers (TMPV, BSE, JIOFIN, MAXHEALTH, ...) take part only after 252 days of their own futures history. ZOMATO->ETERNAL and TATAGLOBAL->TATACONSUM spliced as pure renames; SHRIRAMFIN (amalgamation) not spliced.
- The paper's speed filter (1/(-ln b) < 30 days on 60 observations) is weak: the AR(1) slope is biased down on short samples, and about 65% of simulated pure random walks pass it (tests/unit/test_statarb.py). Kept as pre-registered.
