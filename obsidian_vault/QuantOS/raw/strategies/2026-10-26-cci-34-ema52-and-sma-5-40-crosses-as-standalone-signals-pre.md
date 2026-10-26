---
title: 'CCI(34)/EMA52 and SMA 5/40 crosses as standalone signals (pre-registration)'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/CCI_SMA_CROSS_SIGNALS_PREREG_2026-10-26.md'
checksum: 846587e1c0d8e759586f1835f6b88be94e79a54dbea5d24e08c07fb08578ffe4
body_checksum: eea4402e8f01fe6b06c3692663d1c5252dbf00d73424da1efb9cc503b3c036b3
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# CCI(34)/EMA52 and SMA 5/40 crosses as standalone signals (pre-registration)

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/CCI_SMA_CROSS_SIGNALS_PREREG_2026-10-26.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Fixed 2026-10-26, BEFORE the test was run. The same two daily indicators failed to add
anything as screener filters (docs/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md); the
user asked to test the crosses as entries in their own right.

## Data

Daily bars for the 213 F&O stocks and NIFTY in `~/.quantos/bt_fno/bars.pkl`
(2024-07-25 to 2026-10-23). Indicators as in the filter test (CCI(34) on typical price
vs its 52-EMA; SMA5 vs SMA40), so signals start once CCI's EMA has 52 values (about
December 2024).

## Signals (fresh crosses, read at the day's close)

- **SMA:** SMA5 crosses above SMA40 → long; below → short.
- **CCI:** CCI(34) crosses above its EMA52 → long; below → short.
- **Both:** the day the two first agree (one crosses while the other already points the
  same way) → long or short.

Entry at the next day's open.

## Exits (two, each reported for every signal)

1. **Opposite cross:** exit at the next open after the same indicator crosses back (for
   Both: after the two stop agreeing). Capped at 60 sessions (exit at that close).
   Trades still open at the end of the data are dropped.
2. **Fixed (screener's rules on daily bars):** stop on a daily close 0.75 ATR(14)
   against entry, emergency 1 ATR further on touch, 1R target on touch, out at the
   close of session 10. If the target and emergency are both touched in one day, the
   emergency counts.

One open trade per stock, signal and exit; a signal while in a trade is skipped. Cost
0.1% round trip (futures).

## Measure and pass bar

Each trade's return minus NIFTY's return over the same entry-to-exit prices (sign
flipped for shorts), so market drift isn't credited. Longs and shorts are reported
separately: 3 signals × 2 sides × 2 exits = 12 tests.

A test PASSES when its market-adjusted mean per trade:
- has n ≥ 150,
- is > 0 in both halves (split at the median entry date),
- has a day-clustered t ≥ 2.7.

Raw (unadjusted) returns are shown alongside. A PASS goes to a forward paper log
before any real use.
