---
title: 'CCI(34)/EMA52 and SMA 5/40 crosses as standalone signals: results'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/CCI_SMA_CROSS_SIGNALS_RESULTS_2026-10-26.md'
checksum: 4cd8ae64e228fa2eb594511a749b77d4262b306657b01a560937f2280c0f69cb
body_checksum: da33cab752ff008fc9bfa8d1ccf23b70f0c97ad4385eac5d3d614d8b5e9cb7ee
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# CCI(34)/EMA52 and SMA 5/40 crosses as standalone signals: results

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/CCI_SMA_CROSS_SIGNALS_RESULTS_2026-10-26.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Rules: docs/CCI_SMA_CROSS_SIGNALS_PREREG_2026-10-26.md. 213 stocks, entries 2024-11-28 to 2026-10-23, halves split at 2025-11-11. % per trade after 0.1% cost; 'vs NIFTY' subtracts NIFTY's move over the same days.

**Verdict:** 0 of 12 pass.

| signal | exit | side | n | raw mean | vs NIFTY mean | win (vs NIFTY) | t | H1 | H2 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| sma | opposite | long | 1973 | -0.03% | +0.63% | 33% | +1.3 | +0.28% | +1.03% | FAIL |
| sma | opposite | short | 1878 | -1.31% | -0.82% | 32% | -5.2 | +0.10% | -1.85% | FAIL |
| sma | fixed | long | 1897 | -0.34% | -0.21% | 53% | -2.6 | -0.26% | -0.15% | FAIL |
| sma | fixed | short | 1941 | +0.02% | -0.06% | 59% | -0.5 | -0.13% | +0.01% | FAIL |
| cci | opposite | long | 5298 | -0.13% | +0.13% | 32% | -0.3 | -0.07% | +0.31% | FAIL |
| cci | opposite | short | 5274 | -0.57% | -0.45% | 31% | -3.4 | -0.30% | -0.60% | FAIL |
| cci | fixed | long | 4196 | -0.23% | -0.18% | 54% | -3.5 | -0.18% | -0.19% | FAIL |
| cci | fixed | short | 4210 | -0.06% | -0.04% | 59% | -0.8 | -0.09% | +0.02% | FAIL |
| both | opposite | long | 3694 | -0.32% | +0.15% | 35% | +0.6 | -0.06% | +0.36% | FAIL |
| both | opposite | short | 3505 | -0.55% | -0.45% | 34% | -4.0 | -0.31% | -0.58% | FAIL |
| both | fixed | long | 3487 | -0.23% | -0.13% | 54% | -3.3 | -0.08% | -0.19% | FAIL |
| both | fixed | short | 3423 | +0.06% | -0.01% | 60% | +0.0 | -0.04% | +0.01% | FAIL |
