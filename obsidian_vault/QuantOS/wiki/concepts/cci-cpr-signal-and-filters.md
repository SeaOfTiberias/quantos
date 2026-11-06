---
title: CCI(34)/SMA52 + Monthly CPR Signal, and CCI / RSI Entry Filters
compiled: 2026-11-07
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: cci-cpr-signal-and-filters
candidate: "CCI + monthly CPR 2026-11-07"
family: trend
instrument: stock-cash / stock-futures
status: closed
verdict: FAIL
first_tested: 2026-11-07
verdict_date: 2026-11-07
trades: 21765
bar: "Part A per side: mean net excess >= +0.50%/trade (10 sessions), Holm, both halves > 0, beats CCI cross alone by >= 0.30 pp (CI > 0), n >= 300. Part B: as 2026-10-26 plus blocks >= 10% and blocked trades worse by >= 0.30 pp"
headline: "The user's CCI-cross + 5-day-SMA-over-monthly-CPR rule, found on HDFCBANK and ADANIPORTS, earns about nothing over 2013-26 (longs -0.02%, shorts +0.16% per trade vs the average stock); CCI -50 and RSI 40/60 filters block 75-96% of screener trades and the blocked ones did no worse. 0 of 8 pass."
quantos:
  layer: wiki
  generated: true
---

# CCI(34)/SMA52 + Monthly CPR Signal, and CCI / RSI Entry Filters

> [!abstract] Compiled page
> Written from `docs/CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md` and
> `docs/CCI_CPR_SIGNAL_AND_FILTERS_RESULTS_2026-11-07.md` on 2026-11-07. Context and retrieval only:
> rules in this layer never execute.

## Definition

- **Part A** comes from two charts the user picked after the move (HDFCBANK and ADANIPORTS,
  Oct–Nov 2026). The long signal needs all three of:
  1. daily CCI(34) crosses above its 52-day simple average;
  2. that average is flat or rising;
  3. within 3 sessions, the 5-day SMA crosses above the top of the previous month's CPR.

  The short signal is the mirror image.
- **Part B** comes from the post-trade notes on HDFCBANK and SUPREMEIND. It tests whether two
  blocks help:
  - CCI < −50 blocks a short (CCI > +50 blocks a long);
  - RSI < 40 blocks a short (RSI > 60 blocks a long).

## Verdict

**FAIL, 0 of 8.**

| Test | n | Mean per trade | Note |
|---|---|---|---|
| A long | 11,934 | −0.02% | vs average stock, after 0.25%; p 0.81 |
| A short | 9,831 | +0.16% | p 0.049, fails Holm and the +0.50% bar |
| CCI cross alone (reference) | ~53,000 per side | −0.23% / −0.31% | |

- **The CPR and slope conditions do add something** over the CCI cross alone: +0.21 pp
  (longs) and +0.48 pp (shorts). They lift a losing signal to about break-even, not to a
  usable edge.
- **The shorts that could actually be placed lose.** Among stocks on today's F&O list,
  shorts made −0.36% a trade; the positive short mean comes from stocks that can't be
  shorted overnight.
- **Leads, not rescues** (each needs its own new pre-registration):
  - shorts in Weinstein stage 4 (+0.50%);
  - shorts in the high-ATR% tercile (+0.48%).
- **Part B:** at breakouts and breakdowns, CCI and RSI are almost always stretched, so the
  filters block 75–96% of the screener's trades. The blocked trades did the same as the kept
  ones (−0.14 to +0.06 pp).

## Relation to other concepts

- Extends [[cci-sma-cross-signals]] (the CCI cross alone, FAIL 0/12) and
  [[fno-screener-cci-sma-filters]].
- The monthly CPR is a map element (Market Map definitions v1). Its own test is the S8
  signal pre-registration (H5 pivots, H8 GPZ).
