---
title: Trade Watcher (Discretionary Exit Alerts)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/tool
strategy_id: trade-watcher
candidate: "—"
family: discretionary-aid
instrument: index-options
status: live-tool
verdict: N/A
first_tested: 2026-10-07
verdict_date:
profit_factor:
sharpe:
trades:
bar: "none — an aid for the user's own trades, not a tested strategy"
headline: "Alerts-only exit manager for the user's manual option trades (Telegram, no order code); stage 2 real stop orders need an explicit go-ahead."
capital: "the user's own manual positions"
next_gate: "Stage 2 (real stop orders at the broker) only with the user's explicit go-ahead after stage 1 proves itself"
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-strategy-status-snapshot-2026-10-13
---

# Trade Watcher (Discretionary Exit Alerts)

> [!abstract] Compiled page
> Written from `[[2026-10-13-strategy-status-snapshot-2026-10-13]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

Not a strategy with a verdict. It is a running aid for the user's own manually entered option trades. It watches the positions and sends Telegram exit alerts; it contains no order-placing code. Running since 2026-10-07 `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

## Status and next gate

Stage 1 (alerts only) is live. Stage 2, real stop orders at the broker, comes only with the user's explicit go-ahead after stage 1 proves itself `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

The snapshot source does not record the exit rules themselves (initial stop, lock, trail). They live in the VM's `agent/config.yaml` under `trade_watcher`. Ingest a rules doc if this page should carry them.

## Relation to other concepts

[[fno-screener]] supplies the candidates the user may buy manually; this watcher then manages the exit. Neither places orders. Both sit alongside the one systematic strategy running on paper, [[darvas-atr-stop-bucket-b]].
