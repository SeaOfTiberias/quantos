---
title: Darvas Box / SEPA Breakout (S7-3)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: darvas-sepa-s7-3
candidate: "S7-3"
family: breakout
instrument: equity-cash
status: closed
verdict: FAIL
first_tested: 2026-07-16
verdict_date: 2026-07-19
profit_factor: 0.75
sharpe: -1.25
trades: 690
bar: "PF > 1 and Sharpe > 0.5 at realistic 20 bps slippage"
headline: "The original Darvas/SEPA breakout failed its first pre-registered backtest; even zero-slippage costs missed the Sharpe bar (0.22)."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-s7-3-backtest-sample-pre-committed-2026-07-16-before-any-res, 2026-09-17-s7-3-backtest-results-go-no-go-verdict, 2026-10-13-s7-2-expectancy-arithmetic-does-darvass-plausible-edge-clear
---

# Darvas Box / SEPA Breakout (S7-3)

> [!abstract] Compiled page
> Written from `[[2026-09-17-s7-3-backtest-sample-pre-committed-2026-07-16-before-any-res]]` and `[[2026-09-17-s7-3-backtest-results-go-no-go-verdict]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The original strategy this project's whole live-trading infrastructure (discovery scanner, cockpit, execution agent) was built around, before the project's own pre-registered-backtest discipline existed. S7-3 is the first strategy actually held to that discipline: a pre-committed, seeded sample of 40 NSE symbols (20 large/mid-cap, 20 small-cap, drawn from `agent/universe_nifty500.txt` split by Smallcap 250 membership) run through a Darvas-box breakout backtest before any result was seen `[[2026-09-17-s7-3-backtest-sample-pre-committed-2026-07-16-before-any-res]]`.

## Mechanics

The sample itself is the pre-registration: seed `20260716`, N=40, reproducible from `scripts/sample_s73_backtest_universe.py` against the same inputs. Cost model: NSE stack + 20bps slippage/leg (`core/risk/costs.py`) `[[2026-09-17-s7-3-backtest-results-go-no-go-verdict]]`.

## Verdict

**FAIL — "NO demonstrated edge."** 39 of 40 symbols analyzed (DOMS excluded, wrong currency export), 690 pooled trades:

| | Trades | Win rate | Profit factor | Sharpe | Net % |
|---|---|---|---|---|---|
| Realistic (20bps slippage) | 690 | 28.7% | 0.75 | -1.25 | -241.0% |
| Best-case (0bps slippage) | 690 | 34.2% | 1.11 | 0.22 | +41.8% |

Even the unrealistic zero-friction case fails the Sharpe half of the bar (0.22 against the required >0.5) — there is no cost assumption within a defensible range at which this specification clears a genuine edge, only a narrow band that is roughly breakeven before real execution friction `[[2026-09-17-s7-3-backtest-results-go-no-go-verdict]]`. By-symbol results are highly dispersed (HINDZINC profit factor 7.15 on 6 trades; DCMSHRIRAM 0.00 on 6 trades) — the pooled loss is not one bad name dragging down an otherwise-working strategy, it is broadly negative across the sample.

The sample is drawn from *current* Nifty 500 / Smallcap 250 constituents, an upper-bound survivorship bias — the negative verdict is read as conclusive precisely because costs beat the edge even with that bias helping.

## Before the backtest: S7-2 expectancy arithmetic

A zero-code check run on 2026-07-16, before S7-3, asking whether a plausible Darvas edge clears its own costs. Round-trip cost from the calibrated cost model: 0.36–0.41% of notional for a liquid fill (15 bps slippage), 0.92% for an illiquid breakout fill (40 bps). Plausible breakout ranges (30–45% win rate, 1.5–2.5R winners, about 1R losers) give 0.05–0.2R gross expectancy. With 1R at 3–5% of price, cost runs 0.07–0.31R. Net expectancy therefore ranges from about +0.13R (wide box, liquid) to −0.26R (tight box, illiquid). **The arithmetic cannot sign the edge**, which is why S7-3 was run `[[2026-10-13-s7-2-expectancy-arithmetic-does-darvass-plausible-edge-clear]]`.

## Relation to other concepts

- [[Mark_Minervini_VCP_Strategy]] and [[Stan_Weinstein_Stage_Analysis]] describe the same family of breakout/momentum chart pattern this strategy traded on, as hand-authored discretionary screening rules rather than a backtested system — this page's FAIL does not bear on whether those patterns are useful for manual screening.
- The FAIL here is the reason this project moved to [[rs-momentum-rotation-s8-3]] as its next rotation-style candidate, per Fable's post-Darvas review naming 52-week-high momentum as the strongest remaining academically-grounded candidate.
- The Darvas signal was reopened in September 2026 from the box-width angle: [[darvas-box-width]] (static exit, failed), then [[darvas-trailing-stop]] (breakeven), then [[darvas-atr-stop-bucket-b]]. The last, with a volatility-scaled stop instead of a fixed buffer, passed and is the project's only live (paper) strategy.
