---
title: 52-Week-High RS Momentum Rotation (S8-3)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: rs-momentum-rotation-s8-3
candidate: "S8-3"
family: momentum
instrument: equity-cash
status: retired
verdict: FAIL
first_tested: 2026-07-19
verdict_date: 2026-07-23
profit_factor: 1.18
sharpe: 0.34
trades: 2104
bar: "Beat Nifty 500 and Nifty Alpha 50 as a capital-tracked account (PF is pooled-trade; Sharpe is the ₹10L account's)"
headline: "Passed the pooled-trade screen but lost to Nifty 500 (−15.6 pt) and Nifty Alpha 50 (−64.6 pt) once survivorship-corrected; weekly dry run and pilot switched off 2026-10-12."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-s8-3-momentum-backtest-methodology-pre-committed-2026-07-19, 2026-09-17-s8-3-52-week-high-rs-momentum-backtest, 2026-09-17-s8-3-rotation-real-capital-tracked-equity-curve, 2026-10-13-quantos-full-project-state-for-external-review, 2026-10-13-strategy-status-snapshot-2026-10-13
---

# 52-Week-High RS Momentum Rotation (S8-3)

> [!abstract] Compiled page
> Written from `[[2026-09-17-s8-3-momentum-backtest-methodology-pre-committed-2026-07-19]]`, `[[2026-09-17-s8-3-52-week-high-rs-momentum-backtest]]`, and `[[2026-09-17-s8-3-rotation-real-capital-tracked-equity-curve]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A documented academic anomaly (George & Hwang 2004: stocks near their 52-week high tend to keep outperforming) applied as a weekly rotation across the full Nifty 500. Picked by Fable's post-Darvas review as the strongest remaining candidate over Darvas's own weaker single-name-breakout citation.

## Mechanics

- **Ranking**: `nearness_score = daily_close / rolling_252_trading_day_high`. Top 20 by score, rebalanced weekly (last NIFTY trading day of each ISO week).
- **Entry/exit**: pure rotation, no anti-chattering buffer — a symbol enters the week it first reaches the top 20, exits the week it first leaves.
- **Cost model**: delivery-style (₹0 brokerage, approximated STT, real stamp duty), 10bps/leg slippage.

## Verdict

**Mechanically PASSES the pooled-trade bar, but FAILS against both real benchmarks once capital-tracked with a point-in-time, survivorship-bias-corrected universe** `[[2026-09-17-s8-3-rotation-real-capital-tracked-equity-curve]]`:

- Pooled-trade stats (2104 trades): PF 1.18, Sharpe 0.63 — technically clears `has_positive_edge`.
- Real ₹1,000,000 capital-tracked account: CAGR 4.0%, Sharpe 0.34, max drawdown 26.2%.
- vs. Nifty 500 buy-and-hold: **-15.6pt** total return, **-4.5pt** CAGR.
- vs. Nifty Alpha 50 buy-and-hold (a real, rules-based momentum index): **-64.6pt** total return, **-16.5pt** CAGR.

A pooled per-trade PASS is not the same question as "does this beat a passive alternative" — this candidate answers yes to the first and no, decisively, to the second. The gap to Nifty Alpha 50 is the direct motivation for [[momentum-turnover-candidate-11]]'s ablation.

## Status

Retired as a strategy candidate on 2026-08-18 `[[2026-10-13-quantos-full-project-state-for-external-review]]`. Its weekly dry run kept running from the agent until **2026-10-12**, when both the weekly dry run (`rotation.enabled`) and the real-capital pilot (`rotation_pilot.enabled`) were switched off. The dry run had never tracked holdings, so its log is meaningless. The quarterly paper walk-forward of [[momentum-turnover-candidate-11]] supersedes it `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

## Relation to other concepts

- Directly motivated [[momentum-turnover-candidate-11]] (does reducing rebalance frequency close the gap to Alpha 50?) and [[ml-factor-combination-candidate-16]] (does combining this ranking with other factors beat it?) — both are explicit attempts to fix what this candidate's own equity curve exposed.
- [[regime-filtered-dual-momentum-s1]] is a structurally different momentum design (Nifty 200, dual-momentum composite, ATR-based exits) that inherits real risk from this candidate's own disappointing result, disclosed up front in its own methodology doc.
