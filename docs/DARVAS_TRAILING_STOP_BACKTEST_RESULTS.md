# Darvas Trailing-Stop Backtest — Results

Methodology: docs/DARVAS_TRAILING_STOP_BACKTEST_METHODOLOGY.md, pre-registered 2026-09-22 before this ran. Single-variable follow-up to docs/DARVAS_BOX_WIDTH_BACKTEST_RESULTS.md -- same universe/window/buckets/costs/split, only the exit rule differs (trailing stop+target, no time-stop, still-open trades marked-to-market and INCLUDED rather than excluded).

648 symbols attempted, 63 errored, 2280 total FRESH BREAKOUT events found (any width, point-in-time-eligible). 14 still open at the fetch window's end, marked-to-market, average unrealized +3.6% (included in the metrics below, not excluded).

Errored symbols (excluded): ABLBL, ACMESOLAR, AEGISVOPAK, AFCONS, AGARWALEYE, ANTHEM, ATHERENERG, BELRISE, CANHLIFE, CPPLUS, EMMVEE, ENRIN, GLS, GROWW, GSPL, GUJGASLTD, HDBFS, HEG, HEXT, HFCL, HYUNDAI, IBREALEST, ICICIAMC, IGIL, IKS, INFIBEAM, ISEC, ITCHOTELS, JAINREC, JBCHEPHARM, JSWCEMENT, JSWDULUX, KENNAMET, KIRLFER, LAXMIMACH, LENSKART, LGEINDIA, MEESHO, MTARTECH, NIVABUPA, NTPCGREEN, ONESOURCE, PEL, PINELABS, PIRAMALFIN, PWL, RAJESHEXPO, RELINFRA, SAGILITY, SAILIFE, STLTECH, SWIGGY, TATACAP, TCNSBRANDS, TENNIND, THELEELA, TMCV, TRAVELFOOD, TV18BRDCST, URBANCO, VENTIVE, VMM, WAAREEENER

## Bucket: <=35% (control)

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 1445 | 33.8% | 0.96 | -0.19 | -163.2% | 13d |
| Mining -- Stressed | 1445 | 33.4% | 0.87 | -0.70 | -597.3% | 13d |
| Holdout -- Clean | 340 | 36.8% | 1.06 | 0.30 | +57.8% | 13d |
| Holdout -- Stressed | 340 | 36.2% | 0.96 | -0.23 | -44.5% | 13d |

## Bucket: 35-50%

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 210 | 30.0% | 1.07 | 0.36 | +65.1% | 16d |
| Mining -- Stressed | 210 | 30.0% | 1.00 | 0.01 | +1.9% | 16d |
| Holdout -- Clean | 67 | 32.8% | 1.38 | 1.42 | +80.8% | 21d |
| Holdout -- Stressed | 67 | 32.8% | 1.27 | 1.07 | +60.5% | 21d |

## Bucket: 50-100%

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 157 | 21.7% | 0.81 | -0.94 | -122.0% | 16d |
| Mining -- Stressed | 157 | 21.0% | 0.75 | -1.31 | -169.0% | 16d |
| Holdout -- Clean | 39 | 28.2% | 1.20 | 0.70 | +28.3% | 18d |
| Holdout -- Stressed | 39 | 28.2% | 1.12 | 0.41 | +16.5% | 18d |

## Verdict

1. Bucket B clears `has_positive_edge` on mining/Stressed: NO
2. Bucket B clears `has_positive_edge` on holdout/Stressed: YES
3. Bucket A (control) does NOT clear `has_positive_edge` on holdout/Stressed: YES

**DOES NOT CLEAR ITS BAR -- trailing the stop/target does not rescue this.**

