---
title: Known-Event (RBI/Budget) Proximity vs Forward Volatility
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
  - vol-conditioning
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-known-event-proximity-vs-forward-realized-vol-methodology-pr, 2026-09-17-nifty-known-event-proximity-validation, 2026-09-17-banknifty-known-event-proximity-validation
---

# Known-Event (RBI/Budget) Proximity vs Forward Volatility

> [!abstract] Compiled page
> Written from `[[2026-09-17-known-event-proximity-vs-forward-realized-vol-methodology-pr]]`, `[[2026-09-17-nifty-known-event-proximity-validation]]`, and `[[2026-09-17-banknifty-known-event-proximity-validation]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The fifth and final vol-conditioning attempt, deliberately different in kind from the four continuous-statistic attempts that preceded it: a binary flag for calendar proximity to publicly known, advance-published event dates (RBI rate decisions, the Union Budget) rather than an inferred statistic bucketed into quintiles. Scoped after the four continuous attempts closed 4-for-4 on the same non-monotonic "smile" artifact — a structurally different construction was judged the only way to know whether that artifact was about the underlying statistics or something real about NSE volatility around known events.

## Mechanics

A trading day is an "event day" if within ±1 calendar day of a sourced RBI MPC resolution date or Union Budget date, 2024-2026 (dates verified against RBI's own press releases and Budget coverage, not assumed from a fixed weekday rule). Compared: mean forward 20-day realized vol, event days vs non-event days, pooled RBI+Budget as the primary cut and RBI-only as a secondary consistency check.

## Verdict

**FAIL — wrong direction, both underlyings**, and a clean, distinct failure shape from the other four (Fable-confirmed not the same non-monotonic-smile artifact) `[[2026-09-17-nifty-known-event-proximity-validation]]`:

| | Event days (n) | Non-event days (n) | Gap |
|---|---|---|---|
| NIFTY | 11.13 (43) | 12.58 (549) | **-1.45** vol points |
| BankNifty | 13.57 (43) | 14.69 (549) | **-1.11** vol points |

Days near a known RBI or Budget event show *lower* forward realized volatility than ordinary days, not higher — the opposite of the hypothesis. RBI-only consistency checks show the same wrong-direction gap on both underlyings.

## Relation to other concepts

This closes the vol/regime-conditioning search at 5-for-5 failures across two structurally different construction types (four continuous statistics: [[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]]; one binary calendar flag: this page). A positive result here would NOT have vindicated the closed continuous-statistic line (different construction, different failure mode) — the negative result here is read as a much stronger basis for concluding no such signal is findable in this project's available data than any single failure alone, and this line of work is treated as closed rather than seeking a sixth construction.
