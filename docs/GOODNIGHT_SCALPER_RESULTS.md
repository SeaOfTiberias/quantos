# "Good Night" Scalper — Backtest Results (Candidate 20)

Methodology: docs/GOODNIGHT_SCALPER_METHODOLOGY.md. Setup A + B, pooled (never split into separate gates) -- see the methodology doc for why.

Universe: 29 symbols from agent/universe_nifty200momentum30.txt (SAIL excluded — confirmed persistently illiquid).
Window: 2026-07-07 to 2026-09-17 (re-verified at run time by the actual 1-minute fetch, not assumed).

## Pooled (validation gate)

| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |
|---|---|---|---|---|---|---|
| Clean | 444 | 54.9% | 1.19 | 0.79 | +206.2% | 108.1% |
| Stressed (real measured spread) | 444 | 41.9% | 0.54 | -2.80 | -725.3% | 750.2% |

**Verdict (gates on Stressed, per the pre-registered methodology doc)**: FAIL (PF 0.54, Sharpe -2.80, bar is PF > 1.0 AND Sharpe > 0.5).

## Per-setup breakdown (Stressed, supplementary — not a separate gate)

| Setup | Trades | Win rate | Profit factor | Sharpe | Net P&L % |
|---|---|---|---|---|---|
| A | 169 | 36.7% | 0.42 | -4.30 | -458.3% |
| B | 275 | 45.1% | 0.65 | -1.78 | -267.1% |

## Per-month breakdown (Stressed)

| Month | Trades | Win rate | Profit factor | Sharpe | Net P&L % |
|---|---|---|---|---|---|
| 2026-07 | 153 | 39.2% | 0.49 | -3.50 | -271.1% |
| 2026-08 | 188 | 36.2% | 0.45 | -4.05 | -422.3% |
| 2026-09 | 103 | 56.3% | 0.88 | -0.43 | -31.9% |

## Trade count by symbol (Stressed)

| Symbol | Trades |
|---|---|
| ABB | 22 |
| ABCAPITAL | 18 |
| ADANIENSOL | 20 |
| ADANIGREEN | 20 |
| ADANIPOWER | 10 |
| BHARATFORG | 18 |
| BHEL | 20 |
| BSE | 9 |
| CGPOWER | 12 |
| CUMMINSIND | 22 |
| FEDERALBNK | 21 |
| GLENMARK | 20 |
| GVT&D | 8 |
| HINDALCO | 8 |
| IDEA | 11 |
| KEI | 13 |
| LAURUSLABS | 6 |
| LTF | 14 |
| MCX | 10 |
| MOTHERSON | 18 |
| NATIONALUM | 11 |
| NTPC | 15 |
| POLYCAB | 18 |
| POWERINDIA | 16 |
| SHRIRAMFIN | 16 |
| SOLARINDS | 25 |
| TATASTEEL | 15 |
| TORNTPHARM | 15 |
| VEDL | 13 |
