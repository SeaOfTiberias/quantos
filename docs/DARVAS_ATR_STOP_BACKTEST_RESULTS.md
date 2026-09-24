# Darvas ATR-Scaled Stop Backtest — Results

Methodology: docs/DARVAS_ATR_STOP_BACKTEST_METHODOLOGY.md, pre-registered 2026-09-23 before this ran. Third link in the chain: box-width (static exit) -> trailing stop/target -> this run (same trailing logic, stop buffer is 2.0x ATR(14) instead of a fixed 2% below the ceiling; target unchanged).

648 symbols attempted, 63 errored, 2280 total FRESH BREAKOUT events found (any width, point-in-time-eligible). 30 still open at the fetch window's end, marked-to-market, average unrealized +2.9% (included in the metrics below, not excluded).

Errored symbols (excluded): ABLBL, ACMESOLAR, AEGISVOPAK, AFCONS, AGARWALEYE, ANTHEM, ATHERENERG, BELRISE, CANHLIFE, CPPLUS, EMMVEE, ENRIN, GLS, GROWW, GSPL, GUJGASLTD, HDBFS, HEG, HEXT, HFCL, HYUNDAI, IBREALEST, ICICIAMC, IGIL, IKS, INFIBEAM, ISEC, ITCHOTELS, JAINREC, JBCHEPHARM, JSWCEMENT, JSWDULUX, KENNAMET, KIRLFER, LAXMIMACH, LENSKART, LGEINDIA, MEESHO, MTARTECH, NIVABUPA, NTPCGREEN, ONESOURCE, PEL, PINELABS, PIRAMALFIN, PWL, RAJESHEXPO, RELINFRA, SAGILITY, SAILIFE, STLTECH, SWIGGY, TATACAP, TCNSBRANDS, TENNIND, THELEELA, TMCV, TRAVELFOOD, TV18BRDCST, URBANCO, VENTIVE, VMM, WAAREEENER

## Bucket: <=35% (control)

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 1445 | 43.7% | 0.99 | -0.05 | -50.3% | 23d |
| Mining -- Stressed | 1445 | 42.8% | 0.92 | -0.45 | -484.6% | 23d |
| Holdout -- Clean | 340 | 43.5% | 1.15 | 0.66 | +162.1% | 23d |
| Holdout -- Stressed | 340 | 41.5% | 1.05 | 0.24 | +59.6% | 23d |

## Bucket: 35-50%

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 210 | 45.2% | 1.22 | 0.96 | +218.7% | 30d |
| Mining -- Stressed | 210 | 43.8% | 1.15 | 0.68 | +155.2% | 30d |
| Holdout -- Clean | 67 | 46.3% | 1.25 | 0.95 | +57.8% | 33d |
| Holdout -- Stressed | 67 | 43.3% | 1.16 | 0.62 | +37.6% | 33d |

## Bucket: 50-100%

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 157 | 40.8% | 1.02 | 0.12 | +19.4% | 29d |
| Mining -- Stressed | 157 | 40.8% | 0.96 | -0.17 | -27.8% | 29d |
| Holdout -- Clean | 39 | 43.6% | 1.49 | 1.74 | +91.4% | 31d |
| Holdout -- Stressed | 39 | 41.0% | 1.41 | 1.51 | +79.5% | 31d |

## Verdict

1. Bucket B clears `has_positive_edge` on mining/Stressed: YES
2. Bucket B clears `has_positive_edge` on holdout/Stressed: YES
3. Bucket A (control) does NOT clear `has_positive_edge` on holdout/Stressed: YES

**CLEARS ITS BAR -- ATR-scaled stop recovers the edge trailing alone didn't.**

**Verified settled 2026-09-24, after fixing a real bug Fable's review found** (the
target-trail update wasn't properly gated by whether the ATR stop actually
improved, `scripts/backtest_darvas_atr_stop.py` commit `cf870c6`). Re-ran the
full 648-symbol backtest with the fix and diffed every one of the 2280
trades (all 277 in Bucket B specifically) against the pre-fix run:
**zero trades changed exit price or exit reason.** The bug was real, but the
scenario it could have affected never actually altered an outcome in this
dataset -- the numbers above are unchanged and were never contaminated by
it. Fable's separate statistical caution (mining vs. holdout Sharpe moving
in opposite directions when trailing switched to ATR-scaling, both landing
just above the 0.5 bar -- consistent with two noisy estimates regressing
toward a threshold, not a uniformly stronger mechanism) is untouched by
this verification and still applies: read this as "real enough for a
discretionary panel, not yet proven for capital," not as a fully
settled edge.

