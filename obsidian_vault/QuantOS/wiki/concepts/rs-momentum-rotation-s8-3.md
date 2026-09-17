---
title: 52-Week-High RS Momentum Rotation (S8-3)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-s8-3-momentum-backtest-methodology-pre-committed-2026-07-19, 2026-09-17-s8-3-52-week-high-rs-momentum-backtest, 2026-09-17-s8-3-rotation-real-capital-tracked-equity-curve
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

## Relation to other concepts

- Directly motivated [[momentum-turnover-candidate-11]] (does reducing rebalance frequency close the gap to Alpha 50?) and [[ml-factor-combination-candidate-16]] (does combining this ranking with other factors beat it?) — both are explicit attempts to fix what this candidate's own equity curve exposed.
- [[regime-filtered-dual-momentum-s1]] is a structurally different momentum design (Nifty 200, dual-momentum composite, ATR-based exits) that inherits real risk from this candidate's own disappointing result, disclosed up front in its own methodology doc.
