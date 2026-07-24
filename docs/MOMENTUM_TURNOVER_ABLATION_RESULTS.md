# Momentum Turnover Ablation — Results

Methodology: docs/MOMENTUM_TURNOVER_ABLATION_METHODOLOGY.md. Weekly baseline is docs/S8_3_EQUITY_CURVE_RESULTS.md's existing run (not re-run here — same parameters, so it's a valid control). Quarterly variant: 14 rebalance dates, same ₹1,000,000 capital, ₹50,000/position, top 20, same point-in-time Nifty 500 universe, same DELIVERY_COST_MODEL, exit_rule=rank_only in both.

## Weekly (control, from S8_3_EQUITY_CURVE_RESULTS.md)

- Total return: 12.8%
- CAGR: 4.0%
- Sharpe: 0.34
- Max drawdown: 26.2%
- Trades: 2034

## Quarterly (this ablation)

- Total return: 34.8%
- CAGR: 10.2%
- Sharpe: 0.81
- Max drawdown: 21.0%
- Trades: 244

## Gap closed vs Nifty Alpha 50 (the sharper peer bar)

- Weekly: CAGR 4.0% vs Alpha 50 19.5% (alpha -15.5pp)
- Quarterly: CAGR 10.2% vs Alpha 50 19.5% (alpha -9.3pp)
- CAGR gap closed by switching to quarterly: +40%
- Sharpe gap closed by switching to quarterly: +80%

## Gap closed vs Nifty 500

- Weekly alpha (total return): -13.5pp
- Quarterly alpha (total return): +8.5pp

## Benchmarks (same window/capital as both runs)

- Nifty 500: final ₹1,263,057, CAGR 7.9%, Sharpe 0.65
- Nifty Alpha 50: final ₹1,730,994, CAGR 19.5%, Sharpe 0.93

## Interpretation

This is a diagnostic ablation, not a strategy validation — see the methodology doc's framing. A large gap closure means turnover/exit-tightness explains most of the weekly wrapper's underperformance vs Alpha 50, and a properly pre-registered lower-turnover momentum candidate is worth building. A small or negative gap closure rules turnover out as the primary explanation.
