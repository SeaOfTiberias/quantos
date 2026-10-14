---
title: Darvas Trailing Stop/Target
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: darvas-trailing-stop
candidate: "Darvas line 2 (trailing stop)"
family: breakout
instrument: equity-cash
status: closed
verdict: FAIL
first_tested: 2026-09-22
verdict_date: 2026-09-22
profit_factor: 1.00
sharpe: 0.01
trades: 210
bar: "Bucket B passes PF > 1 and Sharpe > 0.5 (Stressed) on mining AND holdout; Bucket A does not on holdout"
headline: "Trailing the stop and target to each new higher box improved every cell, but Bucket B's mining set landed exactly at breakeven (PF 1.00, Sharpe 0.01)."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-darvas-trailing-stop-backtest-pre-committed-2026-09-22-befor, 2026-10-13-darvas-trailing-stop-backtest-results
---

# Darvas Trailing Stop/Target

> [!abstract] Compiled page
> Written from `[[2026-10-13-darvas-trailing-stop-backtest-pre-committed-2026-09-22-befor]]` and `[[2026-10-13-darvas-trailing-stop-backtest-results]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

The second link in the Darvas chain. It is a single-variable change on [[darvas-box-width]]: the exit rule is the only difference. Prompted by WELCORP's 2025-05-30 breakout (35.5% width). Its static stop closed it at −5.2% after 17 days, and the stock went on to +193.7% over 15 months. The hypothesis is that the static stop clips winners before a trend has room to develop. The methodology warns against concluding anything from that one stock `[[2026-10-13-darvas-trailing-stop-backtest-pre-committed-2026-09-22-befor]]`.

## Mechanics

Each day a trade is open, `analyse_symbol` is re-run. If it reports a box with a higher ceiling, the stop rises to that box's `sl_price` and the target to its `mm_target`. Neither is ever lowered. There is **no time stop**. Trades still open when the data ends are marked to market and **included** in the metrics, because excluding them would discard exactly the long-running winners this variant exists to capture. `core/darvas/box.py::next_trailing_stop` was deliberately not reused: its 8% box cap belongs to a different, intraday box definition. Universe, window, buckets, costs, split and verdict rules are copied unchanged from [[darvas-box-width]] `[[2026-10-13-darvas-trailing-stop-backtest-pre-committed-2026-09-22-befor]]`.

## Verdict

**FAIL**, the closest miss in the chain `[[2026-10-13-darvas-trailing-stop-backtest-results]]`:

| Bucket | Mining (Stressed) | Holdout (Stressed) |
|---|---|---|
| A ≤ 35% | 1445 trades, PF 0.87, Sharpe −0.70 | 340 trades, PF 0.96, Sharpe −0.23 |
| B 35–50% | 210 trades, PF 1.00, Sharpe 0.01 | 67 trades, PF 1.27, Sharpe 1.07 |
| C 50–100% | 157 trades, PF 0.75, Sharpe −1.31 | 39 trades, PF 1.12, Sharpe 0.41 |

Bucket B passed the holdout but not the mining set, and both were required. Fourteen trades were open at the end of the data, marked to market at an average unrealised +3.6%.

## Relation to other concepts

- A single-variable descendant of [[darvas-box-width]]. Every cell improved, which points to the exit rule, not the entries, as the binding problem.
- [[darvas-atr-stop-bucket-b]] keeps this exact trailing logic and changes only the stop distance. Its methodology cites the finding that 87–90% of trades here exit by stop.
