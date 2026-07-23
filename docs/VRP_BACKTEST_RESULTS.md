# VRP Short Strangle Backtest -- Gross vs Net Result

Methodology: docs/VRP_METHODOLOGY.md (pre-committed 2026-07-23, before this ran). Window: 2023-07-24 to 2026-07-22.

## Verdict

**FAIL against the pre-committed bar** (profit factor > 1.0 AND Sharpe > 0.5, same bar used throughout this project). NET profit factor clears 1.0 (1.034) but Sharpe (0.092) is nowhere near 0.5 -- a thin, noisy edge, not a validated one. This makes FOUR strategy families tested in this project with no validated edge: Darvas (S7-3), S8-3 RS momentum rotation (corrected to a loss), S8-4 NIFTY EMA options (Sharpe 0.19, barely-breakeven), and now VRP short strangle.

## GROSS (pre-cost)

- Trades: 157 (1 cycles skipped -- missing settlement data)
- Win rate: 70.7%
- Avg P&L (pct of credit collected): +2.53%
- Profit factor: 1.039
- Sharpe (annualized, weekly cycles): 0.104
- Max drawdown (cumulative pct-of-credit points): 1622.38

## NET (post-cost, real time-varying NSE F&O charges -- see core/options/vrp/costs.py)

- Trades: 157 (1 cycles skipped -- missing settlement data)
- Win rate: 70.7%
- Avg P&L (pct of credit collected): +2.24%
- Profit factor: 1.034
- Sharpe (annualized, weekly cycles): 0.092
- Max drawdown (cumulative pct-of-credit points): 1649.13

- Strikes that fell back to fixed 2% OTM (delta unreliable that day): 0 calls / 0 puts of 158 trades

## Caveats

- Entry premium = real recorded close on the entry date. Exit value = intrinsic payout (max(0, settlement - strike) / max(0, strike - settlement)) computed from the underlying's real recorded final settlement value on the contract's own expiry date -- NOT read directly off that contract's own settle_price row, which NSE overwrites with the shared underlying settlement value on expiry day itself (see core/options/vrp/simulator.py's module docstring for the full gotcha).
- Spot/forward estimate used for STRIKE SELECTION (not for P&L) is a put-call-parity synthesis from that day's own option prices (see core/options/vrp/strikes.py), not a separately-fetched index quote.
- NET costs are real, sourced, time-varying NSE F&O charges (brokerage, STT on sell and on exercise, exchange transaction charge, SEBI turnover fee, GST) -- see core/options/vrp/costs.py's module docstring for exact rates, effective dates, and sources. Two approximations flagged there explicitly: the exchange transaction charge uses the current uniform rate across the whole window (pre-2024-10-01 NSE used a volume-tiered slab system with no single equivalent number), and lot size is not modeled at all -- checked and confirmed immaterial for this strategy's premium range (max 699.9 points seen across all trades; the brokerage flat cap only binds above ~2,667 points at NIFTY's smallest lot size this window ever used).
- No margin/cost-of-carry modeled -- a short strangle ties up margin for its whole life, and that opportunity cost isn't in either number above.

