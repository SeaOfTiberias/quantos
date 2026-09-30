# Candidate 18 — independent verification in TradingView (2026-09-30)

The user ran `pine/orb_candidate18_verification.pine` (V0 rules, index points, 1 lot = 65, 0.014%/order + 1 pt
slippage per fill) on NSE:NIFTY 5-minute with Deep Backtesting, 2022-06-01 to 2026-09-30, and exported the trade list
(`backtest_results/ORB-verify_NSE_NIFTY_2026-09-30_0612f.csv`). Compared trade-by-trade with QuantOS's
`exit_policies` V0 on its own cached Fyers candles.

| Check | Result |
|---|---|
| Trades | TradingView 1,060 · QuantOS 1,056 · same days 1,055 |
| Same direction on the same day | 1,007 / 1,055 (95%) |
| Same exit reason (where direction agrees) | 935 / 1,007 (93%) |
| Entry price difference | median +1.00 pt = exactly the configured slippage |
| Exit price difference, same reason | median 1.00 pt, 90th percentile 2.45 pts |
| Gross points per trade | QuantOS +2.13 · TradingView +3.59 (TradingView's already net of its 2 pts slippage) |
| Net result | TradingView −Rs4,45,059 (−Rs420/trade, 49% winners) · QuantOS futures V0 −Rs4,63,510 |

**Conclusion:** TradingView's engine, on its own data, independently reproduces the finding: the ORB signal's
gross edge is a few index points per trade, well below the ~9-point round-trip cost, so it loses after costs.

Known mismatches (they don't change the conclusion):
- On ~117 days TradingView entered one 5-minute bar earlier (09:30 vs QuantOS 09:35), i.e. its opening range
  covered fewer bars on those days. This is a Pine-side day-boundary/bar-count quirk to fix if an exact match is
  ever needed. It also explains most of the 48 direction mismatches.
- 40 trades QuantOS held to the 15:20 flatten exited earlier on TradingView's trailing stop, since TradingView
  fills gaps at the gap price and differs slightly in intrabar ordering.
