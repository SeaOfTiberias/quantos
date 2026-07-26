# Dow Theory / Market Structure Trend Following — Backtest Results (Candidate 14)

Methodology: docs/DOW_THEORY_TREND_METHODOLOGY.md. NIFTY spot (futures proxy, see methodology doc), 2022-06-01 to 2026-07-24. 3650 trade legs total (includes both halves of a scaled-out position as separate legs).

## Pooled result

| Period | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| **Overall** | 3650 | 57.6% | 0.88 | 2.23 | +184.9% | 2.9% |
| 2022 | 571 | 55.7% | 0.79 | 1.64 | +22.4% | 2.4% |
| 2023 | 912 | 59.5% | 0.96 | 2.74 | +47.9% | 2.5% |
| 2024 | 808 | 60.0% | 1.05 | 2.89 | +59.5% | 1.9% |
| 2025 | 858 | 55.7% | 0.79 | 1.75 | +31.5% | 2.9% |
| 2026 | 501 | 55.9% | 0.79 | 1.87 | +23.6% | 2.6% |

## Verdict

Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), computed on the pooled trade-leg set, net of the reused futures cost model: **FAIL**.

Read the per-year table above, not just the pooled row, before trusting this — same discipline every prior candidate's per-fold/per-year breakdown has used.
