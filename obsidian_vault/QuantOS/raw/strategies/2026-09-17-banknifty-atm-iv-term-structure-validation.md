---
title: 'BANKNIFTY ATM IV Term Structure Validation'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VOL_TERM_STRUCTURE_VALIDATION_BANKNIFTY.md'
checksum: 84f9b4698eff5fa9aa5f53a9a8d44570a71d4f0144fd1570942b48eb0374dbfa
body_checksum: 4fda106639a2513cb263a3e4dd79ff80b0cfd5343a395f00ead46f5f32762b72
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# BANKNIFTY ATM IV Term Structure Validation

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VOL_TERM_STRUCTURE_VALIDATION_BANKNIFTY.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/VOL_TERM_STRUCTURE_METHODOLOGY.md. Replayed 612 days (2024-01-31 to 2026-07-27), 592 scored with a valid spread and full forward window.

## Skipped days

- none

## Forward realized vol by term-structure-spread quintile

(Q1 = most negative spread i.e. deepest contango/calm shape, Q5 = most positive spread i.e. deepest backwardation/stress shape.)

| Bucket | n | Mean spread | Mean fwd 20d RV |
|---|---|---|---|
| Q1 | 118 | -0.02 | 15.13 |
| Q2 | 118 | -0.00 | 13.64 |
| Q3 | 119 | +0.00 | 12.28 |
| Q4 | 118 | +0.01 | 13.44 |
| Q5 | 119 | +0.03 | 18.54 |

## Verdict

- Q5 mean fwd RV (18.54, n=119) vs Q1 (15.13, n=118): gap = +3.41 vol points.
- Full Q1→Q5 sequence monotonically non-decreasing: False.
- Per docs/VOL_TERM_STRUCTURE_METHODOLOGY.md's pass bar: FAIL (monotonic AND Q5 > Q1 required).
Read the gaps above against the sample sizes (`n`) in the table -- this report presents the numbers, no invented significance test, matching docs/REGIME_VALIDATION.md and every prior vol-conditioning report.
