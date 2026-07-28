# ORB Options Scalping — Backtest Results (Candidate 18)

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. NIFTY and BankNifty reported independently below -- never pooled.

NIFTY window: 2022-06-01 to 2026-07-28 (1011 trades). BankNifty window: 2021-06-01 to 2026-07-28 (1245 trades).

## NIFTY

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1011 | 47.9% | 1.31 | 1.19 | +3119.1% | 394.2% |
| Stressed (+15bps/leg) | 1011 | 47.9% | 1.27 | 1.08 | +2810.8% | 420.4% |

### Per-year breakdown (Stressed)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2022 | 145 | 55.2% | 1.38 | 1.70 | +519.2% | 189.3% |
| 2023 | 240 | 42.5% | 1.01 | 0.12 | +70.5% | 420.4% |
| 2024 | 242 | 49.6% | 1.70 | 1.93 | +1438.6% | 209.2% |
| 2025 | 244 | 50.0% | 1.31 | 1.30 | +800.0% | 197.1% |
| 2026 | 140 | 42.9% | 0.94 | -0.05 | -17.5% | 267.3% |

**Verdict (NIFTY, gates on Stressed per methodology doc)**: PASS (PF 1.27, Sharpe 1.08, bar is PF > 1.0 AND Sharpe > 0.5).

## BankNifty

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 1245 | 46.4% | 1.23 | 1.20 | +4057.2% | 482.4% |
| Stressed (+15bps/leg) | 1245 | 46.3% | 1.20 | 1.09 | +3677.2% | 512.9% |

### Per-year breakdown (Stressed)

| Year | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| 2021 | 145 | 42.8% | 1.10 | 1.61 | +799.0% | 142.9% |
| 2022 | 244 | 45.1% | 1.10 | 0.58 | +352.8% | 512.9% |
| 2023 | 238 | 45.4% | 1.20 | 0.83 | +572.0% | 384.4% |
| 2024 | 241 | 46.5% | 1.34 | 1.35 | +913.3% | 316.1% |
| 2025 | 241 | 45.6% | 1.01 | 0.57 | +312.2% | 401.5% |
| 2026 | 136 | 54.4% | 1.48 | 2.24 | +727.9% | 139.1% |

**Verdict (BankNifty, gates on Stressed per methodology doc)**: PASS (PF 1.20, Sharpe 1.09, bar is PF > 1.0 AND Sharpe > 0.5).

## Overall read

Read each index's own per-year table before trusting the pooled row -- same discipline every prior candidate's per-fold/per-year breakdown has used. A pass on Clean that fails on Stressed is a real finding (the edge is an artifact of synthetic pricing with no real spread), not something to average away.
