# Darvas Box-Width Backtest — Pre-Committed 2026-09-22 Before Any Result Exists

## Why this exists

`docs/DARVAS_BOX_WIDTH_SENSITIVITY_RESULTS.md` (the gut-check, same day) found
that the live `core/darvas/weekly_discovery.py` cutoff (`max_box_width: 35%`)
excludes a 35-50% band that showed BETTER raw forward returns than the
current "genuine" ≤35% bucket, on 181 unbiased breakout events across a
73-symbol systematic sample, 2024-09 to 2026-09. Per that gut-check's own
pre-registered rule, this is grounds for a full cost-adjusted, stop-managed
backtest as a separate next step — NOT sufficient on its own to change the
live default or ship a dashboard change.

**This document is that next step.** It was deliberately deferred to this
session (not rushed at the tail of the gut-check's own session) for two
reasons recorded at the time: Fyers API quota, and because a backtest that
could plausibly change a live signal deserves the same unhurried
pre-registration as every other candidate this project has built.

## Scope

A REAL, managed Darvas-style trade — entry, genuine stop, genuine target,
cost-adjusted P&L — bucketed by box width, with a genuine time-based
mining/holdout split. This is still, explicitly, **not** a green light to
change anything on its own:

- `core/darvas/weekly_discovery.py`'s live `max_box_width` default (35%)
  is untouched by this script, exactly as the gut-check left it. This
  backtest calls `analyse_symbol` with the same `max_box_width=200.0`
  override the gut-check used, so boxes of any width are classified.
- A pass here is scoped, at most, to the previously-discussed discretionary
  "Leadership panel" dashboard idea, or to widening `max_box_width` itself
  — never to an automated live entry. Per the user's own explicit standing
  instruction this session: no new dashboard additions without a validated
  edge behind them.
- If this backtest does NOT clear its bar (see Verdict below), nothing
  changes anywhere and this candidate closes the same way candidates
  12-20 did.

## What's different from the gut-check (and why each change is needed)

| Gut-check | This backtest | Why |
|---|---|---|
| Raw forward return at fixed horizons | Managed trade: genuine stop, genuine target, time-stop | A raw forward return isn't tradeable — nobody holds through an -8% drawdown hoping for +4.45% at 8 weeks. The stop/target ARE the ones `analyse_symbol` already computes for this exact breakout (see below) — not invented for this document. |
| No costs | `core/risk/costs.py` delivery-style cost model, Clean + Stressed | Every other candidate in this project gates on cost-adjusted, not gross, numbers (S7-3, candidate 15-20). Box width should not be the one exception. |
| 73-symbol systematic sample (stride 7) | Full Nifty 500 + point-in-time historical constituents | The gut-check's own stated next step ("consider widening... now that the gut-check has already justified the effort"). See Universe below for why "full" also means point-in-time, not just today's list. |
| Single 2-year window, reported once | Same 3-year pull, split into mining (earliest 80%) and holdout (most recent 20%) by breakout date | The gut-check's bucket-B-beats-bucket-A finding was observed on ONE window. Re-running the identical window with costs added would just be re-confirming a result already seen, not testing it — the same circularity problem candidate 18's entry-filter methodology explicitly built a mining/holdout split to avoid (`docs/ORB_CONDITION_MINING_METHODOLOGY.md`, replicated 3 weeks apart before being trusted). |

Kept unchanged from the gut-check, deliberately: the signal itself
(`analyse_symbol`, unmodified), the three width buckets and their exact
boundaries (≤35%, 35-50%, 50-100%, >100% excluded as "not a real box") —
these were pinned before the gut-check ran and are not being re-tuned now
that a favorable split exists.

## Universe: full Nifty 500, point-in-time — not today's list applied
retroactively

**This project has already been burned once by exactly this shortcut.**
S8-3's original momentum-rotation backtest ranked every historical week
against `agent/universe_nifty500.txt` — TODAY's constituent list — and its
apparent +8pt alpha turned out to be pure survivorship bias once corrected
(`docs/S8_3_EQUITY_CURVE_RESULTS.md`, memory: quantos-s8-3-survivorship-fix-
status). The fix already exists in this repo:
`core/rotation/nifty500_reconstitution.py`, reconstructing point-in-time
Nifty 500 membership from NSE's own semi-annual reconstitution press
releases (6 broad cycles + 5 mid-cycle corrections, Sept 2023 onward).

This backtest reuses that module unchanged, the same way
`scripts/backtest_equity_curve.py` already does:

```python
snapshots = build_point_in_time_universe(
    frozenset(today_universe), window_start=WINDOW_START,
)
fetch_universe = sorted(frozenset().union(*(s.symbols for s in snapshots)))
```

`fetch_universe` (today's ~500 names plus however many historically-dropped
names the reconstitution surfaces, ~148 extra in the S8-3 case) is what gets
fetched. **A breakout event only counts if the symbol was an actual Nifty
500 constituent on the breakout date** (`eligible_symbols_asof`), checked
once at signal time — a trade already entered is not force-closed if the
index later drops the symbol, matching how S8-3's own fix only gates entry
eligibility, not exit.

**Why this matters specifically for THIS question, not just in general**:
wide-box breakouts (Bucket B, C) are close-definitionally the more volatile
names. If a wide-box breakout is also more likely to blow up badly enough to
get dropped from the index, using today's list only would systematically
hide exactly those failures from Bucket B — inflating its apparent edge
over Bucket A in a way that would specifically flatter this backtest's own
headline question. Point-in-time membership closes that hole.

Reported honestly: this is still not a delisting-survivorship-proof sample
(a stock that left the NSE exchange ENTIRELY, not just the Nifty 500 index,
still won't fetch — it errors and is excluded, same as the gut-check's own
6 errored symbols). That residual gap is smaller than the index-membership
gap this fix closes, and is the same residual gap S8-3's own fix left open.

## Time window

**2023-09-22 to 2026-09-22 (3 years)**, chunked into 3 Fyers requests per
symbol (`<366` days each, same cap and chunking pattern as the gut-check).
Widened from the gut-check's 2 years for two reasons: more raw events for
the mining/holdout split to have power on each side, and because the
`nifty500_reconstitution` module's earliest event is 2023-09-29 — starting
one week earlier keeps this window fully inside its documented coverage
without relying on undocumented pre-2023 extrapolation.

## Mining / holdout split

**Time-based, not random** — a random split lets a later trade's outcome
leak into an earlier one's regime context, same reasoning
`ORB_CONDITION_MINING_METHODOLOGY.md` gives for its own split. Cutoff fixed
here, before any code runs: the window is exactly 1096 days
(2023-09-22 to 2026-09-22); 80% of that is 877 days, giving a split date of
**2026-02-15**. **Earliest 80% of the window by breakout date (2023-09-22 to
2026-02-15) is the mining set; most recent 20% (2026-02-15 to 2026-09-22) is
the holdout set.** This is a genuinely untouched split, not the gut-check's
own already-seen window re-read as if it were fresh — this pull is wider
(full point-in-time universe, not the 73-symbol sample) and longer (3 years,
not 2), so neither sub-window is identical to anything already analyzed.

## Signal (unchanged from the gut-check)

`core/darvas/weekly_discovery.py::analyse_symbol`, walked day-by-day
(`daily[:i+1]`), `cfg={**DEFAULT_CONFIG, "max_box_width": 200.0}`. A
breakout event fires on `status == "FRESH BREAKOUT"`, same as the gut-check
— reused unmodified.

## Width buckets (unchanged from the gut-check)

- **Bucket A (control, current live default)**: width ≤ 35%
- **Bucket B**: 35% < width ≤ 50%
- **Bucket C**: 50% < width ≤ 100%
- **Excluded**: width > 100% (already established as trend, not consolidation)

## The managed trade (new — this is the actual point of this document)

Every rule below is either an EXISTING field `analyse_symbol` already
computes for this exact breakout, or a convention already established
elsewhere in this project. Nothing here is invented fresh for this backtest.

- **Entry**: the NEXT trading day's open after the FRESH BREAKOUT day (same
  no-lookahead convention as the gut-check and candidate 18's `simulate_day`).
- **Position size**: fixed ₹100,000 notional per trade — the same
  `NOTIONAL_PER_TRADE` constant `scripts/backtest_rs_momentum.py` (S8-3) uses,
  for realistic absolute cost figures. Not capital-constrained across
  concurrent positions: this is a discretionary candidate-list signal (like
  candidates 15/18/19/20), not a fixed-slot rotation, so overlapping
  positions across symbols are independent trades, not competing for one
  slot.
- **Stop**: `result.sl_price` — box ceiling minus `sl_ceil_buffer_pct` (2%
  by default), the box's own live stop rule, computed by `analyse_symbol`
  itself. Checked against each subsequent day's LOW; hit = exit that day at
  the stop price.
- **Target**: `result.mm_target` — box ceiling plus one box height (the
  measured-move target), also computed by `analyse_symbol` itself. Checked
  against each subsequent day's HIGH; hit = exit that day at the target
  price.
- **Same-day double-touch**: if a single day's range spans both the stop and
  the target, the STOP wins (conservative, standard backtest convention,
  pinned here before any run — never decided per-trade after seeing which
  assumption flatters the result more).
- **Time-stop**: if neither stop nor target is hit within 60 trading days
  (12 weeks — the gut-check's own longest horizon), force-close at that
  day's close. No trade runs indefinitely.
- **Data-ends-first**: a trade still open when the fetched window itself
  ends is force-closed at the last available close, flagged separately, and
  excluded from the pass/fail metrics (its outcome is incomplete, not a
  real result) — same spirit as the gut-check excluding horizons a breakout
  couldn't reach.

## Cost model

Reuse `scripts/backtest_rs_momentum.py`'s `DELIVERY_COST_MODEL` **imported
directly, unmodified** — a multi-week Darvas swing hold has the same
CNC/delivery product character as that momentum rotation's weekly holds
(Rs0 discount-broker delivery brokerage, 0.1%-both-legs-equivalent STT,
delivery stamp duty, 10bps/leg slippage for a non-urgent weekly-hold entry).
No new cost tuning for this document.

**Stressed variant**: the same cost model plus an additional 15bps/leg
slippage penalty, matching candidate 18's own stress convention
(`ORB_OPTIONS_SCALPING_METHODOLOGY.md`). Both Clean and Stressed are
computed and reported for every bucket/split; **Stressed is the variant
that gates the verdict**, per this project's established practice that the
harsher cost assumption gates pass/fail, not the friendlier one.

## Metrics

Reuse `core/backtest/parser.py`'s `BacktestTrade` / `_compute_metrics`
unmodified — the same machinery S7-3, S8-3, and candidate 18 already use.
Per bucket, per split (mining/holdout), per cost variant (Clean/Stressed):
trade count, win rate, profit factor, Sharpe, net P&L%, average bars held.

**Minimum sample size to report a bucket/split combination at all: 30
trades** — this project's standard bar (used by `ORB_CONDITION_MINING_
METHODOLOGY.md`'s own mining/holdout gate), not the gut-check's deliberately
lowered 10 (that was an explicit first-pass exception; this is a real,
potentially-live-changing backtest and gets the real bar). Below 30, reported
as "too few, not a read."

## Verdict — what would actually justify a dashboard change

`BacktestMetrics.has_positive_edge` (`profit_factor > 1.0 AND sharpe_ratio
> 0.5`) is this project's own existing bar, unchanged, used by every other
candidate. This backtest CLEARS its bar only if **all three** hold, on the
Stressed cost variant:

1. **Mining confirmation**: Bucket B clears `has_positive_edge` on the
   mining set.
2. **Holdout confirmation**: Bucket B clears `has_positive_edge` on the
   HOLDOUT set too — the step that actually distinguishes a real effect
   from a mining-set fluke, same logic as condition-mining's own step 3.
3. **Control comparison**: Bucket A (≤35%, today's live cutoff) does NOT
   clear `has_positive_edge` on the holdout set — confirming the current
   cutoff really is the worse one on fresh data, not just noise around a
   comparison that was never really different.

If Bucket B's holdout sample lands below the 30-trade minimum (a real risk
— it was the smallest bucket in the gut-check, ~10% of all events), this
backtest is reported as **INCONCLUSIVE on the question it was built to
answer**, not stretched to a verdict either way by lowering the bar after
seeing the number.

Only if all three hold does a dashboard change (the Leadership panel idea,
or widening `max_box_width`) become warranted — not before, per the user's
explicit instruction.

## What would make this untrustworthy after the fact

- Moving the 80/20 mining/holdout cutoff after seeing a weak holdout result.
- Lowering the 30-trade minimum below its pre-registered value because
  Bucket B's holdout count came up short.
- Reporting Clean and omitting Stressed, or letting Clean's more flattering
  number substitute for Stressed in the verdict.
- Re-tuning the 35%/50% bucket boundaries now that a full cost-adjusted
  result exists for the current boundaries.
- Silently dropping the point-in-time universe correction back to today's
  list if the full run's API cost turns out heavier than expected.
- Treating a mining-only pass (without a holdout confirmation) as
  sufficient to change anything.
