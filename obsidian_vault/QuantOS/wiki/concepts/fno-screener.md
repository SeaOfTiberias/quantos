---
title: F&O Screener (Evening Call/Put Candidates)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/tool
strategy_id: fno-screener
candidate: "—"
family: discretionary-aid
instrument: stock-options
status: live-tool
verdict: N/A
first_tested: 2026-10-12
verdict_date:
profit_factor:
sharpe:
trades:
bar: "none yet — hit rate to be reviewed once 20–30 candidates exist"
headline: "Evening Telegram list of stock call/put candidates for discretionary 1–5 day swings; no orders; first live run 2026-10-12."
capital: "none (the user trades candidates manually)"
next_gate: "Review the hit rate once 20–30 candidates exist"
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-strategy-status-snapshot-2026-10-13
---

# F&O Screener (Evening Call/Put Candidates)

> [!abstract] Compiled page
> Written from `[[2026-10-13-strategy-status-snapshot-2026-10-13]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

A discretionary aid, not a tested strategy. Every weekday at 18:15 IST it sends a Telegram list of stock call and put candidates. It places no orders; the user buys manually. First live run 2026-10-12 `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

## Status and next gate

Live. Review the hit rate once 20–30 candidates exist `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`. Until then it has no measured edge, and its candidates should be read as a shortlist, not a signal.

The snapshot source does not record how candidates or contracts are selected. Ingest the screener's design notes if this page should carry them.

## Relation to other concepts

Exits on trades the user takes from this list are managed by [[trade-watcher]].
