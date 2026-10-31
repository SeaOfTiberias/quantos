# Techno-Funda momentum: signal-count feasibility

Run 2026-11-01 by `scripts/count_techno_funda_signals.py` (read its docstring for the rules, written before the run). Counts only, no returns. Window: 2018-01-01 .. 2026-10-23.

These are CEILINGS: the fundamental filters (Piotroski >= 8, profit growth > 15%, OPM > 15%) and the true Rs 20,000 Cr cap are not applied yet.

Liquid universe (50-day mean traded value > Rs 50 lakh): median 1289 stocks a day.

## How often each price filter passes (liquid stock-days)

| filter | pass rate |
|---|---|
| T1 close > 0.85 x ATH | 22.5% |
| T2 50 < RSI14 < 65 | 36.7% |
| T3 green day | 46.8% |
| T4 volume > SMA5 | 38.3% |
| T1 and T2 | 11.4% |
| all four | 2.73% |

## Stocks passing all four filters on a day: all liquid stocks

| year | median | p10 | p90 | days >=1 | days >=10 | days >=15 |
|---|---|---|---|---|---|---|
| 2018 | 22 | 6 | 48 | 99% | 83% | 72% |
| 2019 | 14 | 7 | 24 | 100% | 75% | 50% |
| 2020 | 12 | 3 | 26 | 96% | 58% | 42% |
| 2021 | 39 | 18 | 64 | 100% | 99% | 96% |
| 2022 | 28 | 11 | 52 | 100% | 92% | 83% |
| 2023 | 42 | 23 | 80 | 100% | 99% | 98% |
| 2024 | 69 | 32 | 106 | 100% | 99% | 98% |
| 2025 | 31 | 13 | 50 | 100% | 94% | 85% |
| 2026 | 34 | 12 | 63 | 100% | 95% | 88% |
| **all** | 29 | 8 | 69 | 99% | 88% | 79% |

## Same, excluding the top 200 by traded value (rough large-cap proxy)

| year | median | p10 | p90 | days >=1 | days >=10 | days >=15 |
|---|---|---|---|---|---|---|
| 2018 | 14 | 4 | 34 | 98% | 70% | 47% |
| 2019 | 9 | 4 | 15 | 100% | 42% | 12% |
| 2020 | 6 | 1 | 15 | 92% | 31% | 11% |
| 2021 | 28 | 13 | 50 | 100% | 97% | 86% |
| 2022 | 22 | 9 | 37 | 100% | 89% | 76% |
| 2023 | 34 | 18 | 66 | 100% | 98% | 95% |
| 2024 | 55 | 26 | 89 | 100% | 98% | 96% |
| 2025 | 24 | 9 | 41 | 100% | 88% | 78% |
| 2026 | 27 | 10 | 49 | 100% | 90% | 82% |
| **all** | 21 | 5 | 55 | 99% | 78% | 64% |

## Distinct stocks passing on at least one day of the week

| universe | median | p10 | weeks >=10 | weeks >=15 |
|---|---|---|---|---|
| all liquid | 109 | 39 | 99% | 99% |
| ex-top-200 | 82 | 23 | 98% | 96% |
