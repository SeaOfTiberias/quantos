---
title: 'Put retest (H1): can context remove the losing trades? (pre-registration)'
ingested: 2026-10-26
origin: '/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md'
checksum: cea08f6690e5fe48a0529f24861c59e9f4015b886b67b00192ff840797e33b99
body_checksum: d2790cb01e1aaaa1a162a017e35e89b1df66fbe5b15092bb17ca519a8ed565d8
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Put retest (H1): can context remove the losing trades? (pre-registration)

> [!info] Ingested source
> Filed 2026-10-26 from `/home/ubuntu/quantos/obsidian_vault/QuantOS/raw/_inbox/PUT_RETEST_CONTEXT_REVIEW_PREREG_2026-10-26.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Fixed 2026-10-26, BEFORE any context feature was computed or shown to a model. The
user asked for an LLM review of the best tested strategy: given the context around
each trade (results dates, market, sector…), propose rules that skip the losers.

## The strategy and its trades

The F&O screener's put H1 retest (docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md): after a
put breakdown, sell a limit 0.25 ATR under the broken floor, valid 3 sessions; stop on a
daily close 0.75 ATR above the fill, emergency 1 ATR further, 1R resting target, out by
session 10, 0.1% cost. One trade per breakout episode (first fill), as in
scripts/backtest_fno_indicator_filter.py: 1,672 trades, 69% won, +0.34% per trade,
signals 2025-09-02 to 2026-10-23.

## Context features (each known by the time of the fill)

- **Results:** trading days from the signal to the next results board meeting and since
  the last one (NSE corporate board meetings with "financial results").
- **Market:** NIFTY above its EMA20 (from the signal), NIFTY 5- and 20-day return, India
  VIX level and its 5-day change.
- **Sector:** NSE sectoral index membership (else "other") and the sector's mean 20-day
  return across the stocks in the backtest.
- **Stock:** 5- and 20-day return, distance above the 52-week low in ATR, ATR %, depth
  below the broken floor at the signal (ATR), box width %, volume ratio, sessions out,
  screener tier/bucket, momentum percentile, futures OI label, option IV.
- **Fill:** sessions from signal to fill (1–3), the fill day's opening gap in ATR,
  filled at the open or intraday.
- **Calendar:** weekday of the fill, trading days to the monthly expiry.

The forward-outcome columns in the signals file (cc*, oc*, ex*, chain) are never used.

## Blind review

- Split at the median signal date (2026-03-27, as in the earlier filter test). The
  model sees ONLY the first half: each trade's features and its result (return, win),
  with no symbol and no date, so it cannot recall what a named stock did. It also gets
  per-feature win-rate tables for that half.
- Model: Claude Opus via the API (`model_for("context_review")`), one call, prompt and
  response saved under docs/.
- It returns at most 3 skip rules as machine-readable conditions on the feature columns,
  each with its reasoning. No rule may use the trade's outcome.

## Test (second half only, which the model never saw)

Each rule, and all of them combined (skip if any fires), PASSES when on the second half:
- it removes at least 30 trades and keeps at least half,
- the kept trades' mean beats the unfiltered mean,
- kept minus removed mean has a Welch t ≥ 2.0.

A PASS goes into the screener as a shown flag on put picks first, judged on the live
outcome log, before it is ever allowed to drop a pick. A FAIL is recorded and the put
plan stays as it is.
