---
title: 'Darvas ATR-stop — falsification pass'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\DARVAS_ATR_STOP_FALSIFICATION.md'
checksum: 954671b81f4e901f242f1231666f73dbebc554f66b821e0212d4224293537257
body_checksum: def630c2fbc8323c30a6b0e46bb48a840eba9f82c6e0d681328159ba9d35f62f
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Darvas ATR-stop — falsification pass

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\DARVAS_ATR_STOP_FALSIFICATION.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Kill conditions pre-registered in `scripts/falsify_darvas_atr_stop.py` (committed before this run). Net = Stressed costs on a Rs100,000 position; returns per trade.

| Bucket | N | Mean net | Mean net minus NIFTY (K1) | Total net | Total without top 5% (K2) | Entry weeks | 90% CI of mean, week bootstrap (K3) |
|---|---|---|---|---|---|---|---|
| <=35% (control) | 1785 | -0.24% | -0.11% (n=1785) | -425.1% | -2186.4% (−89) | 144 | -0.75% .. +0.28% |
| 35-50% | 277 | +0.70% | +0.95% (n=277) | +192.8% | -233.1% (−14) | 101 | -0.76% .. +2.10% |
| 50-100% | 196 | +0.26% | +0.66% (n=196) | +51.7% | -293.9% (−10) | 86 | -1.48% .. +2.09% |

## Bucket B verdict

- K1 beta: survives
- K2 few trades: **KILLED**
- K3 noise: **KILLED**

**PASS DOES NOT SURVIVE -- not ready for capital**
