---
title: Options VRP Short Strangle
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-options-vrp-variance-risk-premium-backtest-methodology-pre-c, 2026-09-17-vrp-short-strangle-backtest-gross-vs-net-result, 2026-09-17-vrp-iv-conditional-gut-check-results-exploratory-not-pre-reg
---

# Options VRP Short Strangle

> [!abstract] Compiled page
> Written from `[[2026-09-17-options-vrp-variance-risk-premium-backtest-methodology-pre-c]]`, `[[2026-09-17-vrp-short-strangle-backtest-gross-vs-net-result]]`, and `[[2026-09-17-vrp-iv-conditional-gut-check-results-exploratory-not-pre-reg]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A premium-selling strategy testing whether NIFTY's implied volatility systematically overprices realized volatility (the variance risk premium) — flagged by Fable's 2026-07-19 review as "the genuinely best-supported edge" among remaining candidates after Darvas and S8-3 both disappointed.

## Mechanics

- **Structure**: sell one OTM call + one OTM put, same expiry, no delta-hedging, no mid-trade adjustment — chosen over a straddle (too much tail exposure) or an iron condor (long wings would dilute the very IV-RV gap being measured).
- **Entry**: roll immediately — a new cycle opens the trading day after the prior one expires, selling the next-nearest weekly, landing naturally in a ~5–7 day DTE band.
- **Strikes**: ~0.20-delta, computed from that day's real settlement prices (Black-Scholes delta, IV backed out per strike); falls back to a fixed 2% OTM if delta can't be computed.
- **Exit**: hold to expiry, cash-settle — no stop-loss, no profit target, no early close. Deliberately the simplest, most auditable read of the gap, at the cost of having no downside protection during a real tail event.
- **Data**: real NSE F&O bhavcopy settlement prices, 2023-07-24 to 2026-07-22 (737 trading days), spanning both the 2024-06 election-result crash and the 2025-04 geopolitical shock.

## Verdict

**FAIL** — profit factor clears 1.0 but Sharpe is nowhere near the 0.5 bar `[[2026-09-17-vrp-short-strangle-backtest-gross-vs-net-result]]`:

| | Trades | Win rate | Profit factor | Sharpe |
|---|---|---|---|---|
| Gross | 157 | 70.7% | 1.039 | 0.104 |
| Net (real time-varying NSE F&O costs) | 157 | 70.7% | 1.034 | 0.092 |

A 70.7% win rate with a Sharpe of 0.09 describes a strategy that wins often in small increments and occasionally loses large — a thin, noisy edge, not a validated one. This made VRP the fourth strategy family tested in this project (after Darvas, S8-3, and S8-4) with no validated edge.

### Exploratory follow-up (not pre-registered)

A post-hoc IV-tercile cut of the same 158 trades found a directionally sensible pattern — high entry-IV trades did much better (PF 1.661, Sharpe 1.465) than low entry-IV trades (PF 0.787, Sharpe -0.595) `[[2026-09-17-vrp-iv-conditional-gut-check-results-exploratory-not-pre-reg]]`. Explicitly flagged as not yet a finding: the tercile boundaries were computed in-sample over the whole 2023–2026 window (a live system couldn't have known them in real time), the bucket sizes (~52–54 trades) may represent far fewer independent volatility episodes than their raw count suggests, and raw IV level was used rather than a rolling percentile. A proper follow-up would need all three fixed and pre-registered before rerunning — not done as of this writing.

## Relation to other concepts

The VRP trade data is explicitly NOT connected to any of the five [[strategy-search|vol-conditioning signals]] before each of those signals' own validation locks — a standing rule repeated in every one of those methodology docs, to avoid a regime-filtered VRP subset being reported as a rescued headline.
