# ORB Options Scalping — Arm-Threshold Give-Back Analysis (Candidate 18)

MEASUREMENT ONLY. See this script's own module docstring: the signal (core/orb_scalping/signal.py) is untouched, no parameter changed, no new backtest variant. Prompted by a real 2026-09-21 live paper trade (BankNifty, +143pt intraday rally, never armed, gave it all back by the 15:20 flatten) -- this asks how common that shape is across the full historical sample already behind the pre-registered verdict.

NIFTY window: 2022-06-01 to 2026-09-21 (1049 trades). BankNifty window: 2021-06-01 to 2026-09-21 (1280 trades).

## NIFTY

1049 trades total.

| Bucket | Trades | Share | Mean/median MFE (pts) | Mean/median given back (pts) |
|---|---|---|---|---|
| armed at some point | 378 | 36.0% | mean +116.9, median +97.1 | mean +31.7, median +25.8 |
| never-armed, rode to flatten | 305 | 29.1% | mean +52.8, median +46.8 | mean +49.5, median +38.7 |
| never-armed, stopped out | 366 | 34.9% | mean +23.2, median +13.7 | mean +109.1, median +93.7 |

**The exact shape 2026-09-21's live BankNifty trade showed** — never armed, rode to the 15:20 flatten: 305 of 1049 trades (29.1%).

- Given back: mean +49.5, median +38.7 points.
- Kept 6% of total peak profit in aggregate (per-trade median 17% — no per-trade mean reported, see this function's docstring for why that statistic is meaningless here).
- 146 of 305 (48%) closed net NEGATIVE despite having been in profit intraday.
- Total points given back across this bucket: +15102.8 (vs. total MFE across the same bucket: +16115.9).

**Contrast — trades that DID arm**: Kept 73% of total peak profit in aggregate (per-trade median 74% — no per-trade mean reported, see this function's docstring for why that statistic is meaningless here).

## BankNifty

1280 trades total.

| Bucket | Trades | Share | Mean/median MFE (pts) | Mean/median given back (pts) |
|---|---|---|---|---|
| armed at some point | 413 | 32.3% | mean +353.5, median +313.3 | mean +94.7, median +83.4 |
| never-armed, rode to flatten | 453 | 35.4% | mean +149.0, median +135.7 | mean +148.9, median +129.4 |
| never-armed, stopped out | 414 | 32.3% | mean +63.1, median +47.2 | mean +317.8, median +290.0 |

**The exact shape 2026-09-21's live BankNifty trade showed** — never armed, rode to the 15:20 flatten: 453 of 1280 trades (35.4%).

- Given back: mean +148.9, median +129.4 points.
- Kept 0% of total peak profit in aggregate (per-trade median 7% — no per-trade mean reported, see this function's docstring for why that statistic is meaningless here).
- 222 of 453 (49%) closed net NEGATIVE despite having been in profit intraday.
- Total points given back across this bucket: +67446.2 (vs. total MFE across the same bucket: +67476.8).

**Contrast — trades that DID arm**: Kept 73% of total peak profit in aggregate (per-trade median 73% — no per-trade mean reported, see this function's docstring for why that statistic is meaningless here).

## Reading this

"Given back" is MFE minus the trade's own final signed move -- 0 for a trade that closed at its own best moment, positive for one that pulled back before exit. A NEVER-ARMED trade that stops out is NOT automatically a small given-back number -- its downside is bounded by the initial stop in absolute points, but if its own MFE was tiny (a brief wiggle before reversing hard), the round-trip from that tiny peak down to the stop can read as a LARGE given-back number despite the trade's total loss being capped. The two buckets' given-back figures are answering different questions and should not be read as "stopped is safer than flatten" without checking which one it is per index above. The bucket that most directly matches "is the arm threshold leaving intraday profit on the table" is NEVER-ARMED + session_flatten, reported with its own detail. This does not by itself say the 1-range-width arm threshold is wrong -- the whole historical sample using this exact rule already cleared the pre-registered PF/Sharpe bar (see docs/ORB_SCALPING_RESULTS.md) -- only how much of the strategy's real profile this specific behaviour accounts for.
