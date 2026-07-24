# Momentum Turnover Ablation — Methodology, Pre-Committed 2026-07-25 Before Any Result Exists

## Why this exists

Fable's 2026-07-25 review (called in after the user asked to pivot toward
discretionary-trading infra) found a pattern across this project's two
momentum implementations that had never been isolated: **Nifty Alpha 50** —
itself a real, rules-based momentum index — earned Sharpe 0.97–1.04 and
CAGR 20–22% over the same windows where S8-3's 52-week-high rotation
(`docs/S8_3_EQUITY_CURVE_RESULTS.md`) earned Sharpe 0.34 and CAGR 4.0%, and
Strategy 1's dual-momentum (`docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md`)
earned Sharpe 0.45–0.70. That gap is not evidence the momentum factor
itself is absent from this market — Alpha 50 proves it isn't — it's
evidence this project's specific execution wrapper (weekly rebalance,
tight rank-dropout/stop exits) is losing a large fraction of the raw
factor's value in translation. That gap has never been isolated with a
controlled test. This is that test.

**This is a diagnostic ablation, not a new strategy pre-registration.**
There is no `has_positive_edge` pass/fail bar here — the question is
narrower: *how much of the Sharpe/CAGR gap to Alpha 50 closes when
turnover alone is reduced, holding the ranking formula, universe, costs,
capital, and window fixed?* If most of the gap closes, that's a real,
actionable lead for a future momentum candidate. If it doesn't move much,
turnover is ruled out as the primary explanation and the gap points
elsewhere (the ranking formula itself, position sizing/weighting, or
something structural to Alpha 50's own methodology that isn't
replicable by a discretionary-adjacent rotation).

## What is held fixed (reused unchanged, not rebuilt)

- **Ranking function**: `core/rotation/ranker.py`'s `rank_universe()` —
  52-week-high proximity (`close / rolling_252d_high`), `TOP_N = 20`,
  `LOOKBACK_DAYS = 252`. This module's own docstring forbids tuning these
  after seeing a result; this ablation does not touch it.
- **Universe**: point-in-time Nifty 500 membership,
  `core/rotation/nifty500_reconstitution.py`, same historical
  add/remove-event reconstruction S8-3's own corrected run used — not
  today's list applied retroactively.
- **Simulation engine**: `core/rotation/equity_curve.py`'s
  `simulate_portfolio()`, unchanged — same day-by-day mark-to-market loop,
  same `_size_new_entrants` position sizing.
- **Exit rule**: `exit_rule="rank_only"` — rank-dropout only, no
  stop-loss/EMA variant layered on. This isolates rebalance *frequency* as
  the single variable; adding a stop-loss on top would confound two
  changes into one test.
- **Cost model**: `DELIVERY_COST_MODEL`
  (`scripts/backtest_rs_momentum.py`), unchanged.
- **Capital, position size, window**: ₹1,000,000 initial capital,
  ₹50,000/position, 3 years — identical to S8-3's own equity-curve run, so
  the existing `docs/S8_3_EQUITY_CURVE_RESULTS.md` numbers serve directly
  as the control without needing to be re-run.
- **Benchmarks**: same buy-and-hold Nifty 500 and Nifty Alpha 50
  comparisons, same `compute_alpha()`.

## What varies — the one thing being tested

**Rebalance cadence: quarterly instead of weekly.** Last NIFTY trading day
of each calendar quarter (analogous to `rebalance_dates()`'s
last-day-of-ISO-week logic, grouped by `(year, quarter)` instead of
`(year, week)`), rather than every week. This is the only variable
changed. Not chosen by sweeping multiple cadences and picking the best —
quarterly is a single pre-registered middle ground between S8-3's weekly
churn and Alpha 50's real semi-annual rebalance, cheap to test once. If
this shows partial recovery, semi-annual becomes a natural follow-up; it
is explicitly NOT run in this pass, to avoid the appearance of tuning
until something looks good.

## Reporting

Both runs (existing weekly baseline, new quarterly variant) reported
side by side: total return, CAGR, Sharpe, max drawdown, trade count, and
alpha vs both benchmarks. Plus one derived number not in either individual
report: **% of the Sharpe/CAGR gap to Alpha 50 closed** by the cadence
change alone.

## What would make this untrustworthy after the fact

- Also changing the ranking formula, TOP_N, or LOOKBACK_DAYS "while I'm in
  there" — that's a different, separately pre-registered test.
- Adding a stop-loss/EMA exit variant to the quarterly run but not the
  weekly baseline (or vice versa) — confounds two variables.
- Trying multiple rebalance cadences (monthly, semi-annual, etc.) and
  reporting only the best-looking one. Quarterly is the single
  pre-registered choice; a different cadence is a new pass.
- Treating a partial gap closure as proof of a tradeable edge — this
  ablation answers "where does the gap come from," not "is this now a
  validated strategy." A positive finding here is a lead for a future
  properly pre-registered candidate, not a result to act on directly.
