---
title: Momentum Turnover Ablation / Walk-Forward (Candidate 11)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/open
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-momentum-turnover-ablation-methodology-pre-committed-2026-07, 2026-09-17-momentum-turnover-ablation-results, 2026-09-17-momentum-turnover-ablation-follow-up-diagnostics-pre-committ, 2026-09-17-momentum-turnover-ablation-follow-up-diagnostics, 2026-09-17-momentum-turnover-walk-forward-methodology-pre-committed-202
---

# Momentum Turnover Ablation / Walk-Forward (Candidate 11)

> [!abstract] Compiled page
> Written from `[[2026-09-17-momentum-turnover-ablation-methodology-pre-committed-2026-07]]`, `[[2026-09-17-momentum-turnover-ablation-results]]`, `[[2026-09-17-momentum-turnover-ablation-follow-up-diagnostics-pre-committ]]`, `[[2026-09-17-momentum-turnover-ablation-follow-up-diagnostics]]`, and `[[2026-09-17-momentum-turnover-walk-forward-methodology-pre-committed-202]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A diagnostic ablation, not a strategy pre-registration: [[rs-momentum-rotation-s8-3]] underperformed Nifty Alpha 50 — a real, rules-based momentum index — by a wide margin despite both being momentum strategies on a similar universe. This asks how much of that gap closes if turnover alone is reduced (weekly → quarterly rebalance), holding the ranking formula, universe, costs, and capital fixed.

## Mechanics

Everything from S8-3 held fixed (52-week-high ranking, top 20, point-in-time Nifty 500, rank-dropout-only exit, `DELIVERY_COST_MODEL`, ₹1,000,000/₹50,000-position sizing) except rebalance cadence, changed from weekly to the last NIFTY trading day of each calendar quarter.

## Verdict — in-sample ablation: real, but partial, gap closure

| | Weekly (S8-3 control) | Quarterly (this ablation) |
|---|---|---|
| CAGR | 4.0% | 10.2% |
| Sharpe | 0.34 | 0.81 |
| Trades | 2034 | 244 |

Closes ~80% of the Sharpe gap and ~40% of the CAGR gap to Nifty Alpha 50 (19.5% CAGR) `[[2026-09-17-momentum-turnover-ablation-results]]`. Two follow-up diagnostics — restricting to the period where point-in-time universe data is genuinely real (2023-09-29 onward: CAGR 10.0%, Sharpe 0.77, barely different from the full-window number) and a first-half/second-half stability split (no material degradation flag) — both came back clean `[[2026-09-17-momentum-turnover-ablation-follow-up-diagnostics]]`.

Despite the clean diagnostics, this was **not promoted to a pre-registered strategy candidate**: everything is in-sample, drawn from one ~3-year uptrend window with no bear leg, and the 244 trades come from only 14 correlated quarterly decisions, not independent draws. A genuine out-of-sample backtest was found infeasible (no untouched historical slice exists that wouldn't reintroduce survivorship bias).

## Current status: OPEN — live forward paper walk-forward

Deployed as a daily-gated, quarter-triggered paper simulation on the production VM (`~/.quantos/paper_rotation_positions.json`, never touches real capital, never calls `place_order()`), using real, never-backtested prices going forward from the methodology's commit date `[[2026-09-17-momentum-turnover-walk-forward-methodology-pre-committed-202]]`.

**Pass/inconclusive/fail bar, fixed before any live quarter exists**: PASS if OOS Sharpe > 0.5; INCONCLUSIVE if between 0.34 (the weekly control) and 0.5; FAIL if ≤0.34. **No verdict before at least 4 completed quarters** (~1 year) — a good or bad first quarter is one data point, not a sample.

## Relation to other concepts

Directly downstream of [[rs-momentum-rotation-s8-3]]'s disappointing capital-tracked result. [[ml-factor-combination-candidate-16]] is a separate, parallel attempt to close the same Alpha-50 gap by combining factors rather than reducing turnover — both trace back to the same diagnosis.
