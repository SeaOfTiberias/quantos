---
title: Good Night Stock-Options Scalper (Candidate 20)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-good-night-open-price-stock-options-scalper-candidate-20-fea, 2026-09-17-good-night-stock-options-scalper-methodology-pre-committed-2, 2026-09-17-good-night-scalper-backtest-results-candidate-20
---

# Good Night Stock-Options Scalper (Candidate 20)

> [!abstract] Compiled page
> Written from `[[2026-09-17-good-night-open-price-stock-options-scalper-candidate-20-fea]]`, `[[2026-09-17-good-night-stock-options-scalper-methodology-pre-committed-2]]`, and `[[2026-09-17-good-night-scalper-backtest-results-candidate-20]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

An externally-sourced (attributed to "Rajesh Jain", unverifiable) fast scalp on individual Nifty200 Momentum 30 stock options, keyed to whether the day's opening candle touches the session's own open exactly. Sat in informal "gather a few more sessions" status for two weeks before getting a pre-registered methodology and a real backtest.

## Mechanics

- **Setup A**: 09:15 1-minute candle's low == the day's open → CALL. **Setup B**: high == open → PUT. (A third setup, "cross-back-through-open," was never precisely specified in any source and is explicitly excluded — testing it would mean inventing a rule, not testing the one described.)
- **Execution**: next 1-minute candle's open.
- **Exit**: +10% premium target / -15% premium stop / 09:30 IST hard flatten, whichever comes first — a ~14-minute maximum hold.
- **Universe**: Nifty200 Momentum 30, current constituents, minus SAIL (10 independent live readings, 78–192% round-trip spread — confirmed persistently illiquid, excluded from the universe rather than filtered per-day).
- **IV proxy**: trailing 20-trading-day realized volatility per stock (no per-stock India-VIX equivalent exists for 30 individually different names).
- **Cost model**: Clean (statutory costs only) and Stressed — the Stressed rate is a *measured* median spread (2.09% round-trip, `quantos-goodnight-openwindow-probe.timer`, 7 trading mornings, 242 real at-open bid-ask legs), not a guessed bps range.

## Verdict

**FAIL**, decisively, on the Stressed variant `[[2026-09-17-good-night-scalper-backtest-results-candidate-20]]`:

| | Clean | Stressed (real measured spread) |
|---|---|---|
| Trades | 444 | 444 |
| Win rate | 54.9% | 41.9% |
| Profit factor | 1.19 | **0.54** |
| Sharpe | 0.79 | **-2.80** |
| Net P&L | +206% | **-725%** |

Clean passes both bars; Stressed doesn't just fail, it inverts. Both setups fail independently (A: PF 0.42; B: PF 0.65) and so does every month in the 2026-07-07 to 2026-09-17 window — not one bad subset dragging down an otherwise-viable pool. The feasibility work that preceded the backtest had already flagged this as the central risk: individual stock options carry a 10–30x wider round-trip spread than NIFTY/BankNifty index options, measured at the actual thin-liquidity moment right after open, not a mid-session proxy.

## Relation to other concepts

- Shares its failure shape with [[breakout-1010-banknifty-candidate-15]]: a real edge under frictionless/synthetic pricing that a real spread cost erases. The difference is this candidate used a real *measured* spread rather than a guessed stress bps, so the FAIL here is decisive rather than a stress-test caveat on a technical PASS.
- [[orb-options-scalping-candidate-18]] is the index-option counterpart that survived the equivalent cost scrutiny — the contrast is between index-option liquidity (11–18bps round-trip) and individual stock-option liquidity (209bps) on otherwise similar option-scalping mechanics.
