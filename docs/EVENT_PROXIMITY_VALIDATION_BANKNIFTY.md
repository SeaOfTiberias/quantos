# BANKNIFTY Known-Event Proximity Validation

Methodology: docs/EVENT_PROXIMITY_METHODOLOGY.md. Replayed 612 days (2024-01-31 to 2026-07-27), 592 scored with a full forward window.

## Pooled: RBI + Budget vs non-event days

| Group | n | Mean fwd 20d RV |
|---|---|---|
| Event days (±1d) | 43 | 13.57 |
| Non-event days | 549 | 14.69 |

## Secondary breakdown: RBI-only vs non-RBI days

| Group | n | Mean fwd 20d RV |
|---|---|---|
| RBI days (±1d) | 35 | 13.52 |
| Non-RBI days | 557 | 14.67 |

## Verdict

- Pooled (RBI+Budget) event days (13.57, n=43) vs non-event days (14.69, n=549): gap = -1.11 vol points.
- Per docs/EVENT_PROXIMITY_METHODOLOGY.md's pass bar: FAIL (event days must show materially higher mean fwd RV).
- RBI-only consistency check: gap = -1.15 vol points (n=35 RBI days) — reported alongside, not independently required to pass.
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and every prior signal report in this project.
