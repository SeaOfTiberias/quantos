---
title: 'Candidate 18b filters — edge in index points?'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\ORB_18B_FILTER_INDEX_POINTS.md'
checksum: 3164b8309e078d8930563b231f58fc40635841bb6e081606104b574893eacc1e
body_checksum: f6b978175c86ed941871ed7a63610254216fcc9a50aba2ea0cc1a61e6af27b18
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Candidate 18b filters — edge in index points?

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\ORB_18B_FILTER_INDEX_POINTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Method and pre-registered rule: `scripts/test_orb_18b_filters_index_points.py` docstring, committed before this run. V0 exit rules; points are measured in the trade's direction; no option pricing.

| Index | Filter | Filtered N | Filtered pts/trade | Other N | Other pts/trade | Difference | p (one-sided) | Verdict |
|---|---|---|---|---|---|---|---|---|
| NIFTY | Monday/Friday | 417 | +2.07 | 639 | +1.55 | +0.52 | 0.463 | PRICING ARTIFACT |
| BANKNIFTY | gap > 0.3% | 618 | +4.73 | 605 | -2.05 | +6.78 | 0.320 | PRICING ARTIFACT |

Filtered subset alone (descriptive):

| Index | pts/trade | t | Net Rs/trade after futures costs | t (net) |
|---|---|---|---|---|
| NIFTY | +2.07 | 0.47 | -418 | -1.45 |
| BANKNIFTY | +4.73 | 0.43 | -322 | -0.97 |
