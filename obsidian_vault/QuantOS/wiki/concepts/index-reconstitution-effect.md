---
title: Index Reconstitution Effect
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/closed
strategy_id: index-reconstitution-effect
candidate: "—"
family: event-drift
instrument: equity-cash
status: closed
verdict: FAIL
first_tested:
verdict_date: 2026-09-25
profit_factor:
sharpe:
trades:
bar: "mechanical feasibility"
headline: "Closed as untradeable: the required short leg has no F&O coverage, so the strategy cannot be run as designed."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-quantos-full-project-state-for-external-review
---

# Index Reconstitution Effect

> [!abstract] Compiled page
> Written from `[[2026-10-13-quantos-full-project-state-for-external-review]]` on 2026-10-13. **Thin record**: the only vault source is one line of the 2026-09-25 project-state review. Context and retrieval only — rules in this layer never execute.

## Definition

Trading the price effect around index additions and deletions on NSE equities. The project-state review lists it as **CLOSED** because "the required short leg has zero F&O (derivatives) coverage — mechanically untradeable as designed" `[[2026-10-13-quantos-full-project-state-for-external-review]]`.

Recorded here as a FAIL on feasibility, not on returns: no edge was measured either way. `verdict_date` is the date of the review that records it.

## Relation to other concepts

The same constraint (no overnight cash shorts for retail in India) shaped [[pairs-trading-candidate-12]] and [[statarb-residual-mean-reversion]], which put their short legs in stock futures instead; per the source, that route was not available for this strategy's short leg.
