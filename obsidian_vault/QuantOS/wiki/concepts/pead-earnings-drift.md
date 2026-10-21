---
title: PEAD (Post-Earnings Announcement Drift)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/shelved
strategy_id: pead-earnings-drift
candidate: "—"
family: event-drift
instrument: equity-cash
status: shelved
verdict: INCONCLUSIVE
first_tested:
verdict_date: 2026-09-25
profit_factor:
sharpe:
trades:
bar: "not recorded in a vault source"
headline: "Shelved as inconclusive: not enough new data to test it properly, so it is neither a clean fail nor adoptable."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-quantos-full-project-state-for-external-review
---

# PEAD (Post-Earnings Announcement Drift)

> [!abstract] Compiled page
> Written from `[[2026-10-13-quantos-full-project-state-for-external-review]]` on 2026-10-13. **Thin record**: the only vault source is one line of the 2026-09-25 project-state review. The PEAD pipeline's own docs have not been ingested. Context and retrieval only — rules in this layer never execute.

## Definition

The post-earnings-announcement drift anomaly, tested on NSE equities. The project-state review lists it as **SHELVED, inconclusive**: "No new data available to test it properly; not a clean fail, not adoptable either" `[[2026-10-13-quantos-full-project-state-for-external-review]]`.

## What the vault does not yet hold

No methodology, sample or numbers. `verdict_date` is the date of the review that records the status, not the date PEAD was shelved. Ingest PEAD's own docs to complete this page.

## Relation to other concepts

[[earnings-gap-drift]] (2026-10-21) tested a price/volume proxy for the same anomaly — ±5% days on ≥ 4× volume, 2016–2026 — and found no long-side drift for a next-day entry and only a small, fading short-side drift. It does not settle the fundamental-surprise version shelved here, which needs results data.

[[regime-filtered-dual-momentum-s1]]'s page records that an earnings-beat breakout proposal from the same session was rejected outright as "PEAD's already-shelved anomaly with a new execution layer".
