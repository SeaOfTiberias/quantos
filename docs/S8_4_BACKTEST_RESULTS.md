# S8-4 NIFTY EMA9/21 Options Strategy Backtest

Option P&L approximated as `delta(0.45) x underlying point move x LOT_SIZE(65)`, held at constant delta for each trade's life — a real first pass, not an options pricing model (no historical NIFTY option chain/IV data exists in this repo). Delta was checked against S8-2's real trades first (came back too noisy at n=8 to calibrate — see module docstring) rather than hand-picked with no grounding. Lot size IS grounded in real data (every S8-2 fill used qty=65). Costs use a new options-rate `CostModel` instance (STT 0.1% on sell premium vs equity's 0.025%).

## Comparison

| Variant | Trades | Win rate | Profit factor | Sharpe | Net profit % | Avg bars held |
|---|---|---|---|---|---|---|
| Baseline (+/-Rs2000 or 3:10pm, live strategy) | 693 | 49% | 1.00 | 0.03 | 37.0% | 20.8 |
| Trailing stop (ATR-based) | 774 | 51% | 0.92 | -0.29 | -523.8% | 22.6 |
| Faster invalidation exit | 818 | 35% | 1.05 | 0.19 | 313.6% | 19.4 |

## Caveats

- Delta-approximated P&L, not real option pricing (see header) — read the RELATIVE comparison between variants as the signal, not the absolute rupee figures.
- Single position at a time, no pyramiding — matches the sequential pattern observed in S8-2's real fills.
- This is one backtest run over one historical window, not a pre-committed sample of independent instruments like S7-3/S8-3 — NIFTY is the only underlying the live strategy trades, so there's no universe to sample from. The overfitting risk here is in the EXIT RULE PARAMETERS (trailing ATR multiplier, activation threshold), not instrument selection — these were chosen as standard defaults before running, not grid-searched for the best look.
