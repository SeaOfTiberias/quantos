# Darvas ATR-stop — out-of-sample 2016-2023

Pre-registered in `scripts/backtest_darvas_atr_stop_oos.py` (committed before this run). Frozen rules; NSE bhavcopy data incl. later-delisted names; liquidity-ranked top-500 universe; Stressed costs.

1048 symbols, 0 errored, 7130 breakout trades (14 still open at data end, marked to market).

| Bucket | Trades | Win rate | PF | Sharpe | Net P&L% | Avg hold | Mean net | Minus EW universe | 90% CI (week bootstrap) |
|---|---|---|---|---|---|---|---|---|---|
| <=35% (control) | 5305 | 49.3% | 1.16 | 1.60 | +3033.3% | 23d | +0.57% | -0.56% | +0.15% .. +0.99% |
| 35-50% | 991 | 47.2% | 1.46 | 1.79 | +2142.6% | 30d | +2.16% | +0.70% | +1.23% .. +3.08% |
| 50-100% | 703 | 44.8% | 1.42 | 1.32 | +1489.3% | 30d | +2.12% | +0.31% | +1.05% .. +3.20% |

## Bucket B verdict

- V1 PF > 1 and Sharpe > 0.5: holds
- V2 beats the equal-weight universe: holds
- V3 bootstrap lower bound > 0: holds

Per year (mean net): 2016: +0.25% (n=68), 2017: +3.34% (n=148), 2018: -4.12% (n=65), 2019: -0.88% (n=98), 2020: +4.20% (n=185), 2021: +4.00% (n=207), 2022: -0.12% (n=131), 2023: +4.45% (n=89)

**PASS -- candidate for small real capital**
