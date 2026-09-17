---
title: 'Candle-Confirm Momentum Gut-Check Results (candidate 19)'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\CANDLE_CONFIRM_MOMENTUM_GUTCHECK_RESULTS.md'
checksum: 3489701b7356883a940d1fffc53348acfefdfae17e08c87d22a9fd00e56aae64
body_checksum: 21be91d7370a200e0037d84f64d1e9d39bddc6b143ac4b2c4b1d13eda72eb3c5
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Candle-Confirm Momentum Gut-Check Results (candidate 19)

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\CANDLE_CONFIRM_MOMENTUM_GUTCHECK_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/CANDLE_CONFIRM_MOMENTUM_GUTCHECK_METHODOLOGY.md.

## NIFTY

Trading days: 1036. No-signal days: 545 (doji candle1: 0, candle2 opposed: 545, short session: 0). Signal rate: 47.4%.

### CALL bias (n=221)

| Horizon | n | Win rate | Mean return % | Mean \|return\| % |
|---|---|---|---|---|
| 5min | 221 | 48.0% | -0.004 | 0.092 |
| 10min | 221 | 52.0% | -0.002 | 0.122 |
| 15min | 221 | 50.2% | -0.007 | 0.151 |

### PUT bias (n=270)

| Horizon | n | Win rate | Mean return % | Mean \|return\| % |
|---|---|---|---|---|
| 5min | 270 | 55.9% | -0.001 | 0.099 |
| 10min | 270 | 51.9% | +0.002 | 0.125 |
| 15min | 270 | 55.9% | -0.011 | 0.146 |

**Baseline (unconditional, no signal filter, +10min, n=1036):** mean return +0.004%, mean |return| 0.121%.

## BankNifty

Trading days: 1285. No-signal days: 643 (doji candle1: 1, candle2 opposed: 642, short session: 0). Signal rate: 50.0%.

### CALL bias (n=306)

| Horizon | n | Win rate | Mean return % | Mean \|return\| % |
|---|---|---|---|---|
| 5min | 306 | 56.2% | +0.011 | 0.129 |
| 10min | 306 | 53.3% | +0.011 | 0.172 |
| 15min | 306 | 53.9% | +0.015 | 0.199 |

### PUT bias (n=336)

| Horizon | n | Win rate | Mean return % | Mean \|return\| % |
|---|---|---|---|---|
| 5min | 336 | 47.9% | +0.001 | 0.143 |
| 10min | 336 | 49.4% | +0.010 | 0.178 |
| 15min | 336 | 47.0% | +0.011 | 0.191 |

**Baseline (unconditional, no signal filter, +10min, n=1285):** mean return +0.007%, mean |return| 0.174%.
