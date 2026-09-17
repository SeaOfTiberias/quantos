---
title: 'NIFTY Option Skew Validation'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VOL_SKEW_VALIDATION.md'
checksum: c02ab098a802b654d8b448e5c27ab2063ffa565ddd7dfff796411b485178a7f2
body_checksum: e579bb5c018fcf53e28a5f108ef1052e6bc312fb669aab78badcd1d1725642e1
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# NIFTY Option Skew Validation

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VOL_SKEW_VALIDATION.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/VOL_SKEW_METHODOLOGY.md. Replayed 611 days (2024-01-31 to 2026-07-24), 591 scored with a valid skew and full forward window.

## Skipped days

- none

## Forward realized vol by skew quintile

(Q1 = lowest/most-negative skew i.e. calls pricier than puts, Q5 = highest skew i.e. puts pricing richest.)

| Bucket | n | Mean skew | Mean fwd 20d RV |
|---|---|---|---|
| Q1 | 118 | +0.01 | 12.78 |
| Q2 | 115 | +0.03 | 11.53 |
| Q3 | 120 | +0.04 | 11.54 |
| Q4 | 119 | +0.04 | 11.71 |
| Q5 | 119 | +0.07 | 14.82 |

## Verdict

- Q5 mean fwd RV (14.82, n=119) vs Q1 (12.78, n=118): gap = +2.04 vol points.
- Full Q1→Q5 sequence monotonically non-decreasing: False.
- Per docs/VOL_SKEW_METHODOLOGY.md's pass bar: FAIL (monotonic AND Q5 > Q1 required).
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and docs/VOL_SPREAD_VALIDATION.md's style.
