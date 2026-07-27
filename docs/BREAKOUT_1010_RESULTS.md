# 10:10 Breakout on BankNifty Options — Backtest Results (Candidate 15)

Methodology: docs/BREAKOUT_1010_METHODOLOGY.md. Black-Scholes-reconstructed option premium (real BankNifty spot + India VIX proxy, NOT real traded premium — see docs/CANDIDATE15_OPTION_DATA_FEASIBILITY.md), 2021-06-01 to 2026-07-27. 1273 trades total (one per day, at most).

Real INR aggregates (1 lot/trade, per docs/BREAKOUT_1010_METHODOLOGY.md's position sizing — NOT a claim about a specific capital base): gross profit ₹704,754, gross loss ₹636,067, total transaction costs ₹47,351, **net ₹68,687** across 1273 trades (₹54/trade average).

**Read `net_profit_pct` and `max_drawdown_pct` below with caution**: both are computed by `core/backtest/parser.py` as a raw SUM of each trade's own-entry-notional %% return, not capital-weighted or compounded — the exact measurement trap Fable identified in candidate 14 (Dow theory), where a large summed-%% headline sat next to a confirmed real rupee loss. A `max_drawdown_pct` over 100%% here is a symptom of that same artifact (a real account cannot lose more than 100%% of its capital), not a literal claim. `profit_factor` (real INR gross-profit/gross-loss ratio) and the real-INR line above are the only figures trusted at face value in this report, same precedent as candidate 14.

## Pooled result

| Period | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| **Overall** | 1273 | 18.1% | 1.11 | 0.65 | +1144.0% | 296.2% |
| 2021 | 146 | 15.1% | 0.95 | 0.74 | +192.2% | 127.8% |
| 2022 | 247 | 16.2% | 0.99 | -0.07 | -17.8% | 169.4% |
| 2023 | 245 | 19.2% | 1.33 | 1.53 | +743.7% | 192.9% |
| 2024 | 248 | 23.4% | 1.47 | 1.16 | +354.4% | 109.1% |
| 2025 | 248 | 16.5% | 0.94 | -0.54 | -125.3% | 248.3% |
| 2026 | 139 | 15.8% | 0.86 | -0.03 | -3.2% | 191.5% |

## Verdict

Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), computed on the pooled trade set, net of the reused F&O options cost model: **PASS**.

Read the per-year table above, not just the pooled row, before trusting this — same discipline every prior candidate's per-fold/per-year breakdown has used. **Remember**: every premium here is Black-Scholes theoretical, not a real traded price — see the methodology doc's central-limitation section before treating a PASS as sufficient to move toward live capital.
