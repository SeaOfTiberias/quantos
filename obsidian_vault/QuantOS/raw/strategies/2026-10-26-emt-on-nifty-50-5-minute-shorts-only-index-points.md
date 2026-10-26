---
title: 'EMT on NIFTY 50 5-minute — shorts only (index points)'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/EMT_VWAP_RESULTS_SHORTS.md'
checksum: be3597552c38b824802e4f36b3289af2a75d6da4d76a21442495112e3d3ced28
body_checksum: 2398f36897e7d98ac752455565922a8eb3a7a305d64ced8e40ca6a3136bad834
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# EMT on NIFTY 50 5-minute — shorts only (index points)

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/EMT_VWAP_RESULTS_SHORTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Rules: docs/EMT_VWAP_METHODOLOGY.md, shorts-only addendum. Variant `vwap_ema`. Discovery 2025-10-27..2026-10-26 (247 sessions, already seen); confirmation 2023-10-27..2025-10-24 (496 sessions, never looked at). Costs: 2 pts per round trip unless stated.

**Verdict (shorts only): FAIL: confirmation k=1.5, n=1248, net -3.84 pts/trade, PF 0.71 (bar: n>=40, net>0, PF>=1.2)**

## Discovery (k chosen here)

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| shorts k=0.5 | 965 | 36% | -0.19 | -2.19 | -2116 | 0.80 | -2.69 | 2597 | 18.1 | 350/590/25 |
| shorts k=1 | 804 | 34% | +0.27 | -1.73 | -1390 | 0.86 | -1.80 | 1905 | 18.4 | 261/518/25 |
| shorts k=1.5 | 621 | 31% | +0.40 | -1.60 | -997 | 0.87 | -1.37 | 1563 | 18.6 | 174/422/25 |
| shorts k=2 | 462 | 25% | -0.64 | -2.64 | -1219 | 0.81 | -1.84 | 1591 | 18.6 | 100/337/25 |

## Confirmation (k=1.5 only)

| | n | win | gross pts/trade | net pts/trade | net total | PF | t | max DD | avg risk pts | target/stop/eod |
|---|---|---|---|---|---|---|---|---|---|---|
| shorts k=1.5 | 1248 | 28% | -1.84 | -3.84 | -4795 | 0.71 | -4.75 | 4922 | 17.9 | 326/886/36 |
| shorts k=1.5 cost 1 | 1248 | 28% | -1.84 | -2.84 | -3547 | 0.78 | -3.51 | 3678 | 17.9 | 326/886/36 |
| shorts k=1.5 cost 4 | 1248 | 28% | -1.84 | -5.84 | -7291 | 0.61 | -7.22 | 7410 | 17.9 | 326/886/36 |
| year 2023-10-27..2024-10-27 | 644 | 27% | -2.62 | -4.62 | -2978 | 0.64 | -4.63 | 3017 | 16.5 | 165/466/13 |
| year 2024-10-27..2025-10-24 | 604 | 29% | -1.01 | -3.01 | -1817 | 0.79 | -2.33 | 2012 | 19.4 | 161/420/23 |
