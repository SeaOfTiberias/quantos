---
title: 'Darvas Box-Width Sensitivity — Results'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\DARVAS_BOX_WIDTH_SENSITIVITY_RESULTS.md'
checksum: 8b61a6681e62ce9c76933b534ebefa17064b92c81ce589f4f96b5d937738b395
body_checksum: a1a4ddae63aedbe4e9dfe0c348f5527fe37bb96c7ae77a03ad63b6ea0d51ce8f
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Darvas Box-Width Sensitivity — Results

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\DARVAS_BOX_WIDTH_SENSITIVITY_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/DARVAS_BOX_WIDTH_SENSITIVITY_METHODOLOGY.md, pre-registered 2026-09-22 before this ran. Gut-check only — raw forward returns, no costs, no stops. A favorable bucket here is grounds for a full cost-adjusted backtest, not a dashboard change on its own.

73 symbols attempted, 6 errored, 181 total FRESH BREAKOUT events found across all widths.

Errored symbols (excluded from the analysis): # Nifty 500 - 500 symbols, # market did) - see agent/main.py's regime wiring., GROWW, JAINREC, PWL, TENNIND

## Forward return at 4w

| Width bucket | n | Mean | Median | Hit rate |
|---|---|---|---|---|
| <=35% (control) | 147 | -1.77% | -2.38% | 38.1% |
| 35-50% | 18 | -0.69% | +1.40% | 61.1% |
| 50-100% | 11 | +0.49% | +3.41% | 54.5% |
| >100% (not a real box, excluded from comparison) | 0 | too few (<10), not a read | | |

## Forward return at 8w

| Width bucket | n | Mean | Median | Hit rate |
|---|---|---|---|---|
| <=35% (control) | 135 | -1.93% | -2.32% | 41.5% |
| 35-50% | 15 | +4.45% | +3.17% | 53.3% |
| 50-100% | 9 | too few (<10), not a read | | |
| >100% (not a real box, excluded from comparison) | 0 | too few (<10), not a read | | |

## Forward return at 12w

| Width bucket | n | Mean | Median | Hit rate |
|---|---|---|---|---|
| <=35% (control) | 132 | -2.97% | -4.56% | 37.9% |
| 35-50% | 14 | +3.22% | -0.04% | 50.0% |
| 50-100% | 8 | too few (<10), not a read | | |
| >100% (not a real box, excluded from comparison) | 0 | too few (<10), not a read | | |
