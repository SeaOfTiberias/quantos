# S8-3 Rotation — Real Capital-Tracked Equity Curve

What docs/S8_3_BACKTEST_RESULTS.md's pooled per-trade stats (profit factor 1.18, Sharpe 0.63) actually mean for a real ₹1,000,000 account: one simulated account, real position sizing (₹50,000 across the top 20, via core/rotation/executor.py's own sizing), daily mark-to-market. Baseline rank-dropout exit only — no stop-loss/EMA variants (out of scope for this run, see script docstring). 610/648 universe symbols had enough history to ever be ranked, 161 rebalance dates.

## Strategy

- Initial capital: ₹1,000,000
- Final equity: ₹1,127,590
- Total return: 12.8%
- CAGR: 4.0%
- Sharpe: 0.34
- Max drawdown: 26.2% (₹351,444)
- Trades: 2034

## Nifty 500 benchmark (buy-and-hold, same window/capital)

- Final equity: ₹1,283,826
- Total return: 28.4%
- CAGR: 8.5%
- Sharpe: 0.69
- Max drawdown: 15.8%

Alpha vs Nifty 500 benchmark (buy-and-hold, same window/capital) — total return: -15.6 pts, CAGR: -4.5 pts, strategy beats it: No

## Nifty Alpha 50 benchmark (buy-and-hold, same window/capital)

- Final equity: ₹1,773,698
- Total return: 77.4%
- CAGR: 20.5%
- Sharpe: 0.97
- Max drawdown: 31.5%

Alpha vs Nifty Alpha 50 benchmark (buy-and-hold, same window/capital) — total return: -64.6 pts, CAGR: -16.5 pts, strategy beats it: No

## Caveats

- Delivery-style cost model with an approximated (doubled sell-leg) STT rate — same as docs/S8_3_MOMENTUM_METHODOLOGY.md.
- Point-in-time Nifty 500 membership: each week's ranking is restricted to the actual constituents as of that week (core/rotation/nifty500_reconstitution.py, reconstructed from NSE's semi-annual reconstitution press releases), not today's list applied retroactively. This corrects the survivorship bias in the original run (quantos-equity-curve-and-fable-review) — a stock since dropped from the index can now be ranked/held in the weeks it actually was a constituent, and a recently-added one is excluded from weeks before it joined.
- Nifty Alpha 50 benchmark is buy-and-hold on the index level only — it does NOT get the same point-in-time constituent treatment (nobody is trading its membership here, so there's no survivorship bias to correct for a passive holder).
- Single simulated run, not a distribution — no confidence interval on CAGR/Sharpe/drawdown. Treat as one realization, not an expected value.
