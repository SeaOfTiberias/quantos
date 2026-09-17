---
title: F&O Monthly Expiry-Day Effect (Candidate 13, Gut-Check)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/weak
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-f-o-monthly-expiry-day-effect-gut-check-methodology-pre-comm, 2026-09-17-f-o-monthly-expiry-day-effect-gut-check
---

# F&O Monthly Expiry-Day Effect (Candidate 13, Gut-Check)

> [!abstract] Compiled page
> Written from `[[2026-09-17-f-o-monthly-expiry-day-effect-gut-check-methodology-pre-comm]]` and `[[2026-09-17-f-o-monthly-expiry-day-effect-gut-check]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A cheap, descriptive gut-check (not a backtest — no costs, no position sizing) for whether NIFTY shows elevated volatility or price dislocation around its own monthly expiry, following a 22-year academic study finding such a pattern on NSE derivatives. Deliberately checked at gut-check stage before designing a tradeable strategy and cost model around a pattern that might not exist in this project's much shorter data window.

## Mechanics

NIFTY spot from the cached NSE F&O bhavcopy, 2024-01-01 to 2026-07-24 (631 trading days, 31 expiries — expiry weekday itself changed mid-window, last-Thursday through 2025-08-31 then last-Tuesday per SEBI circular). Four day-groups compared by mean |daily return| (a realized-vol proxy, since the literature's claim is about dislocation, not direction): `expiry`, `pre_expiry`, `post_expiry`, `other` (baseline).

## Verdict

**Weak / inconsistent** — no clean signal `[[2026-09-17-f-o-monthly-expiry-day-effect-gut-check]]`:

| Group | n | Mean \|return\| % | Gap vs. `other` |
|---|---|---|---|
| expiry | 31 | 0.555 | -10.0% relative |
| pre_expiry | 31 | 0.604 | -2.0% relative |
| post_expiry | 30 | 0.732 | **+18.7% relative** |
| other | 538 | 0.616 | — |

Expiry day itself is *quieter*, not louder, than an ordinary day — the opposite of the academic literature's finding. Only `post_expiry` shows an elevated read, on a thin n=30. With only ~31 real expiries in the window (an order of magnitude smaller sample than the 22-year study), this reads as inconclusive rather than a clean confirmation or refutation — the gut-check did not clear the bar for a full pre-registered backtest, and none was built.

## Relation to other concepts

Same "cheap descriptive check first" sequencing discipline this project also applied to the PEAD and index-reconstitution candidates (neither reached a full backtest either) — a thin or flat gut-check is treated as a legitimate reason to stop before building position sizing and a cost model around a pattern that may not be there.
