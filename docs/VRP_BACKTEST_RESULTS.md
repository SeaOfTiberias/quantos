# VRP Short Strangle Backtest -- GROSS, Pre-Cost Result

Methodology: docs/VRP_METHODOLOGY.md (pre-committed 2026-07-23, before this ran). Window: 2023-07-24 to 2026-07-22.

**This is a gross, pre-transaction-cost read only. Phase 4 (cost model) has not run. Do not treat this as a go/no-go verdict.**

## Pooled per-trade stats

- Trades: 157 (1 cycles skipped -- missing settlement data)
- Win rate: 70.7%
- Avg P&L (pct of credit collected): +2.53%
- Profit factor: 1.039
- Sharpe (annualized, weekly cycles): 0.104
- Max drawdown (cumulative pct-of-credit points): 1622.38
- Strikes that fell back to fixed 2% OTM (delta unreliable that day): 0 calls / 0 puts of 158 trades

## Caveats

- GROSS P&L only -- no brokerage/STT/exchange charges, no margin cost of carry.
- Entry premium = real recorded close on the entry date. Exit value = intrinsic payout (max(0, settlement - strike) / max(0, strike - settlement)) computed from the underlying's real recorded final settlement value on the contract's own expiry date -- NOT read directly off that contract's own settle_price row, which NSE overwrites with the shared underlying settlement value on expiry day itself (see core/options/vrp/simulator.py's module docstring for the full gotcha).
- Spot/forward estimate used for STRIKE SELECTION (not for P&L) is a put-call-parity synthesis from that day's own option prices (see core/options/vrp/strikes.py), not a separately-fetched index quote.

