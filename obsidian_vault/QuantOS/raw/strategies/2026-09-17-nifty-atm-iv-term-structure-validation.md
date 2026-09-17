---
title: 'NIFTY ATM IV Term Structure Validation'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VOL_TERM_STRUCTURE_VALIDATION.md'
checksum: 428f52896ea15760539a8324cb66eb2c80a9ec6ce71dabab82841f104dc6bfab
body_checksum: 349ebb1f3f18321606adca331abc80bc1ee5412f8d359813391ddfbaa8a426cd
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# NIFTY ATM IV Term Structure Validation

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VOL_TERM_STRUCTURE_VALIDATION.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/VOL_TERM_STRUCTURE_METHODOLOGY.md. Replayed 612 days (2024-01-31 to 2026-07-27), 592 scored with a valid spread and full forward window.

## Skipped days

- none

## Forward realized vol by term-structure-spread quintile

(Q1 = most negative spread i.e. deepest contango/calm shape, Q5 = most positive spread i.e. deepest backwardation/stress shape.)

| Bucket | n | Mean spread | Mean fwd 20d RV |
|---|---|---|---|
| Q1 | 118 | -0.02 | 12.46 |
| Q2 | 118 | -0.01 | 11.82 |
| Q3 | 117 | -0.00 | 11.10 |
| Q4 | 120 | +0.00 | 12.41 |
| Q5 | 119 | +0.02 | 14.57 |

## Verdict

- Q5 mean fwd RV (14.57, n=119) vs Q1 (12.46, n=118): gap = +2.11 vol points.
- Full Q1→Q5 sequence monotonically non-decreasing: False.
- Per docs/VOL_TERM_STRUCTURE_METHODOLOGY.md's pass bar: FAIL (monotonic AND Q5 > Q1 required).
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and every prior vol-conditioning report.
