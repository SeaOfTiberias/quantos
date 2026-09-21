# ORB Options Scalping — Net Profit by Arm Bucket (Candidate 18)

MEASUREMENT ONLY, same discipline as docs/ORB_ARM_GIVEBACK_ANALYSIS.md and docs/ORB_ARM_THRESHOLD_METHODOLOGY.md: no parameter changed, no new backtest variant. Answers whether the strategy's real, Stratified-cost-adjusted edge is concentrated in the ARMED bucket (trades reaching a full range-width move) or shared across all three buckets.

## NIFTY

All 1049 trades: PF 1.23, Sharpe 0.91, total net profit +331,578 (arbitrary premium units x lot size, same convention as docs/ORB_SCALPING_RESULTS.md).

| Bucket | Trades | Share of trades | Net profit | Share of total net profit | Bucket's own PF/Sharpe |
|---|---|---|---|---|---|
| armed at some point | 378 | 36.0% | +1,142,898 | +345% | 378 trades, PF 60.87, Sharpe 12.88 |
| never-armed, rode to flatten | 305 | 29.1% | -56,726 | -17% | 305 trades, PF 0.67, Sharpe -1.87 |
| never-armed, stopped out | 366 | 34.9% | -754,594 | -228% | 366 trades, PF 0.00, Sharpe -65.36 |

**Non-armed trades alone** (never-armed-flatten + never-armed-stopped, 671 trades): net profit -811,320, PF 0.16, Sharpe -10.07 -- this subset alone does NOT clear the PF>1/Sharpe>0.5 bar on its own.

## BANKNIFTY

All 1280 trades: PF 1.16, Sharpe 0.95, total net profit +425,196 (arbitrary premium units x lot size, same convention as docs/ORB_SCALPING_RESULTS.md).

| Bucket | Trades | Share of trades | Net profit | Share of total net profit | Bucket's own PF/Sharpe |
|---|---|---|---|---|---|
| armed at some point | 413 | 32.3% | +1,745,135 | +410% | 413 trades, PF 72.90, Sharpe 10.87 |
| never-armed, rode to flatten | 453 | 35.4% | -99,610 | -23% | 453 trades, PF 0.67, Sharpe -2.66 |
| never-armed, stopped out | 414 | 32.3% | -1,220,329 | -287% | 414 trades, PF 0.00, Sharpe -50.29 |

**Non-armed trades alone** (never-armed-flatten + never-armed-stopped, 867 trades): net profit -1,319,939, PF 0.18, Sharpe -9.50 -- this subset alone does NOT clear the PF>1/Sharpe>0.5 bar on its own.

