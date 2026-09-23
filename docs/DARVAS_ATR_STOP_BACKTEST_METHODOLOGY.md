# Darvas ATR-Scaled Stop Backtest — Pre-Committed 2026-09-23 Before Any Result Exists

## Why this exists

`docs/DARVAS_TRAILING_STOP_BACKTEST_RESULTS.md` improved every bucket over
the static-exit backtest, but Bucket B's mining set landed at exactly
breakeven (PF 1.00, Sharpe 0.01) — short of its own bar. Looking at what's
actually driving that number: **87-90% of trades in both backtests exit
via stop, only 10-12% via target**, and the small tail of target-hits
carries the entire positive result (median return negative, mean
positive, in both mining and holdout). WELCORP's own real trade makes the
mechanism concrete: its trailing exit was IDENTICAL to its static exit
(-5.2% in 17 days), because trailing only raises the stop after a NEW box
confirms — the INITIAL stop distance is untouched by trailing, and that
initial distance is a fixed `sl_ceil_buffer_pct = 2.0%` below the
ceiling, applied uniformly regardless of the stock's own volatility. A
stock with a naturally noisy 4-5%/day range (typical ATR% observed on
WELCORP/WELSPUNLIV this session) gets shaken out by ordinary movement at
the same fixed distance as a calm one.

**This document tests that specific, narrower hypothesis**: does sizing
the stop to the stock's own volatility (ATR-scaled) instead of a fixed
percentage reduce the whipsaw-driven stop-out rate enough to clear the
bar the trailing-stop backtest fell just short of?

## Explicit anti-drift rule and lineage

Same discipline as the trailing-stop document: **every parameter below is
copied unchanged from `docs/DARVAS_TRAILING_STOP_BACKTEST_METHODOLOGY.md`
except the stop-distance calculation.** This is the third link in an
explicit chain, each a single-variable diff on the one before it:

1. Box-width backtest (static exit, fixed % stop below ceiling) — FAILED.
2. Trailing-stop backtest (stop AND target trail as new boxes confirm,
   still a fixed % buffer) — improved every cell, still FAILED (Bucket B
   mining exactly breakeven).
3. **This document**: trailing stop/target exactly as in (2), except the
   BUFFER used to compute the stop (both the entry stop and every
   subsequent trailed stop) is ATR-scaled instead of a fixed percentage.
   The target formula is untouched — this document tests the stop
   distance specifically, not the target (a "drop the fixed target
   entirely" idea was also raised this session and is explicitly a
   SEPARATE, not-yet-run candidate — not bundled in here, to keep this a
   single-variable test).

**Unchanged from `DARVAS_TRAILING_STOP_BACKTEST_METHODOLOGY.md`**: full
point-in-time Nifty 500 universe (648 symbols), 2023-09-22 to 2026-09-22
window, `analyse_symbol` with `max_box_width=200.0` for entry detection,
the three width buckets, `DELIVERY_COST_MODEL` + Stressed (+15bps/leg),
the 2026-02-15 mining/holdout split, the 30-trade minimum, the
3-condition verdict structure, no fixed time-stop, still-open trades
marked-to-market and INCLUDED (not excluded).

## What changes: the stop buffer only

**ATR source**: `core/darvas/weekly_discovery.py`'s own `_atr()` helper
(Wilder's ATR, period 14, on daily bars) — the SAME function
`analyse_symbol` already calls internally for its own breakout-confirmation
math (`atr_val * cfg["atr_mult_bo"]`). Reused directly, not reimplemented,
so there is no second, subtly-different ATR definition introduced.

**Multiplier: 2.0× ATR(14), a single pre-registered value.** This is the
standard "Chandelier exit" convention from classical trend-following
technical analysis — an external anchor, not a value fitted to this
project's own data. No sensitivity sweep across multiple multipliers is
run: testing 1.5×/2.0×/3.0× side by side and reporting whichever looks
best would be a parameter hunt dressed up as a single test. One value,
decided before any result exists, is the whole point of this document.

**Stop formula, replacing `sl_ceil_buffer_pct`**: for the entry box,
`stop = box_ceiling - 2.0 * atr14`. When trailing raises the stop to a new,
higher-confirmed box (same trigger condition as the trailing-stop
document — a new box with a higher ceiling), the new stop is
`new_box_ceiling - 2.0 * atr14_as_of_that_day` (ATR recomputed at the time
of the new box, not frozen at entry — a stock's volatility regime can
shift over a multi-week hold, and freezing the entry-day ATR would silently
reintroduce a fixed-distance assumption for every subsequent trail).
Still only ever raised, never lowered, same as the trailing-stop rule.

**Target**: unchanged — `box_ceiling + (box_ceiling - box_floor)` (measured
move), trailed to the new box's own measured move exactly as before. Not
ATR-scaled; this document isolates the stop.

## Metrics and verdict

Identical machinery to the trailing-stop document: `core/backtest/
parser.py`'s `BacktestTrade`/`_compute_metrics`, `has_positive_edge`
(PF>1.0 AND Sharpe>0.5), 30-trade minimum, per bucket per split per cost
variant, Stressed gates the verdict. Same three verdict conditions
(Bucket B passes mining AND holdout/Stressed; Bucket A control does not
pass holdout/Stressed).

## What would make this untrustworthy after the fact

- Testing multiple ATR multipliers and reporting the best one, instead of
  the single pre-registered 2.0×.
- Also loosening the target (or the width buckets, universe, window,
  split, or cost model) and attributing any improvement to the stop
  change alone.
- Freezing ATR at entry for trailed stops after seeing that a frozen
  value produces a more flattering result than a recomputed one.
- Treating a pass here as sufficient for anything beyond the discretionary
  panel / `max_box_width` question — no automated-entry claim follows.
