# Darvas Box-Width Sensitivity — Pre-Committed 2026-09-22 Before Any Result Exists

## Why this exists

User noticed WELSPUNLIV's real April breakout (a genuine ~90% mover since)
never appeared on the Breakout Candidates panel. Root cause found: its
weekly box was 36.3% wide, just over `core/darvas/weekly_discovery.py`'s
`max_box_width` cutoff (35%), which excludes it entirely — `analyse_symbol`
returns nothing, not even a "wide box" label, for a box over that width.

A follow-up check of today's other Nifty 500 momentum leaders found ALL
29 currently showing `base_status: "NO BASE"` are excluded by the SAME
cutoff, at widths from 35.6% up to 131.8%.

**That finding does NOT by itself justify loosening the cutoff.** Every
one of those 29 symbols was selected *because* it is already a top
momentum leader — a stock that has already had a large sustained move
will, close to definitionally, show a wide range over any lookback window
that includes that move. Measuring box width only on already-confirmed
winners cannot distinguish "wide boxes predict future winners" from "big
winners have wide boxes in hindsight" — the same survivorship-style
mistake this project's own history has been burned by before (S8-3). This
document exists to test the real, unbiased question: **does an
unfiltered sample of Darvas breakouts, bucketed by box width, show a
different forward return profile by bucket, or not?**

Checked and ruled out: reusing S7-3's original Darvas backtest data to
answer this without a new run — that backtest came from a TradingView
Strategy Tester export and never recorded box width per trade, so it
cannot be resliced.

## Scope

**A gut-check, not a cost-adjusted backtest.** Matches this project's own
established sequence (see candidate 15/19/20's own "gut check first"
step before any of them earned a full pre-registered backtest): measure
raw, unmanaged forward returns from a real breakout signal, at fixed
horizons, bucketed by width. If a bucket beyond the current 35% cutoff
shows a forward-return profile comparable to or better than the current
cutoff's own bucket, THAT becomes grounds for a full, cost-adjusted
backtest (stops, realistic entry/exit, PF/Sharpe) as a separate, later,
freshly pre-registered step — not an automatic green light on its own.

**This changes nothing about what candidate 18/18b or any other live
process trades.** `core/darvas/weekly_discovery.py`'s live `max_box_width`
default (35%) is untouched — this analysis calls `analyse_symbol` with an
explicit config override, never changes the module's own default. Any
outcome here is scoped to, at most, the discretionary Breakout Candidates
dashboard panel — never an automated entry.

## Universe (pinned before any data is pulled)

**A systematic sample of `agent/universe_nifty500.txt`, not the full 508
and not a hand-picked list.** Every 7th symbol by file order (index 0, 7,
14, 21, ...), yielding ~72 symbols. Systematic sampling avoids both the
API cost of the full universe (this project hit Fyers' rate limit
repeatedly today on far smaller batches) and the selection bias of
picking symbols by hand or by outcome — the file's own order is not
sorted by performance or sector, so this is a fair, if modest, cross-
section. Reported honestly as a SAMPLE, not the full universe — a
follow-up on the full 508 remains open if this sample shows something
worth confirming at scale.

## Time window

2024-09-22 to 2026-09-22 (2 years, chunked into two <366-day Fyers
requests per symbol per the existing 366-day cap). Long enough to include
multiple real market conditions, short enough to keep this a same-session
gut-check rather than a multi-day fetch.

## Signal (unchanged, just unfiltered)

`core/darvas/weekly_discovery.py::analyse_symbol`, called day-by-day
(`daily[: i+1]` for each `i`) exactly as `WeeklyDiscoveryScanner` and the
existing momentum-shortlist pipeline already call it — but with
`cfg={**DEFAULT_CONFIG, "max_box_width": 200.0}` so a box of ANY width is
classified rather than silently dropped. A breakout event is recorded
each time `status == "FRESH BREAKOUT"` fires (the module's own `prev_close
<= box_ceil` guard already ensures this fires once per breakout, not once
per day the price stays elevated — reused unmodified, not reimplemented).

## Width buckets (pinned before any result exists)

Chosen to match the real clustering already observed in the (biased)
leader sample, not tuned after seeing this analysis's own results:

- **Bucket A (control, current default)**: width ≤ 35%
- **Bucket B**: 35% < width ≤ 50%
- **Bucket C**: 50% < width ≤ 100%
- **Excluded from the comparison, reported separately**: width > 100% —
  already established (AEGISLOG, 131.8%) that these aren't consolidations
  at all, just large sustained trends measured over a wide window; no
  box-width setting should be tuned to chase this bucket.

## Forward-return measurement (pinned before any result exists)

Entry price = the NEXT trading day's open after the FRESH BREAKOUT day
(no same-day lookahead, same convention as candidate 18's own `simulate_
day`). Three fixed horizons, all reported, none dropped after the fact:
**+4 weeks, +8 weeks, +12 weeks** (20/40/60 trading days forward),
measured against that day's close. A breakout too close to the end of the
fetched window to reach a given horizon is excluded from THAT horizon's
stat only (not treated as a zero return).

## What's reported, per bucket, per horizon

- n (breakout event count)
- mean and median forward return %
- % of events with a positive return (hit rate)
- Minimum sample size for a bucket/horizon combination to be reported at
  all: **10 events** — below that, reported as "too few, not a read" per
  this project's standing small-sample caveat. (Lower than the usual
  30-trade convention because this is explicitly a first-pass gut check
  over a deliberately modest sample, not a go/no-go verdict — a stricter
  bar would apply before any of this became a live filter.)

## What would make this untrustworthy after the fact

- Changing the width bucket boundaries after seeing which boundary
  produces the most flattering split.
- Reporting only the horizon that looks best and dropping the other two.
- Re-including width > 100% in the "does widening help" comparison after
  seeing it happen to look good.
- Treating a favorable gut-check as sufficient to change
  `core/darvas/weekly_discovery.py`'s live default, or to ship a
  dashboard change, without the cost-adjusted backtest this document
  explicitly defers as a separate next step.
- Silently swapping the systematic sample for a hand-picked or
  outcome-conditioned one if the systematic sample's result is
  disappointing.
