---
title: Sector-Cointegrated Pairs Trading v2, Bug-Fixed (Candidate 17)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-pairs-trading-v2-roll-adjustment-corporate-action-fix-pre-co, 2026-09-17-pairs-trading-v2-backtest-results-candidate-17
---

# Sector-Cointegrated Pairs Trading v2, Bug-Fixed (Candidate 17)

> [!abstract] Compiled page
> Written from `[[2026-09-17-pairs-trading-v2-roll-adjustment-corporate-action-fix-pre-co]]` and `[[2026-09-17-pairs-trading-v2-backtest-results-candidate-17]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A bug-fix re-run of [[pairs-trading-candidate-12]], not a new hypothesis. An independent review confirmed candidate 12's FAIL was trustworthy but found two real construction bugs — no corporate-action jump guard, and unadjusted futures-roll splicing inflating the frozen formation-window spread estimates — and recommended fixing both before any future pairs candidate. Every other design choice (universe, cointegration test, 6-month/3-month walk-forward, entry/exit rules, cost model) is held identical to candidate 12.

## Mechanics

- **Fix 1**: reuses the reconstitution gut-check's corporate-action jump guard (a >2x or <0.5x day-over-day ratio) — any pair with either leg flagged in either window is excluded from that fold.
- **Fix 2**: a forward-built, point-in-time-safe futures-roll adjustment (adjustment at day `t` depends only on rolls that already happened by `t`) — used for the cointegration test and the trading-window z-score, but never for actual fill prices/P&L/costs, which always use the raw, unadjusted close (a trader cannot fill at a synthetic price).

## Verdict

**FAIL, still** — both fixes measurably improved the numbers without flipping the verdict `[[2026-09-17-pairs-trading-v2-backtest-results-candidate-17]]`:

| | v2 (bug-fixed) | v1 (candidate 12, original) |
|---|---|---|
| Trades | 4535 | 4705 |
| Net P&L | +₹2,349,508 | -₹3,819,293 |
| Profit factor | 1.04 | 0.94 |
| Sharpe | 0.14 | -0.17 |

Net P&L flips from a real loss to a real gain, and profit factor crosses 1.0 — but Sharpe (0.14) remains far short of the 0.5 bar. 405 pairs were excluded across all folds by the corporate-action guard; zero futures-roll seams were left unadjusted. Folds 6-8 (candidate 12's original collapse) still show the weakest performance (PF 0.88, 0.83, 0.87) even after both fixes — consistent with a genuine regime shift in those quarters rather than either bug explaining the collapse.

## Relation to other concepts

Confirms [[pairs-trading-candidate-12]]'s FAIL was not an artifact of these two specific bugs. An intra-window adaptive hedge-ratio re-estimation was explicitly named as the next candidate hypothesis if this re-run didn't resolve the fold 6-8 question — not built as of this writing.
