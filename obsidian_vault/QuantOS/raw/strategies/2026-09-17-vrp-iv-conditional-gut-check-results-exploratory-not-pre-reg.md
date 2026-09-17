---
title: 'VRP IV-Conditional Gut-Check — Results (exploratory, NOT pre-registered)'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VRP_IV_CONDITIONAL_CHECK_RESULTS.md'
checksum: 71563ec314863042188caf5ce3a54fa8613e253d7d94438275cf55c2b8cd68ca
body_checksum: 22793dcd4fb0653c81f06103fc0357a196e12dec4ac7f5ac938e6ea3d4c2f9f6
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# VRP IV-Conditional Gut-Check — Results (exploratory, NOT pre-registered)

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\VRP_IV_CONDITIONAL_CHECK_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Script: `scripts/vrp_iv_conditional_check.py`. Reran the exact same VRP pipeline
as `scripts/backtest_vrp_strangle.py` (same cache, same 158 selections/trades,
same NET cost model), bucketed the already-computed trades into terciles by
entry-day average IV (call+put legs' implied vol from
`core/options/vrp/strikes.py`'s `StrikeSelection`, already computed during
strike selection — not re-derived), and reported NET stats per bucket.

**This is a post-hoc cut on an already-run backtest, not a pre-registered
test.** Run 2026-07-25, output captured here for the record — same
discipline as every other result in this project, even exploratory ones.

## Result

IV terciles: low < 10.5% <= mid < 13.2% <= high (n=158)

| Bucket | N | Win Rate | Avg P&L (% credit) | Profit Factor | Sharpe |
|---|---|---|---|---|---|
| LOW  | 52 | 69.2% | -17.83% | 0.787 | -0.595 |
| MID  | 51 | 62.7% | -8.08%  | 0.880 | -0.386 |
| HIGH | 54 | 79.6% | +31.33% | 1.661 | 1.465  |

Directionally sensible (unlike the earlier IV-minus-RV-spread regime
attempt, which ran backwards) — higher entry IV correlates with
meaningfully better short-strangle outcomes.

## Why this is not yet a finding (Fable review, 2026-07-25)

- **In-sample terciles are lookahead for any live rule.** `t1`/`t2` are
  computed from `sorted()` over the entire 2023-2026 sample. A live system
  wouldn't know the full-sample tercile boundary in real time — a
  pre-registered version needs a trailing/rolling percentile (e.g. today's
  IV vs. the last 252 trading days), not a static in-sample cutoff.
- **Clustering risk, same failure mode flagged in the mean-reversion
  gutcheck.** 52-54 trades per bucket may represent far fewer independent
  volatility episodes if the HIGH bucket is dominated by one or two
  elevated-vol stretches rather than being spread evenly across the window.
  Not yet checked.
- **Raw IV level, not percentile/rank.** Raw level conflates "elevated vol
  regime" with the window's own baseline vol. Percentile is more portable
  and is also what a rolling/trailing version would need to be well-defined.

## What a proper follow-up would need

Fixed, pre-registered BEFORE rerunning: trailing IV percentile threshold
(not in-sample terciles), a cluster/independent-episode check, and reported
as a capital-tracked equity curve for "IV-gated VRP" rather than pooled
bucket stats — same standard applied everywhere else in this project. Not
done yet. This doc records the exploratory result only.
