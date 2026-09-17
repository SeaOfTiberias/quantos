---
title: IV-minus-RV Vol Spread
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
  - vol-conditioning
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-iv-minus-rv-vol-spread-methodology-pre-committed-2026-07-24, 2026-09-17-iv-minus-rv-vol-spread-validation
---

# IV-minus-RV Vol Spread

> [!abstract] Compiled page
> Written from `[[2026-09-17-iv-minus-rv-vol-spread-methodology-pre-committed-2026-07-24]]` and `[[2026-09-17-iv-minus-rv-vol-spread-validation]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

The second of five vol-conditioning attempts, built after [[regime-classifier-s8-1]]'s structural diagnosis: VIX scored as an absolute level never checks whether that level was actually justified by what volatility did next. This signal instead asks whether a *spread* between implied and realized vol predicts whether an implied-vol premium will actually be earned.

## Mechanics

`Spread_t = India VIX_t − trailing 20-day realized vol_t` (a plain difference, chosen over a ratio for auditability). Replayed over 5 years, bucketed into quintiles of the spread distribution (data-driven cut points, not hand-picked). For each bucket: mean earned premium (`IV_t − forward 20-day realized vol`) and % of days the premium was actually earned.

## Verdict

**FAIL** — no separation in the expected direction `[[2026-09-17-iv-minus-rv-vol-spread-validation]]`:

| Bucket | n | Mean spread | Mean earned premium | % premium earned |
|---|---|---|---|---|
| Q1 (lowest spread) | 245 | -2.35 | +3.04 | 82% |
| Q5 (highest spread) | 246 | +6.45 | +2.51 | 76% |

The signal claims Q5 ("richest" spread) should show a *larger* earned premium and hit rate than Q1 ("cheapest"). Both go the wrong way — Q5's earned premium is lower (-0.53 vol points) and its hit rate is lower (-6pp) than Q1's, on 1228 replayed days (2021-07-13 to 2026-07-24).

## Relation to other concepts

Closed line: this is attempt 2 of 5 in the [[strategy-search|vol-conditioning search]] ([[regime-classifier-s8-1]] → this → [[nifty-banknifty-option-skew]] → [[atm-iv-term-structure]] → [[event-proximity-vol]]), all independently failed. Explicitly not checked against [[vrp-short-strangle]]'s trade data before this validation's own verdict locked, per the project's standing anti-rescue-narrative rule.
