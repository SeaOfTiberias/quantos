# ORB Options Scalping — Condition-Mining Methodology, Pre-Committed 2026-09-03 Before Any Result Exists

## Why this exists

Candidate 18 (`docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md`,
`quantos_orb_options_scalping_status` memory) clears every backtest gate
this project applies to a strategy: both NIFTY and BankNifty pass the
locked-final Stratified cost variant, and every specific bug an
adversarial review found has been root-caused and fixed. It fires on
~95-98% of trading days — a near-daily system, not a selective one. The
user's ask: instead of firing every day, can it be gated to fire only on
days whose conditions resemble the days it has historically won on?

**This is NOT a new backtest of the signal.** The signal (opening range,
trailing stop, DTE floor, 25% premium stop) stays frozen exactly as
candidate 18 locked it. This document only pre-registers a search for a
**conditional filter** applied on top of an unchanged signal.

## The trap this document exists to avoid

This project has run this exact kind of search five times before, under
the name "regime/vol-conditioning" (`quantos_regime_signal_redesign_plan`
memory): a VIX-level classifier, an IV−RV spread, NIFTY+BankNifty option
skew, NIFTY+BankNifty ATM IV term structure, and RBI/Budget event
proximity. **All five failed**, each independently Fable-reviewed.
Separately, `docs/VRP_METHODOLOGY.md` bans, in writing, *"reporting a
regime-filtered or vol-event-excluded subset as the headline instead of
the full unfiltered sample"* — building a gate and then checking which
subset of an already-run backtest it would have rescued is a rescue
narrative, not a finding, even when no signal parameter is touched.

Mining candidate 18's own trade outcomes for "what conditions made this
trade win" is the same maneuver. It is not banned — this project has a
standard answer for how to do this kind of search honestly: pre-register
the candidate conditions and the pass bar **before** looking at which
trades won, hold out data the mining process never sees, and get an
independent review before treating any result as real. This document is
that pre-registration.

## Scope

**Candidate 18 (ORB) only.** Candidate 17 (pairs trading v2) is explicitly
OUT of scope for this exercise — it nets an overall loss across its full
tested history (pooled Sharpe 0.14, CLOSED FAIL). Mining "which conditions
made a net-losing strategy win" is much shakier ground than doing the same
search on a strategy with a real overall edge: on 17, an "informative"
condition found this way is more likely to just be the noisiest slice of
an already-negative sample. If this exercise says anything useful about
17, that is a separate, later, explicitly-flagged decision — not a side
effect of this one.

**Both indices, reported independently, never pooled** — same discipline
as candidate 18 itself.

## Candidate conditions (the actual pre-registration)

Everything on this list was chosen specifically because it is **not** a
cut of the data family that already failed 5-for-5 (no VIX level, no
IV−RV spread, no skew, no term structure, no event-day calendar, no
`core/regime/classifier.py`). Five primary candidates, plus one secondary
diagnostic:

1. **Index trend stage at entry** — Weinstein-style classification
   (`core/vault/stages.py`'s existing stage DSL, applied to the NIFTY/
   BankNifty index series itself rather than a single stock): is the
   index in Stage 2 (advancing) vs Stage 1/3/4 on the trade's entry date?
   Trend-context, not a volatility-level classifier — a genuinely
   different kind of feature from everything in the closed search.
2. **Day of week** of entry.
3. **Opening-range width relative to its own trailing history** — is
   *today's* first-15-minute range wide or narrow compared to, say, its
   trailing 20-day average range. A feature of the signal's own
   construction, never tested as a conditioning variable before.
4. **Gap at open** — today's 09:15 index level vs yesterday's 15:30
   close, signed and as a percentage.
5. **Days-to-expiry bucket** at entry (already known to interact with
   *cost*, via the DTE floor and the Stratified spread split — this asks
   whether it also interacts with *win rate*, independently of cost,
   which has never been checked).

Secondary, diagnostic only — **not eligible to become a firing condition
on its own**, since it is observed at exit, not at the moment a trade
would fire:

6. **Exit reason** (`trailing_stop` / `stop` / `premium_stop` /
   `session_flatten`) cross-tabulated against conditions 1-5. This can
   only ever explain *why* a conditioned subset won or lost after the
   fact (e.g. "condition X's losses are mostly premium-stop exits") — it
   can inform which of 1-5 to trust more, but it cannot itself gate a
   future trade, because you cannot know a trade's exit reason before it
   happens.

**No condition outside this list of six may be added after seeing mining-
set results.** A condition that occurs to someone after looking at the
data is a new, separately pre-registered follow-up, not an amendment here
— same rule candidate 18's own methodology doc holds itself to.

### Exact parameters, pinned before any code runs

- **Condition 1 (stage)**: `Stan_Weinstein_Stage_Analysis.md`'s existing
  `quantos-stages` clauses (`obsidian_vault/QuantOS/brain/`), applied
  unmodified to the index's own daily close/high/low/volume series — no
  new clauses written for this exercise.
- **Condition 3 (range width)**: today's opening-range width (high−low of
  the first 3 five-minute candles, same window the signal itself uses)
  divided by the trailing 20-trading-day average of that same day's-own
  opening-range width, entry day excluded. Ratio > 1 = wider than usual.
- **Condition 4 (gap)**: today's first 5-minute candle's open vs the prior
  trading day's daily close, signed percentage.
- **Condition 5 (DTE bucket)**: `days_to_expiry` (already computed by
  `resolve_nifty_expiry`/`resolve_banknifty_expiry`) bucketed as `0-1`,
  `2-4`, `5-9`, `10+` — four buckets, fixed before any result exists.

### Which predicate is actually tested per condition (pinned before any code runs)

The five features above are continuous or multi-valued; `evaluate_condition`
needs a binary true/false predicate. Each one is fixed here, not decided
while writing the extraction script, and not one predicate per possible
value (testing all 5 weekdays or all 4 DTE buckets separately multiplies
the number of chances to find a spurious pass on an already-modest sample
— exactly the multiple-comparisons risk this project's own history warns
about):

- **Stage**: `stage is Stage.ADVANCING` (Stage 2) vs everything else
  (including unclassified, which the predicate returns `None` for, per
  the exclusion rule below).
- **Day of week**: `Monday or Friday` vs `Tuesday–Thursday` — the two
  days with an a priori market-microstructure story (Monday: weekend gap
  risk; Friday: proximity to NIFTY's own weekly expiry), not a five-way
  split of the whole week.
- **Range width**: two SEPARATE conditions, `wide` (ratio > 1.25) and
  `narrow` (ratio < 0.75) — symmetric bands around 1.0, each evaluated
  and reported on its own, not combined.
- **Gap at open**: `big gap`, `|gap_pct| > 0.3` — a round number close to
  NIFTY's typical absolute gap size, picked before looking at any trade
  outcome, not tuned to a distribution.
- **DTE bucket**: two SEPARATE conditions, `0-1` (near expiry) and `10+`
  (far from expiry) — the two ends with an a priori liquidity/theta
  story. The middle buckets (`2-4`, `5-9`) are reported as context in the
  raw extraction but are NOT evaluated as their own pass/fail hypothesis.

Any predicate that cannot be evaluated for a trade (e.g. an unclassified
stage) excludes that trade from BOTH the true and false subsets for that
condition only — it stays in the unconditional baseline.

## Data extraction

`run_index_backtest` (`core/orb_scalping/backtest.py`) is reused for its
building blocks (`simulate_day`, `reconstruct_premium`, `resolve_nifty_
expiry`/`resolve_banknifty_expiry`, `is_nifty_weekly_expiry_day`/
`is_banknifty_monthly_expiry_day`) but **not called directly** — its
return type (`BacktestTrade`) drops `exit_reason` and CALL/PUT direction
on the way to TradingView's trade-list shape, and conditions 1-5 need the
underlying 5-minute candle series around each trade's entry, which
`BacktestTrade` also does not carry. A new extraction script builds one
row per trade directly from `IndexTrade` + `PremiumTrade` (which already
carry `exit_reason`, `direction`, and timestamps) plus the six condition
values computed against the day's own candle series, joined to the
**Stratified** (locked-final) net P&L for that trade — same variant any
go/no-go decision in this project reads. Output: one CSV per index,
gitignored under `data_cache/` like every other real-market artifact this
project has produced, with the code that reproduces it committed.

## Mining / holdout split

**Time-based, not random** — a random split lets a later trade's outcome
leak information into an earlier trade's condition-fit indirectly through
shared regime state, and this project's own no-lookahead discipline
treats that as a real risk, not a formality. Cutoff: the most recent 20%
of each index's trade history **by calendar date**, computed once the
real data is fetched (not fixed in advance to a specific date, since
trade density is not perfectly time-uniform — but the 80/20 split point
itself is fixed by this rule before anyone looks at which subset performs
how). Mining set = earliest 80%; holdout = most recent 20%. Reported
separately per index (NIFTY and BankNifty do not share a cutoff date).

## Pass bar for a mined condition

A candidate condition from the list of five is only reported as
**informative** if ALL of the following hold, checked in this order:

1. **Minimum sample size**: the "condition true" subset has at least 30
   trades in the mining set AND at least 30 trades in the holdout set,
   per index. Below 30, `core/backtest/parser.py`'s own `is_overfit_risk`
   already treats a result as statistically unreliable — reusing that
   project-standard threshold rather than inventing a new one.
2. **Mining-set improvement**: the "condition true" subset clears
   `has_positive_edge` (PF>1.0, Sharpe>0.5) on the mining set, AND does so
   by a real margin over the mining set's own unconditional Stratified
   baseline (not just barely above the bar the unfiltered signal already
   clears).
3. **Holdout confirmation**: the SAME condition, evaluated on the untouched
   holdout set, ALSO clears `has_positive_edge` AND improves on the
   holdout's own unconditional baseline, in the same direction. This is
   the step that actually distinguishes a real effect from a mining-set
   fluke — a condition that passes step 2 and fails step 3 is reported as
   **not informative**, full stop, not iterated on.

Every one of the five conditions gets evaluated and reported, whether it
passes or fails — a negative result here is exactly as legitimate an
outcome as candidate 18's own weak years, and is reported with the same
directness.

## What this does NOT produce, even in the best case

A mined condition that clears the bar above becomes a **hypothesis for a
new, separately pre-registered candidate** (an explicit filter added to
candidate 18's signal, run through this project's normal backtest +
adversarial-review pipeline) — not an immediate change to what candidate
18 fires on, and not a capital decision. The orchestrator described in the
user's broader ask (poll conditions, call an agent to fire) is explicitly
deferred until this mining exercise, if it produces anything, has itself
been validated to that standard. No `dry_run: false`, no position sizing,
no live wiring, regardless of what this search finds
(`feedback_confirm_before_scaling_capital`).

## What would make this untrustworthy after the fact

- Adding a sixth (or seventh) condition after seeing how the first five
  perform on the mining set.
- Moving the 80/20 mining/holdout cutoff after seeing a weak holdout
  result for a condition that looked good on the mining set.
- Combining two failing single conditions into an AND rule to manufacture
  a pass — that is fitting two extra degrees of freedom to the same data
  the single-condition test already used, the exact shape of curve-fitting
  this project's own history warns against (`quantos_ml_factor_
  combination_status`, `quantos_s8_3_survivorship_fix_status`).
- Reporting only the conditions that passed and omitting the ones that
  failed the holdout check.
- Pooling NIFTY and BankNifty, or reporting only one index's result.
- Treating exit reason (condition 6) as a firing condition on its own.
- Skipping the holdout check because the mining-set result "looks obviously
  real."
- Treating a pass on this exercise as sufficient to change what candidate
  18 fires on without a fresh, separately pre-registered methodology doc
  and Fable review for the resulting filtered candidate.
