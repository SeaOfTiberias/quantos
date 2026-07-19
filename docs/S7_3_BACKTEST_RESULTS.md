# S7-3 Backtest Results — go/no-go verdict

**Sample:** 39 of 40 pre-committed symbols analyzed (1 missing: ['DOMS'] — PARTIAL, not a full verdict) [excluded for wrong currency: ['DOMS (SEK)']]
**Cost model:** NSE stack + 20bps slippage/leg (core/risk/costs.py)
**No-trade symbols (box never fired in the tested window):** none

## Verdict: NO demonstrated edge

- Total trades (pooled, all symbols): 690
- Win rate: 28.7%
- Profit factor: 0.75
- Sharpe ratio: -1.25
- Max drawdown: 241.1%
- Net profit (sum of per-trade net %): -241.0%
- Overfit risk flag: no

## By cap tier

| Tier | Trades | Win rate | Profit factor | Net % |
|---|---|---|---|---|
| Large/mid | 420 | 28% | 0.83 | -98.6% |
| Small | 270 | 29% | 0.66 | -142.5% |

## By symbol

| Symbol | Tier | Trades | Win rate | Profit factor | Net % |
|---|---|---|---|---|---|
| APOLLOTYRE | large_mid | 11 | 36% | 0.60 | -2.8% |
| APTUS | small | 14 | 21% | 0.30 | -13.3% |
| BAJAJ-AUTO | large_mid | 32 | 47% | 0.91 | -1.2% |
| BAJAJHLDNG | large_mid | 17 | 12% | 0.07 | -30.4% |
| BAYERCROP | small | 15 | 13% | 0.31 | -17.7% |
| BDL | large_mid | 19 | 37% | 2.63 | 32.6% |
| BEML | small | 17 | 35% | 1.48 | 7.4% |
| BRIGADE | small | 14 | 21% | 0.21 | -23.7% |
| DATAPATTNS | small | 17 | 24% | 0.93 | -0.4% |
| DCMSHRIRAM | small | 6 | 0% | 0.00 | -19.8% |
| DEVYANI | small | 5 | 40% | 0.29 | -4.0% |
| DRREDDY | large_mid | 23 | 9% | 0.10 | -21.5% |
| EICHERMOT | large_mid | 31 | 32% | 0.45 | -12.3% |
| ELECON | small | 19 | 37% | 0.77 | -4.4% |
| EMMVEE | small | 5 | 0% | 0.00 | -17.1% |
| ETERNAL | large_mid | 42 | 19% | 0.22 | -46.5% |
| EXIDEIND | large_mid | 30 | 37% | 0.44 | -14.6% |
| GAIL | large_mid | 21 | 19% | 0.18 | -20.2% |
| GLAND | small | 16 | 44% | 0.40 | -9.9% |
| GMRAIRPORT | large_mid | 23 | 26% | 0.76 | -3.8% |
| GRSE | small | 22 | 41% | 1.13 | 7.3% |
| HDFCBANK | large_mid | 5 | 20% | 0.12 | -3.0% |
| HINDZINC | large_mid | 6 | 67% | 7.15 | 49.5% |
| HOMEFIRST | small | 9 | 33% | 0.10 | -24.7% |
| ICICIBANK | large_mid | 16 | 25% | 0.26 | -9.9% |
| IOB | small | 10 | 60% | 5.30 | 32.8% |
| IRFC | large_mid | 13 | 46% | 2.82 | 37.2% |
| LALPATHLAB | small | 21 | 5% | 0.05 | -22.9% |
| LTM | large_mid | 16 | 6% | 0.11 | -14.1% |
| MOTILALOFS | large_mid | 25 | 36% | 1.28 | 8.3% |
| NBCC | small | 26 | 42% | 0.84 | -5.4% |
| SCI | small | 18 | 50% | 1.18 | 4.3% |
| SHREECEM | large_mid | 14 | 14% | 0.07 | -13.6% |
| SUMICHEM | small | 11 | 9% | 0.15 | -18.1% |
| SUPREMEIND | large_mid | 10 | 20% | 0.19 | -16.3% |
| TVSMOTOR | large_mid | 41 | 29% | 0.47 | -13.5% |
| UCOBANK | small | 14 | 29% | 0.88 | -1.6% |
| ZYDUSLIFE | large_mid | 25 | 36% | 0.86 | -2.6% |
| ZYDUSWELL | small | 11 | 9% | 0.19 | -11.2% |

Remember: this sample is survivorship-biased (current Nifty 500 constituents) and thus an UPPER BOUND. A negative verdict here is conclusive (costs beat the edge even with the bias helping); a positive verdict here is necessary but not sufficient — it still needs S7-4's veto instrumentation before the live record is interpretable.

## Sensitivity check: is this just the slippage assumption?

Re-ran with `--slippage-bps 0` (statutory NSE costs only — brokerage/STT/exchange/SEBI/stamp/GST, zero execution friction, the most generous case possible) to check whether the negative verdict is an artifact of the 20bps slippage estimate rather than a real result:

| Slippage/leg | Trades | Win rate | Profit factor | Sharpe | Net % | Verdict |
|---|---|---|---|---|---|---|
| 20bps (realistic) | 690 | 28.7% | 0.75 | -1.25 | -241.0% | NO demonstrated edge |
| 0bps (best case, unrealistic) | 690 | 34.2% | 1.11 | 0.22 | +41.8% | NO demonstrated edge (Sharpe 0.22 < 0.5 threshold) |

Even under a zero-friction assumption no real execution could achieve, the
edge is barely above breakeven on profit factor and fails the Sharpe bar
(`BacktestMetrics.has_positive_edge` requires both profit_factor > 1.0 AND
Sharpe > 0.5, `core/backtest/parser.py`). This is exactly what
`docs/EXPECTANCY_CHECK.md` predicted from arithmetic alone — the
hypothesized edge sits inside the cost model's error bars — now confirmed
empirically rather than sketched: there is no cost assumption within a
defensible range at which this specification clears a genuine edge, only a
narrow band where it's roughly breakeven before accounting for realistic
execution friction.

## Missing symbol

DOMS.csv was excluded (exported in SEK, not INR — needs re-export). Given
690 pooled trades and how decisively negative the realistic-cost result is,
one more symbol is very unlikely to change the verdict, but re-running with
the full 40 once DOMS is fixed would complete the pre-committed sample
properly.
