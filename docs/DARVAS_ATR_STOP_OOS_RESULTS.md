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

## Post-run scrutiny (2026-10-05, NOT part of the pre-registered verdict)

- The first version of this report printed Sharpe 92.8 / 69.0 / 3.36: core/backtest/parser.py assumed
  trades arrive in date order, but these are listed by symbol, so the span collapsed. Fixed the same day
  (42ecd16: order-independent span and drawdown); the table above uses the fix. Still overstated in one
  respect: overlapping trades are not independent. The fix moves the IN-SAMPLE Bucket B Sharpe from
  0.68 -> 0.55 (mining) and 0.62 -> 0.63 (holdout): the original pass still holds, mining now only just.
- Most of the raw return is the market: the equal-weight universe returned 14.7%/yr. Bucket B's EXCESS
  over it is +0.70%/trade, week-bootstrap 90% CI **+0.03% .. +1.36%** -- above zero, but only just.
- Excess by entry year: 2016 -0.05%, 2017 +1.87%, 2018 -0.58%, 2019 +0.47%, 2020 +0.93%, 2021 +0.74%,
  2022 +0.66%, 2023 +0.05% (positive in 6 of 8 years).
- Concentration: total net +2143%; without the top 5% of trades still +665%.
- Raw losing years: 2018 -4.12%/trade, 2019 -0.88%, 2022 -0.12% -- expect drawdowns when mid/small caps fall.

## Correction (2026-11-28, Lab verification): the PASS rests on impossible stop fills

This report regenerates exactly from its code and data (67de055). But the exit simulation (`_simulate_exit_atr`, shared with the in-sample backtest) fills every stop at the stop price whenever the day's low reaches it, even when the stock opened below the stop. A trailed stop (new box ceiling − 2 × ATR) often lands **above** the current price, so the next bar "hits" it at a price that never traded. 1,857 of the 7,130 trades exit this way; for 1,330 of them the fill is above that day's high.

This was first found on 2026-10-24 (`docs/DARVAS_CUES_PREREG_2026-10-23.md`, "Why the baseline fell from +2.16% to +0.38%"), but was not carried into this report, the Lab or the go/no-go.

Same trades, same costs, scored by this script's own `summarize`, with a stop above the exit day's open filled at the open (what a live stop above the market gets): `scripts/research/gap_fill_check/atr_stop_oos.py`.

| Bucket B (35-50%) | Published | Stop filled at the open on a gap |
|---|---|---|
| Win rate | 47.2% | 39.5% |
| PF / Sharpe | 1.46 / 1.79 | 1.09 / 0.39 |
| Mean net per trade | +2.16% | +0.48% |
| Minus EW universe | +0.70% | −0.98% |
| 90% CI (week bootstrap) | +1.23% .. +3.08% | −0.47% .. +1.43% |
| V1 / V2 / V3 | holds / holds / holds | **fails / fails / fails** |

Under realistic fills the pre-registered verdict is **FAIL**. The in-sample 2024-26 Bucket B trades move the same way: PF 1.15 → 0.82, mean net +0.70% → −0.97% (`scripts/research/gap_fill_check/atr_stop_bucket_b_l1.py`, 274 of 277 checked against NSE prices).
