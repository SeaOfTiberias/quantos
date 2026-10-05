# Darvas ATR-stop — out-of-sample 2016-2023

Pre-registered in `scripts/backtest_darvas_atr_stop_oos.py` (committed before this run). Frozen rules; NSE bhavcopy data incl. later-delisted names; liquidity-ranked top-500 universe; Stressed costs.

1048 symbols, 0 errored, 7130 breakout trades (14 still open at data end, marked to market).

| Bucket | Trades | Win rate | PF | Sharpe | Net P&L% | Avg hold | Mean net | Minus EW universe | 90% CI (week bootstrap) |
|---|---|---|---|---|---|---|---|---|---|
| <=35% (control) | 5305 | 49.3% | 1.16 | 3.36 | +3033.3% | 23d | +0.57% | -0.56% | +0.15% .. +0.99% |
| 35-50% | 991 | 47.2% | 1.46 | 92.84 | +2142.6% | 30d | +2.16% | +0.70% | +1.23% .. +3.08% |
| 50-100% | 703 | 44.8% | 1.42 | 69.00 | +1489.3% | 30d | +2.12% | +0.31% | +1.05% .. +3.20% |

## Bucket B verdict

- V1 PF > 1 and Sharpe > 0.5: holds
- V2 beats the equal-weight universe: holds
- V3 bootstrap lower bound > 0: holds

Per year (mean net): 2016: +0.25% (n=68), 2017: +3.34% (n=148), 2018: -4.12% (n=65), 2019: -0.88% (n=98), 2020: +4.20% (n=185), 2021: +4.00% (n=207), 2022: -0.12% (n=131), 2023: +4.45% (n=89)

**PASS -- candidate for small real capital**

## Post-run scrutiny (2026-10-05, NOT part of the pre-registered verdict)

- The Sharpe column is wrong (92.8 / 69.0 / 3.36): core/backtest/parser.py derives trades/year from the
  date span and over-annualises here. A plain estimate for Bucket B: mean/sd of per-trade net x sqrt(137
  trades/yr) = **1.81** (overstated too, since overlapping trades are not independent). V1 holds on PF 1.46 alone.
- Most of the raw return is the market: the equal-weight universe returned 14.7%/yr. Bucket B's EXCESS
  over it is +0.70%/trade, week-bootstrap 90% CI **+0.03% .. +1.36%** -- above zero, but only just.
- Excess by entry year: 2016 -0.05%, 2017 +1.87%, 2018 -0.58%, 2019 +0.47%, 2020 +0.93%, 2021 +0.74%,
  2022 +0.66%, 2023 +0.05% (positive in 6 of 8 years).
- Concentration: total net +2143%; without the top 5% of trades still +665%.
- Raw losing years: 2018 -4.12%/trade, 2019 -0.88%, 2022 -0.12% -- expect drawdowns when mid/small caps fall.
