# ORB Options Scalping — Backtest Results (Candidate 18)

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and BankNifty reported independently below -- never pooled.

**Harsh is a POST-HOC additional stress test** (added 2026-07-28 after an adversarial review of the original Clean/Stressed PASS, core/orb_scalping/costs.py's `harsh_trade_cost`) — it is NOT part of the pre-registered methodology doc's pass/fail bar, which gates on Stressed alone. Reported for transparency, not to move the goalposts after the fact.

NIFTY window: 2022-06-01 to 2026-07-28 (1011 trades). BankNifty window: 2021-06-01 to 2026-07-28 (1245 trades).

## NIFTY

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1011 | 47.9% | 1.31 | 1.19 | +3119.1% | 394.2% |
| Stressed (+15bps/leg) | 1011 | 47.9% | 1.27 | 1.08 | +2810.8% | 420.4% |
| Harsh (post-hoc, see below) | 1011 | 47.7% | 1.21 | 0.84 | +2193.0% | 492.5% |

### Per-year breakdown (Harsh)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2022 | 145 | 54.5% | 1.31 | 1.42 | +431.4% | 206.3% |
| 2023 | 240 | 42.5% | 0.95 | -0.20 | -120.9% | 492.5% |
| 2024 | 242 | 49.6% | 1.62 | 1.75 | +1302.0% | 229.2% |
| 2025 | 244 | 49.6% | 1.25 | 1.08 | +663.2% | 210.3% |
| 2026 | 140 | 42.9% | 0.91 | -0.25 | -82.7% | 286.4% |

**Verdict (NIFTY, gates on Stressed per the pre-registered methodology doc)**: PASS (PF 1.27, Sharpe 1.08, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.21, Sharpe 0.84).

## BankNifty

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1245 | 46.4% | 1.23 | 1.20 | +4057.2% | 482.4% |
| Stressed (+15bps/leg) | 1245 | 46.3% | 1.20 | 1.09 | +3677.2% | 512.9% |
| Harsh (post-hoc, see below) | 1245 | 46.0% | 1.17 | 0.97 | +3248.9% | 543.8% |

### Per-year breakdown (Harsh)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2021 | 145 | 42.1% | 1.07 | 1.49 | +736.8% | 146.4% |
| 2022 | 244 | 45.1% | 1.07 | 0.46 | +276.8% | 543.8% |
| 2023 | 238 | 45.4% | 1.16 | 0.68 | +463.1% | 449.9% |
| 2024 | 241 | 46.1% | 1.31 | 1.23 | +835.8% | 335.8% |
| 2025 | 241 | 45.2% | 0.98 | 0.43 | +239.1% | 450.9% |
| 2026 | 136 | 54.4% | 1.45 | 2.14 | +697.2% | 143.1% |

**Verdict (BankNifty, gates on Stressed per the pre-registered methodology doc)**: PASS (PF 1.20, Sharpe 1.09, bar is PF > 1.0 AND Sharpe > 0.5).

**Harsh read (post-hoc, NOT part of the pre-registered pass/fail bar)**: still clears the same bar under a flat Rs20/leg brokerage + liquidity-tiered slippage on the DTE-floor-rolled subset (PF 1.17, Sharpe 0.97).

## Overall read

Read each index's own per-year table before trusting the pooled row -- same discipline every prior candidate's per-fold/per-year breakdown has used. A pass on Clean/Stressed that fails under Harsh is a real finding (the pre-registered Stressed cost model still understates real F&O brokerage/liquidity friction at this trade size), not something to average away.
