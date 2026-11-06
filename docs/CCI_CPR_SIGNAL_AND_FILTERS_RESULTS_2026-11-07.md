# CCI + monthly CPR signal, and CCI / RSI entry filters: results

Rules: docs/CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md (approved 2026-11-07). Run once.

**Verdicts:** A-long: FAIL; A-short: FAIL; CE baseline × cci: FAIL; CE baseline × rsi: FAIL; PE baseline × cci: FAIL; PE baseline × rsi: FAIL; PE H1 retest × cci: FAIL; PE H1 retest × rsi: FAIL

## Part A: CCI(34)/SMA52 + monthly CPR signal

Top-500 universe by 60-session median traded value, signals 2013-01-01 to 2026-09-22, entry at the next open. Returns are % per trade, minus the equal-weighted universe over the same window (sign flipped for shorts), after 0.25% cost.

| side | n | mean | 95% CI | p | Holm | H1 | H2 | vs CCI alone | its 95% CI | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| long | 11,934 | -0.02% | -0.20 to +0.16 | 0.808 | fail | -0.10% | +0.06% | +0.21 pp | +0.05 to +0.38 | FAIL |
| short | 9,831 | +0.16% | +0.00 to +0.33 | 0.049 | fail | +0.19% | +0.13% | +0.48 pp | +0.31 to +0.64 | FAIL |

- **long** failed: mean >= +0.50%, Holm, both halves > 0, beats CCI alone by >= 0.30 pp, CI > 0.
- **short** failed: mean >= +0.50%, Holm.

### Comparison arms and horizons (reported only)

| arm | side | horizon | n | mean | win | H1 | H2 |
|---|---|---|---|---|---|---|---|
| full | long | 5 | 11,938 | -0.04% | 44% | -0.10% | +0.02% |
| full | long | 10 | 11,934 | -0.02% | 46% | -0.10% | +0.06% |
| full | long | 20 | 11,931 | +0.20% | 46% | +0.19% | +0.21% |
| full | short | 5 | 9,835 | -0.08% | 51% | -0.13% | -0.03% |
| full | short | 10 | 9,831 | +0.16% | 54% | +0.19% | +0.13% |
| full | short | 20 | 9,830 | +0.31% | 54% | +0.48% | +0.14% |
| cci_only | long | 5 | 53,071 | -0.28% | 42% | -0.32% | -0.23% |
| cci_only | long | 10 | 53,062 | -0.23% | 43% | -0.30% | -0.16% |
| cci_only | long | 20 | 53,041 | -0.19% | 44% | -0.30% | -0.08% |
| cci_only | short | 5 | 53,480 | -0.28% | 51% | -0.24% | -0.31% |
| cci_only | short | 10 | 53,472 | -0.31% | 52% | -0.28% | -0.35% |
| cci_only | short | 20 | 53,456 | -0.37% | 52% | -0.34% | -0.40% |
| no_slope | long | 5 | 22,345 | -0.08% | 44% | -0.13% | -0.04% |
| no_slope | long | 10 | 22,340 | +0.01% | 45% | -0.02% | +0.04% |
| no_slope | long | 20 | 22,336 | +0.18% | 46% | +0.18% | +0.17% |
| no_slope | short | 5 | 17,197 | -0.10% | 51% | -0.09% | -0.10% |
| no_slope | short | 10 | 17,192 | +0.04% | 53% | +0.04% | +0.03% |
| no_slope | short | 20 | 17,189 | +0.09% | 54% | +0.19% | -0.02% |
| no_cpr | long | 5 | 29,757 | -0.19% | 43% | -0.20% | -0.19% |
| no_cpr | long | 10 | 29,752 | -0.17% | 44% | -0.18% | -0.15% |
| no_cpr | long | 20 | 29,741 | -0.07% | 45% | -0.12% | -0.03% |
| no_cpr | short | 5 | 30,941 | -0.25% | 51% | -0.16% | -0.33% |
| no_cpr | short | 10 | 30,934 | -0.20% | 52% | -0.07% | -0.34% |
| no_cpr | short | 20 | 30,923 | -0.17% | 53% | -0.01% | -0.33% |

### By year (full rule, 10 sessions)

| group | side | n | mean | win | H1 | H2 |
|---|---|---|---|---|---|---|
| 2013 | long | 804 | -0.16% | 48% | +0.15% | -0.46% |
| 2013 | short | 809 | +0.06% | 48% | -0.13% | +0.25% |
| 2014 | long | 958 | -0.05% | 46% | +0.13% | -0.23% |
| 2014 | short | 651 | +0.45% | 56% | +0.31% | +0.58% |
| 2015 | long | 937 | +0.00% | 44% | +0.27% | -0.26% |
| 2015 | short | 867 | +0.05% | 54% | +0.13% | -0.03% |
| 2016 | long | 811 | -0.27% | 45% | -0.36% | -0.19% |
| 2016 | short | 714 | -0.16% | 54% | -0.85% | +0.53% |
| 2017 | long | 1,019 | +0.01% | 45% | -0.16% | +0.18% |
| 2017 | short | 607 | +0.64% | 60% | +0.42% | +0.83% |
| 2018 | long | 508 | +0.23% | 52% | +0.24% | +0.21% |
| 2018 | short | 778 | -0.19% | 52% | +0.02% | -0.40% |
| 2019 | long | 788 | -0.49% | 45% | -0.33% | -0.65% |
| 2019 | short | 807 | +0.67% | 51% | +1.21% | +0.14% |
| 2020 | long | 930 | -0.13% | 43% | +0.02% | -0.28% |
| 2020 | short | 568 | +0.66% | 58% | +0.83% | +0.50% |
| 2021 | long | 912 | +0.47% | 44% | +0.02% | +0.89% |
| 2021 | short | 522 | +0.28% | 58% | +0.67% | -0.09% |
| 2022 | long | 747 | +0.05% | 46% | +0.17% | -0.07% |
| 2022 | short | 709 | -0.07% | 52% | -0.29% | +0.14% |
| 2023 | long | 1,009 | -0.08% | 44% | -0.07% | -0.09% |
| 2023 | short | 553 | -0.07% | 56% | -0.26% | +0.12% |
| 2024 | long | 952 | +0.07% | 47% | +0.12% | +0.02% |
| 2024 | short | 843 | +0.32% | 57% | +0.50% | +0.13% |
| 2025 | long | 881 | -0.16% | 47% | +0.27% | -0.59% |
| 2025 | short | 770 | -0.74% | 46% | -0.95% | -0.53% |
| 2026 | long | 678 | +0.34% | 48% | +0.47% | +0.21% |
| 2026 | short | 633 | +0.66% | 56% | +0.97% | +0.35% |

### By Weinstein stage (proxy: 150-day SMA and its slope) (full rule, 10 sessions)

| group | side | n | mean | win | H1 | H2 |
|---|---|---|---|---|---|---|
| 1/3 (mixed) | long | 2,191 | -0.38% | 43% | -0.57% | -0.19% |
| 1/3 (mixed) | short | 2,566 | -0.21% | 52% | -0.27% | -0.14% |
| 2 (above, rising) | long | 7,521 | +0.09% | 46% | +0.14% | +0.03% |
| 2 (above, rising) | short | 3,447 | +0.05% | 54% | +0.04% | +0.06% |
| 4 (below, falling) | long | 2,056 | -0.11% | 45% | -0.61% | +0.39% |
| 4 (below, falling) | short | 3,677 | +0.50% | 55% | +0.59% | +0.42% |
| n/a | long | 166 | +1.02% | 47% | +0.76% | +1.29% |
| n/a | short | 141 | +0.69% | 57% | +0.41% | +0.96% |

### By where the previous close sat against the monthly CPR (full rule, 10 sessions)

| group | side | n | mean | win | H1 | H2 |
|---|---|---|---|---|---|---|
| above | long | 10,198 | +0.01% | 46% | -0.07% | +0.09% |
| above | short | 500 | +0.67% | 57% | +0.78% | +0.55% |
| below | long | 593 | -0.20% | 44% | -0.31% | -0.10% |
| below | short | 8,464 | +0.14% | 54% | +0.20% | +0.09% |
| inside | long | 1,143 | -0.19% | 45% | -0.37% | -0.02% |
| inside | short | 867 | +0.05% | 52% | -0.27% | +0.36% |

### By ATR% tercile (full rule, 10 sessions)

| group | side | n | mean | win | H1 | H2 |
|---|---|---|---|---|---|---|
| low | long | 4,170 | -0.07% | 48% | +0.13% | -0.26% |
| low | short | 3,086 | -0.14% | 51% | -0.32% | +0.04% |
| mid | long | 4,138 | +0.03% | 45% | +0.07% | -0.02% |
| mid | short | 3,118 | +0.09% | 55% | +0.08% | +0.09% |
| high | long | 3,626 | -0.02% | 44% | -0.56% | +0.51% |
| high | short | 3,627 | +0.48% | 55% | +0.47% | +0.50% |

### Shorts: stocks on the current F&O list (survivorship-biased) (full rule, 10 sessions)

| group | side | n | mean | win | H1 | H2 |
|---|---|---|---|---|---|---|
| False | short | 6,440 | +0.44% | 56% | +0.49% | +0.38% |
| True | short | 3,391 | -0.36% | 50% | -0.60% | -0.13% |

84 signals had no 10-session outcome (no bar on the entry or exit day) and are left out.

## Part B: CCI and RSI as entry filters

F&O screener backtest trades, one per breakout episode; halves split at 2026-03-27; 0 signal rows skipped for indicator warm-up. % per trade after 0.1% cost.

### CE baseline

| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|
| unfiltered | 2310 | 273 | -0.11% | 58% | -1.2 | -0.11% | -0.11% |  |
| cci: kept | 103 | 77 | -0.06% | 59% | -0.2 | -0.12% | +0.02% | FAIL |
| cci: blocked (96%) | 2207 | 272 | -0.11% | 58% | -1.5 | -0.11% | -0.11% |  |
| cci: kept − blocked | +0.05 pp | | | | | | | failed: kept > 0 both halves, t >= 2.7, beats unfiltered both halves, blocked worse by >= 0.30 pp |
| rsi: kept | 439 | 205 | -0.06% | 59% | +0.8 | -0.15% | +0.06% | FAIL |
| rsi: blocked (81%) | 1871 | 264 | -0.12% | 58% | -2.0 | -0.10% | -0.15% |  |
| rsi: kept − blocked | +0.06 pp | | | | | | | failed: kept > 0 both halves, t >= 2.7, beats unfiltered both halves, blocked worse by >= 0.30 pp |

### PE baseline

| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|
| unfiltered | 2646 | 275 | +0.23% | 67% | +2.6 | +0.40% | +0.03% |  |
| cci: kept | 117 | 86 | +0.14% | 67% | +0.6 | +0.12% | +0.16% | FAIL |
| cci: blocked (96%) | 2529 | 270 | +0.24% | 67% | +2.4 | +0.41% | +0.03% |  |
| cci: kept − blocked | -0.10 pp | | | | | | | failed: t >= 2.7, beats unfiltered both halves, blocked worse by >= 0.30 pp |
| rsi: kept | 489 | 225 | +0.20% | 67% | +1.0 | +0.32% | +0.09% | FAIL |
| rsi: blocked (82%) | 2157 | 254 | +0.24% | 67% | +3.0 | +0.42% | +0.02% |  |
| rsi: kept − blocked | -0.04 pp | | | | | | | failed: t >= 2.7, beats unfiltered both halves, blocked worse by >= 0.30 pp |

### PE H1 retest

| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|
| unfiltered | 1672 | 269 | +0.34% | 69% | +3.7 | +0.41% | +0.25% |  |
| cci: kept | 98 | 78 | +0.20% | 66% | +0.6 | -0.28% | +0.62% | FAIL |
| cci: blocked (94%) | 1574 | 259 | +0.34% | 70% | +3.9 | +0.44% | +0.23% |  |
| cci: kept − blocked | -0.14 pp | | | | | | | failed: kept n >= 100, kept > 0 both halves, t >= 2.7, beats unfiltered both halves, blocked worse by >= 0.30 pp |
| rsi: kept | 414 | 213 | +0.35% | 70% | +2.4 | +0.41% | +0.29% | FAIL |
| rsi: blocked (75%) | 1258 | 239 | +0.33% | 69% | +3.9 | +0.41% | +0.24% |  |
| rsi: kept − blocked | +0.02 pp | | | | | | | failed: t >= 2.7, blocked worse by >= 0.30 pp |

