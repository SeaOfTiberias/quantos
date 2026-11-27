# Desk edge E3, phase 1: overnight vs intraday in NIFTY / BANKNIFTY futures — results (2026-11-27)

Pre-registration `docs/E3_OVERNIGHT_PREREG_2026-11-27.md` (0169450, signed off before any return was computed). Code `scripts/measure_overnight_futures.py` + `core/fno/bhavcopy_futures.py` (ae333f8). Run once on 2026-11-27.

## Verdict: DEAD for both indices. E3 closes.

| Index | Nights | Gross overnight (bps/night) | Cost at 2026 rates + 3 bps slip | Net | t | Both halves > 0 |
|---|---|---|---|---|---|---|
| NIFTY | 1,908 | +2.00 | 9.09 | **−7.09** | −4.69 | no (−6.89 / −7.30) |
| BANKNIFTY | 1,906 | +2.78 | 9.08 | **−6.30** | −3.47 | no (−5.21 / −7.39) |

The overnight premium exists but is small: about 2-3 bps a night gross, and most of the index's daily drift does accrue overnight (intraday gross is +0.5 to +0.9 bps). The cost of one futures round trip is 3-4 times larger. Even at each night's own historical rates (cost ~5.8 bps) the net is negative (NIFTY −3.80, t −2.51; BANKNIFTY −3.01). Measured from the last trade instead of the 30-minute VWAP close (2024 on), the gross falls to ~0.1-0.3 bps. Per the pre-registration, nothing is re-tuned (no other contract, cost, slippage, window or filter).

Not a result, noted for the record only: the futures price also carries the cost-of-carry premium over spot, which decays toward expiry, so part of any overnight move on futures is carry, not market return. It doesn't change the verdict: the gross is below the cost either way.

## Full output

Window 2019-02-11 to 2026-11-27. Costs: charges at 2026 rates (STT 0.05% sell side) plus 3 bps slippage per round trip, on every night (the verdict).

## NIFTY: phase 1 DEAD

### Overnight (buy at close, sell next open), verdict costs

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| all | 1908 | +2.00 | 9.09 | -7.09 | -4.69 | 45.2% |
| 2019-02-11 to 2022-12-31 | 956 | +2.22 | 9.10 | -6.89 | -2.61 | 49.0% |
| 2023-01-01 on | 952 | +1.77 | 9.07 | -7.30 | -4.96 | 41.4% |

### Reported, not scored

Overnight net at each night's own historical rates:

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| all (rates of the day) | 1908 | +2.00 | 5.80 | -3.80 | -2.51 | 49.7% |

By year (verdict costs):

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| 2019 | 214 | +0.53 | 9.10 | -8.58 | -3.12 | 38.8% |
| 2020 | 248 | +2.49 | 9.10 | -6.61 | -0.79 | 55.6% |
| 2021 | 246 | +7.38 | 9.10 | -1.73 | -0.57 | 53.3% |
| 2022 | 248 | -1.72 | 9.10 | -10.83 | -2.46 | 46.8% |
| 2023 | 243 | +4.44 | 9.10 | -4.67 | -2.50 | 46.1% |
| 2024 | 243 | +3.00 | 9.30 | -6.31 | -2.38 | 43.2% |
| 2025 | 247 | +1.61 | 8.93 | -7.32 | -2.91 | 36.8% |
| 2026 | 219 | -2.35 | 8.93 | -11.29 | -2.52 | 39.3% |

Weekend/holiday nights vs one-night gaps (verdict costs):

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| one night | 1451 | +2.98 | 9.09 | -6.11 | -4.10 | 44.5% |
| weekend/holiday | 457 | -1.12 | 9.09 | -10.21 | -2.45 | 47.3% |

Intraday mirror (buy at open, sell at close), verdict costs:

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| all | 1908 | +0.92 | 9.09 | -8.17 | -4.08 | 46.3% |

Overnight from the last trade instead of the 30-minute VWAP close (2024 on, newer files only):

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| 2024-01-01 on | 709 | +0.10 | 9.06 | -8.96 | -4.83 | 38.4% |

## BANKNIFTY: phase 1 DEAD

### Overnight (buy at close, sell next open), verdict costs

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| all | 1906 | +2.78 | 9.08 | -6.30 | -3.47 | 45.0% |
| 2019-02-11 to 2022-12-31 | 956 | +3.89 | 9.10 | -5.21 | -1.61 | 49.9% |
| 2023-01-01 on | 950 | +1.66 | 9.05 | -7.39 | -4.62 | 40.0% |

### Reported, not scored

Overnight net at each night's own historical rates:

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| all (rates of the day) | 1906 | +2.78 | 5.79 | -3.01 | -1.66 | 48.6% |

By year (verdict costs):

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| 2019 | 214 | +7.01 | 9.10 | -2.09 | -0.62 | 46.7% |
| 2020 | 248 | +5.38 | 9.10 | -3.73 | -0.38 | 50.4% |
| 2021 | 246 | +4.44 | 9.10 | -4.66 | -1.02 | 51.6% |
| 2022 | 248 | -0.84 | 9.10 | -9.94 | -1.81 | 50.4% |
| 2023 | 243 | +3.86 | 9.10 | -5.24 | -2.23 | 44.0% |
| 2024 | 242 | +1.22 | 9.26 | -8.05 | -2.70 | 43.0% |
| 2025 | 246 | +1.71 | 8.93 | -7.21 | -2.84 | 34.6% |
| 2026 | 219 | -0.34 | 8.91 | -9.25 | -1.95 | 38.4% |

Weekend/holiday nights vs one-night gaps (verdict costs):

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| one night | 1449 | +2.99 | 9.08 | -6.09 | -3.32 | 43.7% |
| weekend/holiday | 457 | +2.11 | 9.08 | -6.97 | -1.44 | 49.0% |

Intraday mirror (buy at open, sell at close), verdict costs:

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| all | 1906 | +0.54 | 9.08 | -8.54 | -3.07 | 45.8% |

Overnight from the last trade instead of the 30-minute VWAP close (2024 on, newer files only):

| Slice | Nights | Gross mean (bps) | Cost (bps) | Net mean (bps) | t (net) | Net > 0 |
|---|---|---|---|---|---|---|
| 2024-01-01 on | 707 | +0.29 | 9.04 | -8.74 | -4.44 | 38.5% |

