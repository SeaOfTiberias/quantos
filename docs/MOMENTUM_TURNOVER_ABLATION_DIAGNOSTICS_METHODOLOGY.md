# Momentum Turnover Ablation — Follow-Up Diagnostics, Pre-Committed 2026-07-25

Addendum to `docs/MOMENTUM_TURNOVER_ABLATION_METHODOLOGY.md`, not a revision
of it — the original quarterly-vs-weekly result
(`docs/MOMENTUM_TURNOVER_ABLATION_RESULTS.md`) stands as run. Fable's
review of that result (requested by the user, 2026-07-25) withheld a
verdict pending two specific checks, citing this project's own history
(S8-3 and S1 both looked clean on a first pass and failed under exactly
these checks). This doc pre-registers both before running them.

## Diagnostic 1 — point-in-time coverage check

`core/rotation/nifty500_reconstitution.py`'s `EVENTS` list's earliest real
entry is `2023-09-29` (`ind_prs17082023.pdf`) — confirmed by reading the
module directly, not assumed. The ablation's window starts `2022-06-20`
(3 years back from run time, `--years 3` default). Any quarterly rebalance
date before 2023-09-29 ranks against a static backward-projected snapshot
(same universe held constant from `_EPOCH` to the first real event), not
true point-in-time membership — identical in kind to the gap Fable's
review of Strategy 1 found (`NIFTY200_RECONSTITUTION_COVERAGE_START` was
later than that backtest's first rebalance).

**Test**: re-run the quarterly simulation restricted to rebalance dates
on/after 2023-09-29 only, as its own fresh ₹1,000,000 account (not a slice
of the full-window curve, same convention S1's coverage-clean check used)
— report full/coverage-clean side by side.

## Diagnostic 2 — first-half vs second-half stability

Only 14 quarterly rebalances total in the full run — a couple of outsized
quarters could be doing most of the work, the same failure mode that
collapsed Strategy 1's pooled Sharpe from 1.37 (first half) to -0.01
(second half).

**Test**: split the quarterly run's closed trades chronologically by entry
date into two equal-count halves, compute pooled per-trade profit
factor and Sharpe (same `has_positive_edge`-style pooled-trade convention
used throughout this project, not the equity-curve Sharpe) for each half.
Report a degradation flag if first-half Sharpe minus second-half Sharpe
exceeds 0.5 — same threshold S1's own diagnostic used.

## What this diagnostic does NOT do

- Does not sweep to a different rebalance cadence (semi-annual, monthly) —
  that's explicitly deferred per the original methodology doc.
- Does not change the ranking formula, universe, or cost model — all
  identical to the original ablation run.
- Does not itself constitute a pass/fail verdict. Per the original
  methodology doc's framing, this whole ablation (with or without these
  diagnostics) answers "where does the gap to Alpha 50 come from," not
  "is this a validated strategy." A clean result here makes quarterly
  momentum a stronger candidate for a full, separately pre-registered
  strategy test — it does not substitute for one.
