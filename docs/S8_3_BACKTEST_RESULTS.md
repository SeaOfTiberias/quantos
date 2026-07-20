# S8-3 52-Week-High RS Momentum Backtest

Methodology pre-committed in `docs/S8_3_MOMENTUM_METHODOLOGY.md` before this ran. Top 20 by nearness-to-52-week-high, weekly rotation, 480/500 universe symbols had enough history to ever be ranked, 162 rebalance dates.

## Verdict: POSITIVE net-of-cost edge

- Total trades (pooled rotation): 2104
- Win rate: 43.1%
- Profit factor: 1.18
- Sharpe ratio: 0.63
- Max drawdown: 652.4%
- Net profit (sum of per-trade net %): 745.4%
- Avg holding period: 11 days
- Trades/month: 57.0
- Overfit risk flag: no

## Caveats

- Delivery-style cost model with an approximated (doubled sell-leg) STT rate — see docs/S8_3_MOMENTUM_METHODOLOGY.md for why.
- No anti-chattering buffer at the rank-20 boundary by design (pre-committed) — if turnover looks high, that's the honest cost of a pure rotation, not a bug to fix retroactively.
- Survivorship note: agent/universe_nifty500.txt is the CURRENT constituent list, so this shares Darvas's survivorship bias (an upper bound, not a lower bound) — a negative result here is conclusive; a positive one still needs to clear that bar.
