---
title: 'Candidate 23b Part C — Surge Follow-Through Persistence — Results'
ingested: 2026-10-15
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\SURGE_23B_PERSISTENCE_RESULTS.md'
checksum: 4c002ff1f84d88721cfa5e852adc07e93b843cbbbdd07e6af955f588debc6ec8
body_checksum: 5fe51a4c83edaf5ebf44019ed32f4a198b69441d754edb2ffbbad342b006d7f4
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Candidate 23b Part C — Surge Follow-Through Persistence — Results

> [!info] Ingested source
> Filed 2026-10-15 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\SURGE_23B_PERSISTENCE_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/SURGE_23B_METHODOLOGY.md, Part C (pre-registered 2026-10-15). Stage 1 events with breakout52=FALSE, months 2020-05 to 2024-12. Predictor = mean 5-day excess return of the previous 3 months' events whose outcome was known before the month began (≥ 15 events); outcome = that month's events' mean 5-day excess return.

## Verdict: **FAIL**

- Spearman correlation 0.149, one-sided p 0.137 → FAIL (needs > 0, p < 0.05)
- Mean outcome when the predictor > 0: +0.25% (42 months); when ≤ 0: +0.31% (14 months) → FAIL

Consequence: no gate. Market state stays descriptive only (Part B). With about 56 monthly points the test has low power: this is no evidence of persistence, not proof of none.

## Monthly series

| Month | Predictor (trailing 3-mo X(5)) | Outcome (month X(5)) | Trailing events | Month events |
|---|---|---|---|---|
| 2020-05 | +0.56% | +0.41% | 252 | 82 |
| 2020-06 | +0.22% | -0.70% | 344 | 91 |
| 2020-07 | -0.14% | -0.66% | 294 | 50 |
| 2020-08 | -0.20% | +1.50% | 218 | 55 |
| 2020-09 | +0.22% | +0.35% | 180 | 45 |
| 2020-10 | +0.51% | -0.45% | 124 | 27 |
| 2020-11 | +0.74% | +1.60% | 117 | 50 |
| 2020-12 | +0.74% | +0.56% | 111 | 32 |
| 2021-01 | +0.89% | +0.50% | 106 | 25 |
| 2021-02 | +0.93% | +2.63% | 104 | 60 |
| 2021-03 | +1.51% | +0.06% | 109 | 21 |
| 2021-04 | +1.41% | -0.55% | 102 | 29 |
| 2021-05 | +1.45% | +1.36% | 103 | 26 |
| 2021-06 | +0.25% | -0.55% | 72 | 17 |
| 2021-07 | +0.03% | -1.27% | 67 | 14 |
| 2021-08 | +0.24% | -0.76% | 51 | 15 |
| 2021-09 | -0.95% | +0.42% | 45 | 30 |
| 2021-10 | -0.25% | +0.18% | 53 | 23 |
| 2021-11 | +0.08% | +1.46% | 59 | 26 |
| 2021-12 | +0.61% | -0.09% | 73 | 15 |
| 2022-01 | +0.71% | +0.07% | 62 | 33 |
| 2022-02 | +0.38% | +1.21% | 61 | 62 |
| 2022-03 | -0.00% | -0.88% | 77 | 39 |
| 2022-04 | +0.35% | -1.15% | 133 | 27 |
| 2022-05 | +0.25% | -1.39% | 121 | 60 |
| 2022-06 | -1.15% | -0.32% | 106 | 33 |
| 2022-07 | -0.98% | -0.21% | 117 | 39 |
| 2022-08 | -0.82% | +0.74% | 118 | 25 |
| 2022-09 | +0.07% | -0.34% | 91 | 26 |
| 2022-10 | +0.30% | +0.38% | 79 | 29 |
| 2022-11 | +0.49% | -0.38% | 72 | 30 |
| 2022-12 | -0.14% | +0.53% | 77 | 23 |
| 2023-01 | -0.21% | +0.84% | 69 | 21 |
| 2023-02 | +0.35% | +2.44% | 61 | 30 |
| 2023-03 | +0.68% | -0.41% | 68 | 19 |
| 2023-04 | +1.26% | +0.16% | 65 | 22 |
| 2023-05 | +1.28% | +0.56% | 63 | 32 |
| 2023-06 | +0.10% | +0.48% | 64 | 11 |
| 2023-07 | +0.42% | +0.87% | 63 | 25 |
| 2023-08 | +0.68% | +1.27% | 57 | 14 |
| 2023-09 | +0.64% | -0.63% | 48 | 21 |
| 2023-10 | +0.63% | +1.64% | 53 | 10 |
| 2023-11 | +0.30% | +1.24% | 42 | 24 |
| 2023-12 | +0.30% | +0.89% | 49 | 17 |
| 2024-01 | +1.24% | +1.35% | 49 | 23 |
| 2024-02 | +1.16% | -0.71% | 50 | 16 |
| 2024-03 | +0.62% | +0.76% | 54 | 19 |
| 2024-04 | +0.29% | -0.08% | 49 | 27 |
| 2024-05 | +0.05% | -0.70% | 53 | 21 |
| 2024-06 | +0.22% | -1.27% | 64 | 83 |
| 2024-07 | -0.92% | -0.01% | 130 | 28 |
| 2024-08 | -0.98% | +0.00% | 120 | 20 |
| 2024-09 | -0.83% | +1.24% | 128 | 10 |
| 2024-10 | -0.04% | +0.98% | 55 | 29 |
| 2024-11 | +0.92% | -0.21% | 46 | 21 |
| 2024-12 | +0.58% | +0.03% | 52 | 6 |
