# Darvas Box-Width Backtest — Results

Methodology: docs/DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md, pre-registered 2026-09-22 before this ran. Managed trade (real stop/target from analyse_symbol, delivery-style costs, Clean + Stressed), full point-in-time Nifty 500 universe, time-based 80/20 mining/holdout split at 2026-02-15. Stressed gates the verdict.

648 symbols attempted, 63 errored, 2280 total FRESH BREAKOUT events found (any width, point-in-time-eligible), 25 still open at the fetch window's end (excluded from all metrics below).

Errored symbols (excluded): ABLBL, ACMESOLAR, AEGISVOPAK, AFCONS, AGARWALEYE, ANTHEM, ATHERENERG, BELRISE, CANHLIFE, CPPLUS, EMMVEE, ENRIN, GLS, GROWW, GSPL, GUJGASLTD, HDBFS, HEG, HEXT, HFCL, HYUNDAI, IBREALEST, ICICIAMC, IGIL, IKS, INFIBEAM, ISEC, ITCHOTELS, JAINREC, JBCHEPHARM, JSWCEMENT, JSWDULUX, KENNAMET, KIRLFER, LAXMIMACH, LENSKART, LGEINDIA, MEESHO, MTARTECH, NIVABUPA, NTPCGREEN, ONESOURCE, PEL, PINELABS, PIRAMALFIN, PWL, RAJESHEXPO, RELINFRA, SAGILITY, SAILIFE, STLTECH, SWIGGY, TATACAP, TCNSBRANDS, TENNIND, THELEELA, TMCV, TRAVELFOOD, TV18BRDCST, URBANCO, VENTIVE, VMM, WAAREEENER

## Bucket: <=35% (control)

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 1445 | 28.1% | 0.81 | -1.04 | -899.0% | 15d |
| Mining -- Stressed | 1445 | 27.8% | 0.74 | -1.55 | -1332.1% | 15d |
| Holdout -- Clean | 323 | 29.4% | 0.86 | -0.72 | -143.1% | 15d |
| Holdout -- Stressed | 323 | 29.1% | 0.79 | -1.22 | -239.9% | 15d |

## Bucket: 35-50%

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 210 | 19.5% | 0.74 | -1.41 | -244.9% | 20d |
| Mining -- Stressed | 210 | 19.5% | 0.69 | -1.77 | -307.6% | 20d |
| Holdout -- Clean | 63 | 20.6% | 0.93 | -0.44 | -24.4% | 22d |
| Holdout -- Stressed | 63 | 20.6% | 0.86 | -0.78 | -43.3% | 22d |

## Bucket: 50-100%

| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |
|---|---|---|---|---|---|---|
| Mining -- Clean | 157 | 11.5% | 0.52 | -2.91 | -363.0% | 20d |
| Mining -- Stressed | 157 | 11.5% | 0.48 | -3.29 | -409.6% | 20d |
| Holdout -- Clean | 35 | 14.3% | 0.88 | -0.59 | -23.1% | 20d |
| Holdout -- Stressed | 35 | 14.3% | 0.83 | -0.85 | -33.5% | 20d |

## Verdict

1. Bucket B clears `has_positive_edge` on mining/Stressed: NO
2. Bucket B clears `has_positive_edge` on holdout/Stressed: NO
3. Bucket A (control) does NOT clear `has_positive_edge` on holdout/Stressed: YES

**DOES NOT CLEAR ITS BAR -- no dashboard change is warranted.**

