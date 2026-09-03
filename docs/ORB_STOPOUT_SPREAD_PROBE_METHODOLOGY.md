# ORB Options Scalping — Event-Triggered Stop-Out Spread Probe: Stopping Rule, Pre-Committed 2026-09-03 Before Any Exit Event Exists

## Why this exists

Candidate 18 (ORB options scalping) passes its own locked-final cost
variant (Stratified — see `docs/ORB_SCALPING_RESULTS.md`), but every
spread sample behind that cost model, including the Stratified rate
itself, was measured on a fixed 3x/day clock during calm market moments
(`scripts/probe_orb_scalping_real_spreads.py`). The strategy's real exits
are stop-outs, which by nature happen during fast-market moments a fixed
clock never observes. `scripts/probe_orb_scalping_stopout_spreads.py`
(built and deployed 2026-09-03,
[[quantos_orb_options_scalping_status]]) closes that gap by watching the
live signal and snapshotting the real bid-ask spread at the instant a
stop-out condition actually fires.

This candidate's whole history is a cautionary tale about looking at
cost-model results before a stopping rule exists: four successive
post-hoc cost variants (Clean→Stressed→Harsh→Real-spread→Sampled-spread)
each individually well-motivated, but with no pre-registered stopping
rule and a strong stop-when-favorable pattern Fable's 2026-07-31 review
called out explicitly. This document exists so the SAME mistake doesn't
happen to the stop-out probe's data. As of this writing the probe has
logged exactly one "entry" row and **zero "exit" rows** — this is
genuine pre-registration, not a post-hoc rationalization of a result
already seen.

## The question being tested

Is the calm-time, fixed-clock-derived Stratified spread rate
(`STRATIFIED_SPREAD_SLIPPAGE_BPS`, `core/orb_scalping/costs.py`) still a
reasonable proxy for the real spread AT the moment a stop actually fires
— or is real stop-out execution meaningfully costlier, the way the
single 2026-07-28 Real-spread snapshot (107.5bps NIFTY / 65bps
BankNifty) once suggested before it was traced to a contaminated
post-close/wrong-contract reading (see the memory's "Both remaining
Fable items ROOT-CAUSED" section)? That snapshot was never confirmed as
a real stop-out-moment reading — this probe is the first mechanism that
can actually produce one.

## Minimum sample gate

**N ≥ 20 stop-out ("exit") events per index, NIFTY and BankNifty tracked
and reported independently — never pooled**, same standing convention as
every other measurement in this candidate's history. 20 is not a new
arbitrary number: it reuses the exact threshold this codebase already
treats as a floor for trusting an empirically-derived rate
(`core/risk/trade_history.py`'s Kelly-sizing minimum, `agent/main.py`),
rather than inventing a fresh one.

Per-`trigger_reason` (`stop` / `trailing_stop` / `premium_stop`) or
per-expiry-day breakdowns are **informational only** at any sample size
this probe is likely to reach in a reasonable window — real stop-out
events are inherently rarer than daily trades (a session that ends via
`session_flatten` produces no sample at all, by design — see the probe's
own docstring). Splitting the already-thin N further would produce
strata too small to trust. Report them alongside the pooled read once
the gate clears, but do not treat an underpowered sub-split as a
standalone finding.

## Minimum time gate

**At least 4 calendar weeks of the timer actually running during market
hours**, starting from **2026-09-03** (the date `quantos-orb-stopout-
probe.timer` was enabled on the VM) — so the earliest this gate can
clear is **2026-10-01**. This does not track "4 weeks since the first
exit event" or infer a start date from the data; the clock is a fixed,
disclosed instant chosen before any exit event existed, so it cannot
drift with the data the way an inferred start date could.

Rationale: stop-out events aren't tied to a structural cycle the way
option expiries are (the earlier sampled-spread gate required "2+ NIFTY
weeklies + 1 BankNifty monthly" for exactly this reason), so there is no
clean calendar-cycle analog here. A flat multi-week floor exists for the
same underlying worry — don't let one unusually calm or unusually
volatile week dominate the read.

## Stopping rule mechanics

1. **Both gates must clear before any conclusion is drawn.** N≥20 alone
   is not sufficient if fewer than 4 weeks have elapsed (a lucky burst of
   volatile days could complete the count early); 4 weeks alone is not
   sufficient if N<20 (events may simply be rarer than expected).
2. **If time has passed but N<20, wait longer.** Do not lower N to make
   a calendar date "count" — extend the window instead. Re-run the gate
   check later, or schedule another reminder.
3. **No informal peeking that reveals the actual numbers before both
   gates clear.** `scripts/check_orb_stopout_probe_gate.py` (below) is
   built to report ONLY gate status (N so far, elapsed time, MET/WAITING
   per index) until both gates are satisfied for an index — it will not
   print spread statistics for that index before then, specifically so a
   curious mid-window re-run cannot bias behavior the way the earlier
   "stop-when-favorable" cost-variant sequence did.
4. **One reminder is scheduled for 2026-10-01** (the earliest the time
   gate can clear) as a check-IN point, not an automatic verdict — cloud
   routines cannot SSH into the VM to read the probe's own log
   (`data_cache/orb_scalping_stopout_spread_samples.csv` is VM-only,
   gitignored), so this is a prompt to run the gate check, same
   limitation and same pattern as the 2026-08-31 sampled-spread
   recheck reminder. If N<20 for an index at that point, the correct
   action is to note "gate not yet met" and schedule a further-out
   reminder, not to force a read.

## Verdict computation, once both gates clear (for a given index)

Compute BOTH the mean and the median of `spread_pct_of_mid` across that
index's exit rows — report both, not just the mean, because a mean is
exactly the statistic a single contaminated reading (the 2026-07-28
Real-spread snapshot) previously distorted; the median is more robust to
one outlier row surviving into the sample.

Convert the chosen statistic to an equivalent round-trip bps rate (the
same `50 * spread_pct` conversion `core/orb_scalping/costs.py` already
uses for `REAL_SPREAD_SLIPPAGE_BPS`/`SAMPLED_SPREAD_SLIPPAGE_BPS`/
`STRATIFIED_SPREAD_SLIPPAGE_BPS`), substitute it for that index's
Stratified rate, and **rerun `scripts/backtest_orb_scalping.py`** to see
whether PF/Sharpe still clears the pre-registered bar. This is the
decision-relevant test — identical method to every prior cost-variant
transition in this candidate's history (Stressed→Harsh→Real-
spread→Sampled-spread→Stratified), chosen for direct comparability
rather than an arbitrary "is it more than 2x the old rate" threshold.

**PASS** (stop-out spread does not flip the verdict): treat Stratified
as a validated proxy even at real stop-out moments — meaningful evidence
toward a real-capital go-live discussion (still separately gated by
[[feedback_confirm_before_scaling_capital]]).

**FAIL** (stop-out spread flips PF/Sharpe below the bar for that index):
the candidate's PASS was built on a cost model that understates real
execution cost exactly where it matters most — the same failure mode
that killed candidate 15 and nearly killed this one. Report as a genuine
reversal, the same way the single Real-spread snapshot was originally
reported, this time with a trustworthy sample behind it.

## What this document deliberately does not attempt

No pooling NIFTY and BankNifty. No stopping early because the number
looks favorable, or waiting longer because it looks unfavorable — the
gates above are the only trigger to look. No silent lowering of N=20 if
events prove rarer than expected over 4 weeks; extend the time window
instead and say so explicitly when reporting.
