# Darvas Trailing-Stop Backtest — Pre-Committed 2026-09-22 Before Any Result Exists

## Why this exists

`docs/DARVAS_BOX_WIDTH_BACKTEST_RESULTS.md` (same day) found every width
bucket loses money once a real managed trade is applied. Digging into one
real example (WELCORP's genuine 2025-05-30 breakout, 35.5% width) showed
why: the trade's ENTRY was fine (a real box, real volume confirmation) but
its STATIC stop (2% below the entry box's ceiling) closed it at -5.2% just
17 days later — while the stock went on to +193.7% over the next 15
months. Low win rates across every bucket in the box-width backtest
(20-29%) are consistent with this being a systemic pattern, not a one-off:
the static stop may be clipping winners before a real trend has room to
develop, rather than the entries themselves being bad.

**This document tests that specific, narrower hypothesis**: does trailing
the stop (and target) as new, higher boxes confirm — instead of fixing
both at the entry box's values — recover an edge the static-exit backtest
didn't find? This is a single-variable follow-up, not a new investigation.

## Explicit anti-drift rule

The user flagged, correctly, that this investigation started from one
anecdote (originally misidentified, then corrected to WELCORP) and must
not conclude anything from that one stock. **Every parameter below is
copied unchanged from `docs/DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md`
except the exit rule.** Universe, window, signal, width buckets, cost
model, mining/holdout split, minimum sample size, and verdict structure
are all identical to the already-run backtest, so any change in the
verdict is attributable to the exit rule alone, not to a different
universe, window, or bucket definition. Where anything below reads
identically to that document, it is intentional, not a copy-paste
oversight.

**Unchanged from `DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md`**: full
point-in-time Nifty 500 universe (`core/rotation/nifty500_reconstitution.py`,
648 symbols), 2023-09-22 to 2026-09-22 window, `analyse_symbol` with
`max_box_width=200.0`, FRESH BREAKOUT entry (next day's open), the three
width buckets (≤35%, 35-50%, 50-100%), `DELIVERY_COST_MODEL` + Stressed
(+15bps/leg), the 2026-02-15 time-based 80/20 mining/holdout split, the
30-trade minimum sample size, and the 3-condition verdict structure
(Bucket B passes mining AND holdout, Bucket A control does not pass
holdout — all on Stressed).

## What changes: the exit rule only

**Rejected approach, considered and ruled out**: `core/darvas/box.py`'s
`next_trailing_stop()` looks like the obvious reuse (it exists, it's named
for exactly this), but it calls `detect_darvas_boxes()`, which caps box
width at `BOX_MAX_WIDTH_PCT = 8%` — a completely different, much tighter
box definition built for the Stage-B intraday confluence scanner (15m/1h
timeframes). Every box this investigation has ever measured is 20%+ wide;
that function would essentially never find a matching box on this data.
Using it would silently swap in a different signal's box-detection
algorithm mid-trade, not "add trailing to the same box" — ruled out to
avoid exactly that drift.

**What's used instead**: the SAME algorithm already used for entry
detection (`weekly_discovery.py::analyse_symbol`, called incrementally
through each new day, exactly as it already is for finding the entry
signal) — re-evaluated once per day while a trade is open, to detect
whether a NEW, higher box has confirmed. Nothing new is invented; this is
the same `_detect_box` state machine "stacking" a second box on top of the
first as the stock consolidates again higher, which the module already
does natively (per its own docstring: "Reset — start hunting for the next
box" after each confirmation).

Rule, applied once per day while a trade is open:

1. Check the day's low against the CURRENT stop and high against the
   CURRENT target (same same-day-double-touch-favors-the-stop convention
   as the static-exit backtest).
2. If neither is hit, re-run `analyse_symbol` through that day's close. If
   it reports a box with a HIGHER ceiling than the box currently governing
   the trade, and that new box's own `sl_price` is higher than the current
   stop, raise the stop to the new `sl_price` (never lowered). Likewise
   raise the target to the new box's `mm_target` if it's higher than the
   current target.
3. Repeat until the (possibly-raised) stop or target is hit, or the fetch
   window ends.

**No fixed time-stop.** The static-exit backtest's 60-trading-day cap is
dropped for this variant, deliberately: the whole point of trailing is to
let a genuine trend run as long as it keeps making higher boxes, and an
arbitrary calendar cap would reintroduce the same premature-cutoff problem
this test exists to fix.

**A trade still open when the fetch window ends is marked-to-market at
the last available close and INCLUDED in the metrics — not excluded.**
This is a deliberate departure from the static-exit backtest's own rule
(which excluded "data-ended" trades as incomplete). Reasoning: with no
time-stop, a real trending winner (like WELCORP, whose real position is
still open and unstopped as of today) is exactly the kind of trade most
likely to still be open at the window's end. Excluding "still open"
trades here would systematically discard the very outcomes this variant
is designed to capture, biasing the result against trailing before it's
even tested. Reported separately (count and aggregate mark-to-market P&L)
so this isn't hidden either.

## Metrics and verdict

Identical machinery and identical verdict structure to
`DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md`: `core/backtest/parser.py`'s
`BacktestTrade`/`_compute_metrics`, `has_positive_edge` (PF>1.0 AND
Sharpe>0.5), 30-trade minimum, per bucket per split per cost variant,
Stressed gates the verdict. The three verdict conditions are unchanged:
Bucket B (35-50%) must clear the bar on mining AND holdout/Stressed, and
Bucket A (control) must NOT clear it on holdout/Stressed.

**This backtest answers one question**: does trailing the stop/target
rescue an edge the static-exit version didn't find? A pass here would be
grounds to reconsider the exit rule (not the box-width cutoff) as the
live discretionary panel's design — still not the automated-entry green
light, same standing limits as the prior document.

## What would make this untrustworthy after the fact

- Changing the universe, window, buckets, cost model, or verdict
  conditions from the already-run backtest's values -- any of those
  would make a changed result ambiguous between "trailing helped" and
  "something else changed."
- Silently re-introducing a time-stop only after seeing that removing it
  helped (or hurt).
- Excluding still-open trades from the metrics after seeing that
  including them helped the verdict, or vice versa.
- Treating a pass here as sufficient for anything beyond the discretionary
  panel / `max_box_width` question -- no automated-entry claim follows
  from this document either.
