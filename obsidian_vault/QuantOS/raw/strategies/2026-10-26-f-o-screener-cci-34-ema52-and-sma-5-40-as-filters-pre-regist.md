---
title: 'F&O screener — CCI(34)/EMA52 and SMA 5/40 as filters (pre-registration)'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md'
checksum: 8e297d83c10abfe7d11c5334abe60d7a1948ca2234ccb610f48bd481261a791a
body_checksum: 1067a52c9a38aa1495398639c1b187fc9b1057b4e6aa87687bb29a7e2d9e71ff
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# F&O screener — CCI(34)/EMA52 and SMA 5/40 as filters (pre-registration)

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Fixed 2026-10-26, BEFORE the test was run. The user proposed two daily indicators
and chose (from a short list) to test them as filters on the F&O screener's picks,
each alone and both together.

## Indicators (each stock's own daily bars, known at the signal day's close)

- **CCI rule:** CCI(34) on typical price (H+L+C)/3 = (TP − SMA34(TP)) / (0.015 × mean
  absolute deviation over 34). Its signal line is the 52-period EMA of CCI. Bullish when
  CCI > its EMA52, bearish when below.
- **SMA rule:** bullish when SMA5 of the close > SMA40, bearish when below.
- **Both:** bullish only when both are bullish; bearish only when both are bearish.

A filter keeps a call (CE) pick only on a bullish reading and a put (PE) pick only on a
bearish one. This is the state on the signal day, not a fresh cross (fresh crosses
would leave too few trades to test).

## Trades filtered (unchanged from docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md)

Signals: the screener backtest's FRESH and OUT (≤ 5 sessions) rows, 2025-09-02 to
2026-10-23, 213 stocks (`~/.quantos/bt_fno/outcomes.jsonl`). Exit: futures on the
underlying; stop on a daily close 0.75 ATR beyond entry, emergency 1 ATR further on
touch, 1R resting target, out at the close of session 10, 0.1% round-trip cost.

Three entry sets:
1. **CE baseline:** calls at the next open.
2. **PE baseline:** puts at the next open.
3. **PE H1 retest:** sell limit 0.25 ATR under the broken floor, valid 3 sessions (the
   screener's only measured edge).

**Deduplication:** one trade per breakout episode (symbol, side, box level). For the
baselines that is the episode's first qualifying signal. For H1 it is the first fill.
The filter is read on the day of the signal that produced the trade.

## Pass bar (per filter × entry set; 3 × 3 = 9 tests)

A filter PASSES on an entry set when the kept trades:
- number at least 100,
- have mean > 0 in both halves (split at the median signal date),
- have a day-clustered t ≥ 2.7 (high because there are nine tests),
- beat the unfiltered set's mean in both halves.

The rejected trades are reported too: a useful filter should reject worse trades than
it keeps.

Anything else is FAIL. A PASS would go to the screener as a label first (shown, not
gating), with the outcome log judging it, before it ever removes picks.
