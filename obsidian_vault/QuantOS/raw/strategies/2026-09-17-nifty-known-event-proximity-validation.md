---
title: 'NIFTY Known-Event Proximity Validation'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\EVENT_PROXIMITY_VALIDATION.md'
checksum: ba8a60f99129291c3f238e40912992e56d97d3f158fcebbf5ecd13e1ed7abc8e
body_checksum: 1734b88b367358a3f5d11846c4a2c23792e3c34262655c8dd502ab2dc9fc83c2
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# NIFTY Known-Event Proximity Validation

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\EVENT_PROXIMITY_VALIDATION.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/EVENT_PROXIMITY_METHODOLOGY.md. Replayed 612 days (2024-01-31 to 2026-07-27), 592 scored with a full forward window.

## Pooled: RBI + Budget vs non-event days

| Group | n | Mean fwd 20d RV |
|---|---|---|
| Event days (±1d) | 43 | 11.13 |
| Non-event days | 549 | 12.58 |

## Secondary breakdown: RBI-only vs non-RBI days

| Group | n | Mean fwd 20d RV |
|---|---|---|
| RBI days (±1d) | 35 | 10.82 |
| Non-RBI days | 557 | 12.58 |

## Verdict

- Pooled (RBI+Budget) event days (11.13, n=43) vs non-event days (12.58, n=549): gap = -1.45 vol points.
- Per docs/EVENT_PROXIMITY_METHODOLOGY.md's pass bar: FAIL (event days must show materially higher mean fwd RV).
- RBI-only consistency check: gap = -1.76 vol points (n=35 RBI days) — reported alongside, not independently required to pass.
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and every prior signal report in this project.
