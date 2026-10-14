---
title: Darvas Box-Width Buckets (Static Exit)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: darvas-box-width
candidate: "Darvas line 1 (box width)"
family: breakout
instrument: equity-cash
status: closed
verdict: FAIL
first_tested: 2026-09-22
verdict_date: 2026-09-22
profit_factor: 0.69
sharpe: -1.77
trades: 210
bar: "Bucket B passes PF > 1 and Sharpe > 0.5 (Stressed) on mining AND holdout; Bucket A does not on holdout"
headline: "Wider Darvas boxes looked better on raw forward returns, but every width bucket loses money once a real stop, target and costs are applied."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-darvas-box-width-sensitivity-pre-committed-2026-09-22-before, 2026-10-13-darvas-box-width-sensitivity-results, 2026-10-13-darvas-box-width-backtest-pre-committed-2026-09-22-before-an, 2026-10-13-darvas-box-width-backtest-results
---

# Darvas Box-Width Buckets (Static Exit)

> [!abstract] Compiled page
> Written from `[[2026-10-13-darvas-box-width-sensitivity-pre-committed-2026-09-22-before]]`, `[[2026-10-13-darvas-box-width-sensitivity-results]]`, `[[2026-10-13-darvas-box-width-backtest-pre-committed-2026-09-22-before-an]]` and `[[2026-10-13-darvas-box-width-backtest-results]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

The first link in a three-step chain asking whether the live Darvas weekly-discovery scanner's `max_box_width` cutoff (35%) hides good breakouts. It started from one stock: WELSPUNLIV's April breakout, a roughly 90% mover, never showed on the Breakout Candidates panel because its weekly box was 36.3% wide. All 29 then-current Nifty 500 momentum leaders were excluded by the same cutoff, at widths of 35.6% to 131.8%. The methodology notes that this alone proves nothing, because stocks picked for being winners will have wide ranges in hindsight `[[2026-10-13-darvas-box-width-sensitivity-pre-committed-2026-09-22-before]]`.

## Mechanics

Width buckets, fixed before any data was pulled: **A** ≤ 35% (control, the live default), **B** 35–50%, **C** 50–100%, with > 100% excluded as trend rather than consolidation. The signal is `analyse_symbol` from `core/darvas/weekly_discovery.py`, run unmodified with `max_box_width=200` so that boxes of any width get classified `[[2026-10-13-darvas-box-width-sensitivity-pre-committed-2026-09-22-before]]`.

**Step 1, gut-check** (no costs, no stops). A systematic sample of every 7th Nifty 500 symbol (73), 2024-09 to 2026-09, gave 181 breakouts. Raw forward returns favoured Bucket B over the control:

| Horizon | A (≤35%) mean / hit rate | B (35–50%) mean / hit rate |
|---|---|---|
| 4 weeks | −1.77% / 38.1% (n=147) | −0.69% / 61.1% (n=18) |
| 8 weeks | −1.93% / 41.5% (n=135) | +4.45% / 53.3% (n=15) |
| 12 weeks | −2.97% / 37.9% (n=132) | +3.22% / 50.0% (n=14) |

`[[2026-10-13-darvas-box-width-sensitivity-results]]`

**Step 2, managed backtest.** The universe was the full point-in-time Nifty 500 (648 symbols attempted, 63 errored), over 2023-09-22 to 2026-09-22, with an 80/20 time split at 2026-02-15. Entry at the next day's open. Stop = `sl_price` (2% below the box ceiling); target = `mm_target` (one box height above the ceiling); a 60-day time stop. Delivery cost model, with Stressed (+15 bps a leg) gating the verdict. Point-in-time membership was used because wide-box names are the likeliest to blow up and leave the index, which would flatter Bucket B `[[2026-10-13-darvas-box-width-backtest-pre-committed-2026-09-22-before-an]]`.

## Verdict

**FAIL.** No bucket makes money under Stressed costs `[[2026-10-13-darvas-box-width-backtest-results]]`:

| Bucket | Mining (Stressed) | Holdout (Stressed) |
|---|---|---|
| A ≤ 35% | 1445 trades, PF 0.74, Sharpe −1.55 | 323 trades, PF 0.79, Sharpe −1.22 |
| B 35–50% | 210 trades, PF 0.69, Sharpe −1.77 | 63 trades, PF 0.86, Sharpe −0.78 |
| C 50–100% | 157 trades, PF 0.48, Sharpe −3.29 | 35 trades, PF 0.83, Sharpe −0.85 |

Win rates of 11–29% across buckets prompted the next question: were the static stops cutting winners short?

## Relation to other concepts

- The original [[darvas-sepa-s7-3]] Darvas backtest failed earlier on a different sample. This chain reopens the Darvas signal from the box-width angle.
- Its low win rates motivated [[darvas-trailing-stop]], which changes only the exit rule and keeps everything else identical.
- That chain ends at [[darvas-atr-stop-bucket-b]], the one Darvas variant that passed.
