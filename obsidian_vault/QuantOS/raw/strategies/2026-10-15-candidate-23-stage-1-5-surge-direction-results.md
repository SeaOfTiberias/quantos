---
title: 'Candidate 23 Stage 1 — +5% Surge Direction — Results'
ingested: 2026-10-15
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\SURGE_DIRECTION_RESULTS.md'
checksum: 780ede361e47590cd27959d58f49bb53fd53cd20ed1d89e6a4a376abdb76ad5b
body_checksum: 14816b4d56dd176d915a8aa0a7e0bcb158c59299a73e7214b5ff120b543847f3
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Candidate 23 Stage 1 — +5% Surge Direction — Results

> [!info] Ingested source
> Filed 2026-10-15 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\SURGE_DIRECTION_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/SURGE_DIRECTION_METHODOLOGY.md (pre-registered 2026-10-15). Data 2019-02-11 to 2026-10-12, 347 F&O symbols (near-month futures, roll-adjusted). X(h) = forward return minus the equal-weighted F&O universe over the same days; t-stats cluster by event date. No costs, no option prices.

## Verdict: **PASS**

- **breakout52=FALSE** → continuation → bull call spread candidate (mining +0.49%, t 2.20; holdout +0.98%, t 3.02).

Events: 3206 (mining 2563 before 2025-01-07, holdout 643 from 2025-01-07).
Excluded: history 2061, forward data 24, corporate-action jump 3, 10-day cooldown 1401.

## Q1 — all surges

| Subset | Events | Dates | Mean X(5), date-clustered | t | Median X(5) | P(R8 ≥ 4%) | P(R8 ≥ 7%) | P(R8 ≤ 0) |
|---|---|---|---|---|---|---|---|---|
| All — mining | 2563 | 773 | +0.34% | 1.77 | -0.25% | 31.4% | 19.3% | 45.7% |
| All — holdout | 643 | 211 | +0.84% | 2.83 | +0.16% | 30.9% | 14.5% | 42.1% |
| All — full | 3206 | 984 | +0.45% | 2.72 | -0.15% | 31.3% | 18.3% | 45.0% |

Baseline, all stock-days (n=343001): P(R8 ≥ 4%) 22.8%, P(R8 ≥ 7%) 11.1%, P(R8 ≤ 0) 48.8%.

Drift profile, all events (event-mean X(h)): h=1: +0.06%, h=3: +0.20%, h=5: +0.28%, h=8: +0.25%, h=10: +0.28%.

Events per year: 2020: 792, 2021: 473, 2022: 469, 2023: 358, 2024: 464, 2025: 299, 2026: 351.

Mean X(5) by year: 2020: +0.23%, 2021: +0.64%, 2022: -0.18%, 2023: +0.53%, 2024: -0.11%, 2025: +0.19%, 2026: +0.86%.

## Q2 — selector (mining → holdout)

| Subset | Mining n | Mining mean X(5) | Mining t | Holdout n | Holdout mean X(5) | Holdout t | Result |
|---|---|---|---|---|---|---|---|
| results=TRUE | 309 | +0.33% | 1.04 | 123 | +0.46% | 1.36 | mining |t| 1.04 < 2.0 |
| results=FALSE | 2254 | +0.27% | 1.28 | 520 | +1.07% | 3.11 | mining |t| 1.28 < 2.0 |
| breakout52=TRUE | 557 | -0.10% | -0.41 | 78 | +0.26% | 0.54 | mining |t| 0.41 < 2.0 |
| breakout52=FALSE | 2006 | +0.49% | 2.20 | 565 | +0.98% | 3.02 | **BRANCH (continuation)** |
| big_z=TRUE | 1204 | +0.37% | 0.98 | 331 | +0.36% | 1.47 | mining |t| 0.98 < 2.0 |
| big_z=FALSE | 1359 | +0.35% | 1.52 | 312 | +1.37% | 2.78 | mining |t| 1.52 < 2.0 |
| market_day=TRUE | 1410 | +0.34% | 1.75 | 358 | +1.26% | 3.97 | mining |t| 1.75 < 2.0 |
| market_day=FALSE | 1153 | +0.34% | 1.34 | 285 | +0.70% | 1.85 | mining |t| 1.34 < 2.0 |
| extended=TRUE | 427 | +0.45% | 1.16 | 69 | +1.42% | 2.51 | mining |t| 1.16 < 2.0 |
| extended=FALSE | 2136 | +0.39% | 1.91 | 574 | +0.72% | 2.29 | mining |t| 1.91 < 2.0 |

## Every subset, full sample (descriptive)

| Subset | Events | Dates | Mean X(5), date-clustered | t | Median X(5) | P(R8 ≥ 4%) | P(R8 ≥ 7%) | P(R8 ≤ 0) |
|---|---|---|---|---|---|---|---|---|
| results=TRUE | 432 | 285 | +0.37% | 1.46 | +0.29% | 29.4% | 14.6% | 43.3% |
| results=FALSE | 2774 | 883 | +0.43% | 2.37 | -0.21% | 31.7% | 18.9% | 45.3% |
| breakout52=TRUE | 635 | 409 | -0.04% | -0.20 | -0.31% | 27.7% | 16.2% | 46.9% |
| breakout52=FALSE | 2571 | 842 | +0.60% | 3.18 | -0.13% | 32.2% | 18.8% | 44.5% |
| big_z=TRUE | 1535 | 734 | +0.37% | 1.21 | -0.13% | 27.6% | 14.7% | 46.3% |
| big_z=FALSE | 1671 | 594 | +0.55% | 2.63 | -0.19% | 34.8% | 21.6% | 43.8% |
| market_day=TRUE | 1768 | 258 | +0.53% | 3.09 | -0.20% | 35.4% | 21.8% | 41.2% |
| market_day=FALSE | 1438 | 726 | +0.42% | 1.95 | -0.11% | 26.4% | 14.0% | 49.7% |
| extended=TRUE | 496 | 308 | +0.58% | 1.70 | -0.30% | 31.0% | 20.0% | 50.2% |
| extended=FALSE | 2710 | 915 | +0.46% | 2.65 | -0.15% | 31.4% | 18.0% | 44.1% |

Drift profile by subset (event-mean X(h)):

| Subset | h=1 | h=3 | h=5 | h=8 | h=10 |
|---|---|---|---|---|---|
| results=TRUE | +0.36% | +0.54% | +0.40% | +0.46% | +0.47% |
| results=FALSE | +0.01% | +0.14% | +0.26% | +0.21% | +0.25% |
| breakout52=TRUE | -0.11% | -0.08% | +0.04% | +0.09% | +0.03% |
| breakout52=FALSE | +0.10% | +0.27% | +0.34% | +0.29% | +0.34% |
| big_z=TRUE | +0.07% | +0.10% | +0.29% | +0.33% | +0.44% |
| big_z=FALSE | +0.04% | +0.29% | +0.27% | +0.17% | +0.13% |
| market_day=TRUE | +0.00% | +0.26% | +0.18% | +0.17% | +0.27% |
| market_day=FALSE | +0.12% | +0.12% | +0.40% | +0.34% | +0.29% |
| extended=TRUE | +0.03% | +0.19% | +0.29% | +0.23% | +0.15% |
| extended=FALSE | +0.06% | +0.20% | +0.28% | +0.25% | +0.30% |

## Results × 52-week breakout (descriptive)

| Subset | Events | Dates | Mean X(5), date-clustered | t | Median X(5) | P(R8 ≥ 4%) | P(R8 ≥ 7%) | P(R8 ≤ 0) |
|---|---|---|---|---|---|---|---|---|
| results=True, breakout52=True | 132 | 114 | +0.25% | 0.63 | +0.49% | 29.5% | 15.2% | 44.7% |
| results=True, breakout52=False | 300 | 215 | +0.43% | 1.27 | +0.19% | 29.3% | 14.3% | 42.7% |
| results=False, breakout52=True | 503 | 326 | -0.11% | -0.43 | -0.52% | 27.2% | 16.5% | 47.5% |
| results=False, breakout52=False | 2271 | 763 | +0.60% | 2.88 | -0.15% | 32.6% | 19.4% | 44.8% |

## Disclosures

- 20 of 347 symbols returned no results meetings from NSE (mostly names that left the F&O list or were delisted); their surges count as results=FALSE.
- Futures stand in for spot; basis changes are included in every return.
- 10 subsets are tested; about one false mining pass is expected by chance at |t| ≥ 2. The holdout requirement is the guard.
