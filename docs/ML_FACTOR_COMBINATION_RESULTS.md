# ML Multi-Factor Stock Ranking — Backtest Results (Candidate 16)

Methodology: docs/ML_FACTOR_COMBINATION_METHODOLOGY.md. Nifty 500 universe, 610/648 symbols had enough history to ever be scored. Split date: 2025-06-29 (train before, test on/after). Train rows: 50016, test rows: 26731. Selected C=10.0. Train AUC: 0.552, Test AUC: 0.539.

## ML-ranked strategy (test period only, fresh capital-tracked run)

## ML model

- Final equity: ₹1,048,206
- Total return: 4.8%
- CAGR: 4.5%
- Sharpe: 0.31
- Max drawdown: 26.0%
- Trades: 224

## Single-factor-momentum baseline (test period only, fresh run, same harness)

## Baseline (rank_universe)

- Final equity: ₹978,440
- Total return: -2.2%
- CAGR: -2.0%
- Sharpe: -0.06
- Max drawdown: 14.8%
- Trades: 655

## vs. Nifty 500 buy-and-hold (test period)

- Final equity: ₹938,749
- Total return: -6.1%
- CAGR: -5.7%
- Sharpe: -0.40
- Max drawdown: 15.2%
- Alpha vs this benchmark: total return +10.9pts, CAGR +10.2pts, beats it: Yes

## vs. Nifty Alpha 50 buy-and-hold (test period)

- Final equity: ₹994,370
- Total return: -0.6%
- CAGR: -0.5%
- Sharpe: 0.07
- Max drawdown: 17.5%
- Alpha vs this benchmark: total return +5.4pts, CAGR +5.0pts, beats it: Yes

## Verdict

Per docs/ML_FACTOR_COMBINATION_METHODOLOGY.md's bar — ALL FOUR required, test period only:
1. CAGR>0% and Sharpe>0.5: FAIL (CAGR 4.5%, Sharpe 0.31)
2. Beats Nifty 500 buy-and-hold: PASS
3. Beats Nifty Alpha 50 buy-and-hold: PASS
4. Beats single-factor-momentum baseline (4.8% vs -2.2%): PASS

**Overall: FAIL** (all four required).

Single held-out test period, not a distribution — no confidence interval on any of the above. Treat as one realization, not an expected value, same caveat S8-3's own equity-curve report carries.
