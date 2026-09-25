# Sharpe-Correction Sweep + Generalized Equity-Curve Simulator — Scope & Plan

Written 2026-09-24, before either track starts. Two independent, separately
valuable pieces of follow-up work that came out of the Darvas ATR-stop
investigation, deliberately scoped to avoid becoming an open-ended project.
Likely spans multiple sessions — see "How to resume" at the bottom.

## Why these two, and why now

`core/backtest/parser.py::_sharpe_ratio` was fixed 2026-09-24 (commit
`d8c1293`) to annualize each trade set by its OWN observed frequency
instead of a hardcoded 12-trades/month assumption — found by Fable
reviewing the Darvas ATR-stop backtest, where it mattered (moved Sharpe
0.68→~0.53 before other factors were also corrected). Candidate 18 was
re-checked immediately and got MORE robust (Sharpe 1.03/1.06 → 1.42/1.42)
because it trades far more often than 12/month. Both directions are live
possibilities across the other 20+ closed candidates, and nobody has
looked yet.

Separately, answering "what does ₹50,000 actually grow to" for candidate
18 (or the Darvas ATR-stop candidate, if it ever proceeds past a
discretionary panel) turned out to be impossible from existing pooled
per-trade PF/Sharpe stats — the same trap this project already hit once
with S8-3, which got its own dedicated equity-curve simulator
(`core/rotation/equity_curve.py`). That module is rotation-specific
(weekly rebalance, `rank_universe`-based entries, pluggable exits) and
does NOT generalize to intraday options scalping or independent
overlapping equity positions without real rework — confirmed by reading
its own docstring and entry-point signature before writing this plan.

## Track 1: Sharpe-correction sweep

**Goal**: find out whether any closed candidate's FAIL (or PASS) verdict
would read differently under the corrected annualization. NOT a re-
litigation of any candidate's underlying signal — purely "does the
Sharpe number change enough to matter."

**Two-phase design, cheap-first** (mirrors this project's own gut-check-
before-full-backtest habit):

### Phase 1a: Free triage (no new API calls, no re-runs)

For every script that imports `core.backtest.parser` (confirmed list,
2026-09-24):

```
core/breakout1010/backtest.py        core/orb_scalping/backtest.py
core/orb_scalping/condition_mining.py
scripts/analyze_orb_profit_by_bucket.py   scripts/backtest_breakout1010.py
scripts/backtest_darvas_atr_stop.py       scripts/backtest_darvas_box_width.py
scripts/backtest_darvas_trailing_stop.py  scripts/backtest_dow_theory_trend.py
scripts/backtest_dual_momentum.py         scripts/backtest_goodnight_scalper.py
scripts/backtest_nifty_ema_options.py     scripts/backtest_orb_arm_threshold.py
scripts/backtest_orb_scalping.py          scripts/backtest_pairs_trading.py
scripts/backtest_rs_momentum.py           scripts/check_orb_18b_gate.py
scripts/ingest_s73_backtests.py
```

(re-run this exact grep first — `grep -rl "core\.backtest\.parser" --include=*.py .`
— to catch anything added since; don't trust this list blindly if time
has passed)

For each, read its COMMITTED results doc (not re-run anything) and pull:
original reported Sharpe, trade count, and the backtest's date window.
Compute `implied_trades_per_year = trade_count / years_spanned` and
compare to the old hardcoded 144/yr. Flag a candidate for Phase 1b if
EITHER:
- original Sharpe is within ~0.35 of the 0.5 bar in either direction
  (Fable's own rough 95% CI width at n~65-200 was ~±0.15-0.3 — anything
  closer than that to the line is worth a real check), OR
- implied frequency differs from 144/yr by more than ~30% (small
  frequency differences barely move `sqrt(ratio)`; large ones do).

Known candidates already worth flagging from memory (VERIFY against the
actual committed doc before trusting this — memory is not the source of
truth):
- **Strategy 1 (regime-filtered dual momentum, `backtest_dual_momentum.py`)**:
  "fails its own equity-curve Sharpe bar (0.45<0.5)" — 0.05 away from the
  line, the single highest-priority check in this whole sweep.
- Pairs trading v1/v2 (`backtest_pairs_trading.py` + its v2 counterpart,
  confirm exact script name — may be `backtest_pairs_trading_v2.py`):
  v2's own numbers were "PF 0.94->1.04, Sharpe -0.17->0.14" after bug
  fixes — still well below 0.5, lower priority, but check trade
  frequency since pairs strategies can trade at unusual cadences.
- Candidate 18b once it matures (see Track 1 note below) will already
  use the corrected formula automatically — no action needed, just don't
  forget it's a live candidate, not closed.
- Everything with a Sharpe already far from 0.5 in the SAME direction the
  correction would push it (e.g., a FAIL at Sharpe -1.5 whose frequency
  correction would only push it MORE negative) can be skipped without a
  re-run — the arithmetic alone settles it.

### Phase 1b: Targeted re-runs (only for flagged candidates)

For each candidate flagged in 1a, actually re-run its backtest script
(most will need a fresh Fyers pull — check for a resumable local cache
first, per the lesson learned this session: NONE of the Darvas/ORB
scripts had one for raw candle data, only trade-level output, so budget
for real fetch time). Report old vs. corrected Sharpe side by side,
same pattern as `docs/ORB_SCALPING_RESULTS.md`'s 2026-09-24 addendum —
append a dated correction note, do NOT edit the original verdict line
if that candidate's doc has a "never changes retroactively" clause.

**Explicit non-goal**: this is not a chance to re-open a candidate's
core methodology, mine new conditions, or adjust its bucket/threshold
choices. If a corrected Sharpe flips a verdict, report it plainly and
stop — a flipped verdict from a metrics fix is its own real finding
worth pausing on (like the ATR-stop chain did with Fable), not a
license to start optimizing.

## Track 2: Generalized equity-curve simulator

**Goal**: answer "what does ₹X real capital actually become" for a
strategy, properly — real position sizing against available capital,
real compounding, real mark-to-market, real drawdown bounded to [0,100]%.
Scoped to exactly two target strategies for now, not "generalize to
everything":

1. **Candidate 18 (ORB options scalping)** — the one that triggered the
   original question. Needs a genuinely different engine than S8-3's:
   premium-based position sizing (lot size × entry premium, NOT a share
   count), margin/capital-sufficiency checks (`core/orb_scalping/backtest.py`'s
   `NIFTY_LOT_SIZE=65` / `BANKNIFTY_LOT_SIZE=30` and real premium levels
   determine whether ₹50,000 can even afford a given trade), intraday
   same-day entry/exit (not weekly rebalance), and likely MULTIPLE
   concurrent or same-day trades competing for the same capital pool.
2. **Darvas ATR-stop candidate (Bucket B, if/when it proceeds past a
   discretionary panel)** — independent, overlapping equity positions
   triggered by individual breakout signals, not a fixed-top-N rotation.
   Needs: a capital-allocation policy for "how much of the account goes
   into any one new signal" (fixed %, volatility-scaled, or a fixed slot
   count — this is a real design decision, not just plumbing), and
   correct handling of overlapping positions competing for the same cash
   pool (unlike S8-3's fixed top-20 slots).

**Design approach**: build one shared, asset-agnostic core — an
`Account`-style object tracking cash balance, open positions (arbitrary
instrument type), realized/unrealized P&L, and a daily mark-to-market
loop producing the equity curve — then a thin, strategy-specific adapter
per candidate that decides position sizing and reads that strategy's own
existing signal/trade generation code (`core/orb_scalping/backtest.py`
for 18, `scripts/backtest_darvas_atr_stop.py`'s trade list for the Darvas
candidate) rather than re-deriving signals. Do NOT try to retrofit
`core/rotation/equity_curve.py` itself — confirmed unsuitable, it's built
around `rank_universe`/weekly-rebalance semantics that don't fit either
target. A brand-new module (e.g. `core/backtest/equity_curve.py`, generic)
is cleaner than bending the rotation-specific one.

**Suggested phase order**:
1. ~~Design the shared `Account` core in isolation, with unit tests, no
   strategy-specific logic yet~~ **DONE 2026-09-24** — `core/backtest/equity_curve.py`
   (commit `95408e7`), 21 unit tests in `tests/unit/test_generic_equity_curve.py`.
2. ~~Wire candidate 18 in first~~ **DONE 2026-09-24** —
   `scripts/simulate_orb_scalping_equity_curve.py` (commit `ad1093a`,
   adapter + 7 unit tests) plus a live run against real Fyers data,
   written to `docs/ORB_SCALPING_EQUITY_CURVE_RESULTS.md`. **Answer:
   ₹50,000 is NOT viable — it's wiped to ~₹2,000 (97.7% max DD), while
   ₹55,000 (just 10% more) ends near ₹513,000.** The failure is a cliff,
   not a slope: single-lot premium cost runs ₹7k-25k/trade, and once an
   early drawdown pushes cash below that floor the account is locked out
   of the very trades that would let it recover. See that doc's
   "Interpretation" section for the full mechanism and caveats (in
   particular: exact rupee figures aren't reproducible bit-for-bit on a
   later re-run, since this pulled live intraday data mid-session — the
   cliff's existence and rough location are the finding, not the precise
   numbers). **Follow-up (same day, user asked about ₹500,000 as a
   higher-capital option)**: re-ran at ₹500k — it clears the cliff safely
   (identical 2,335/2,335 trades taken, same behavior as ₹60k+), but earns
   the exact same ~₹523,389 absolute profit as every tier from ₹60k up,
   because sizing is fixed at 1 lot/trade regardless of capital. CAGR
   actually gets WORSE at higher capital (100k: 41.1% → 500k: 14.4%) since
   the same fixed profit is diluted over a bigger idle base. ₹500k buys
   safety, not more return, under the current sizing policy — scaling lot
   count with capital would be a new, not-yet-built design decision.
3. ~~Wire the Darvas ATR-stop candidate in second~~ **DONE 2026-09-25** --
   `scripts/simulate_darvas_atr_stop_equity_curve.py` (14 unit tests),
   run against the already-committed local cache (no new backtest, no
   Fyers calls). Results in `docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md`:
   unlike candidate 18, NO wipeout cliff (worst max DD ~50%, not ~98%) --
   equities size down smoothly instead of hitting an all-or-nothing lot
   floor. Instead the problem is CAPACITY: the backtest's own fixed-
   Rs100k/trade convention loses money below Rs100k and never fully funds
   even at Rs500k (43% of signals still skipped) because many overlapping
   breakout signals compete for a fixed target each. Quarter Kelly
   (~11.5% of equity/trade) is again the standout on the full (larger,
   more trustworthy) window -- positive at every capital tier, lowest
   drawdown and Ulcer Index of any policy tested. The Holdout-only table
   looks spectacular (Sharpe >2, CAGR up to 78%) but is flagged as
   untrustworthy in the doc itself -- only 67 signals, as few as ~20-45
   actually executed per cell, the classic small-sample lucky-regime
   shape. Also surfaced an unresolved methodological gap: the Kelly
   fraction assumes one trade at a time, but Darvas holds many
   concurrent positions -- a portfolio-level Kelly formulation is a real
   follow-up, not built here.

**Follow-up (2026-09-25, user asked to build the portfolio Kelly
formulation) -- DONE**: `core/backtest/equity_curve.py::optimal_fraction_by_growth`
(commit `1cea990`) finds the fraction that maximizes REALIZED portfolio
log-growth by directly simulating the real overlapping trade history
(concurrency, correlation, and the cash ceiling all correct by
construction, not analytically approximated) -- rejected a naive
"divide single-trade Kelly by N concurrent positions" heuristic first
since it can't account for correlation or the fact Account's own cash
constraint already caps aggregate exposure. Wired into
`scripts/simulate_darvas_atr_stop_equity_curve.py` (commit `d35416f`) as
a 5th sizing policy, grid-searched on the mining window and validated on
holdout same as the others. Result: **f=0.09 (9% of equity/trade) beats
every other policy including Quarter Kelly on every risk-adjusted metric
on the full window** (best Sharpe/Sortino/Calmar, lowest Ulcer Index,
lowest max drawdown) -- confirms the concurrency gap was real and that a
properly-derived fraction measurably beats an ad hoc round-number guess,
even though the ad hoc guess (Quarter Kelly, 11.48%) happened to be in
the right ballpark. Updated recommendation:
`docs/DARVAS_ATR_STOP_EQUITY_CURVE_RESULTS.md`.
4. Stop there unless a specific new candidate needs it — resist
   generalizing further without a concrete question driving it, same
   discipline as every other piece of infra this project has built.

**Extension (same day, user asked for the "optimum capital allocation",
not just a fixed-lot survival check) — DONE 2026-09-24**:
`scripts/simulate_orb_scalping_capital_allocation.py` (commit `0a79fb2`,
13 unit tests) adds equity-proportional position sizing (lots scale with
current equity, not fixed at 1) and a Kelly-fraction-based, mining/holdout-
validated way to choose the sizing rule — deliberately NOT a sweep for
whichever fraction backtested best (that would fit the one historical
path this project has). Results in
`docs/ORB_SCALPING_CAPITAL_ALLOCATION_RESULTS.md`:

- Mining-derived Kelly fraction: 31% of equity/trade (full), 15.5% (half),
  7.75% (quarter).
- On the untouched HOLDOUT window: Quarter Kelly is the most consistently
  reasonable policy above ₹100,000 (Sharpe up to 1.25, max DD 16-26%).
  Full Kelly has a positive Sharpe but 74-93% drawdowns even out of
  sample — the classic reason nobody trades full Kelly in practice.
  ₹50,000 has no good option among any of the four policies tested
  (either too small to execute the fractional policies at all, or stuck
  with fixed-lot's already-documented cliff) — this independently
  reconfirms ₹50,000 is undersized for this strategy.
- The full-window numbers (some in the hundreds of millions of % return)
  are explicitly flagged as an in-sample compounding artifact, NOT a
  forecast — included only to show the mechanics, with a prominent
  warning in the doc against reading them at face value.
- Practical recommendation as currently evidenced: ~8-16% of equity per
  trade (quarter-to-half Kelly), ₹100,000+ starting capital, ₹500,000
  showing the cleanest risk-adjusted profile of everything tested.

## Known operational lessons to carry forward (both tracks)

- **Background long-running Fyers pulls can silently die on machine
  sleep, and the log can look "frozen" for hours while the process is
  actually fine (stdout buffering under `tee`) or actually dead — the
  log alone can't tell you which.** Trust the resumable JSON cache's
  file mtime and growing size, not the log tail, not `tasklist` (it gave
  a false "not running" reading at least once this session while the
  process was in fact still alive and later completed correctly).
- **Never relaunch a resumable script against an existing cache without
  confirming the prior process actually exited.** Each process only
  loads the cache once at startup; if two run concurrently, the one with
  the stale in-memory view can overwrite the other's newer entries. This
  cost wasted compute once this session, and was only harmless because
  the underlying computation was fully deterministic — don't count on
  that being true of new code.
- **Check the Fyers token before starting a fresh fetch each session**
  (`python agent/auth/fyers_auth.py`, interactive, needs the user's own
  terminal — never run it via a background tool).
- **A "never changes retroactively" verdict line means append a dated
  correction note, never edit the line in place** — even for a
  legitimate metrics-methodology fix, not just a re-litigated result.

## Track 1 status: Phase 1a + 1b DONE 2026-09-24 — no doc-level verdict changes, one flagged fragile flip

**Key methodological finding that collapsed Phase 1a/1b into one pass**: the
fix is an exact multiplicative rescale, not a re-run-dependent one.
`_sharpe_ratio` is `mean(returns)/std(returns) * sqrt(periods_per_year)`, and
the fix only changed `periods_per_year` from a hardcoded 144 to each trade
set's own `len(trades) / (days_span/365.25)`. Mean/std of per-trade returns
are untouched. So for any already-committed result:

```
corrected_sharpe = old_sharpe * sqrt(actual_trades_per_year / 144)
```

This can be computed from each doc's own reported trade count + date window
— **no re-run, no Fyers pull, no API budget spent**. Verified against
`core/backtest/parser.py` directly before trusting it.

**Top-priority check (Strategy 1 dual-momentum) — resolved as not
applicable.** The "0.45 < 0.5" number this plan flagged as highest priority
(`docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md`, Coverage-clean sub-period) is
the **"Sharpe (equity-curve daily returns)"** line — computed via
`core/rotation/equity_curve.py`'s daily-returns `sqrt(252)` annualization,
a completely different code path from `core.backtest.parser._sharpe_ratio`.
The September fix never touched it; it was never affected. The line this
bug *does* touch — the doc's own stated verdict basis, "pooled-trade
`has_positive_edge`" Sharpe — was already a comfortable PASS (0.51 for
Coverage-clean) and gets more comfortable corrected (0.700). No change
either way for this candidate.

**No doc-level headline verdict flips anywhere.** Every closed candidate's
overall PASS/FAIL stands: candidates 14, 15, 17(v1), 18, 20, S7-3, Darvas
box-width, Darvas trailing-stop. In every gating row, either PF was already
<1.0 (PF is untouched by this bug) or the Sharpe margin was too large to
cross 0.5.

**One real but fragile non-headline flip found**: Pairs trading v2
(candidate 17) pooled Sharpe -0.17→~~0.14~~ → **~0.556** under the
correction (PF 1.04, so this technically crosses FAIL→PASS on the
mechanical bar). Caveat: the window used (2024-07-01→2026-07-01) is
approximated from fold-boundary dates, not the trade set's literal
first-entry/last-exit dates (doc doesn't report those directly) — if the
true span is shorter, corrected Sharpe would be *higher* still (reinforces
the flip, doesn't reverse it), but treat 0.556 as an estimate. Candidate 17
was closed 2026-07-27 on a substantive finding independent of this number
("fold collapse is real regime shift" — see memory
`quantos_pairs_trading_v2_status`), so this is reported per the plan's
"report plainly and stop" rule, not treated as license to reopen the
methodology. **Open follow-up if it ever matters**: get the exact
first-entry/last-exit dates from a cached local run (no API call expected —
pairs trading uses NSE bhavcopy, not live Fyers pulls) to firm up the 0.556
estimate.

**Handful of non-gating sub-row flips** (none change any doc's official
verdict — all are supplementary/Clean-only or margin-over-baseline splits
that were never the gating row): Darvas trailing-stop's ≤35% Holdout-Clean
(0.30→0.595, FAIL→PASS) and 50-100% Holdout-Clean (0.70→0.470, PASS→FAIL);
ORB arm-threshold's BankNifty 0.25x/0.50x Mining rows (0.49→0.770,
0.50→0.785, both FAIL→PASS on the row-level bar, but Holdout still fails
PF so "not adoptable" stands); ORB condition-mining's BankNifty
monday_or_friday Mining (0.60→0.490, PASS→FAIL, doesn't change "Informative:
no" — it already failed on margin-over-baseline).

**Cannot be corrected**: `docs/S7_3_BACKTEST_RESULTS.md` — no date window
recoverable anywhere in the doc, the sample doc, or the repo (source is
per-symbol TradingView CSV exports in `data/s73_backtests/`, not committed).
Doesn't matter for the verdict: the realistic-cost row's PF (0.75) already
fails on its own regardless of Sharpe.

**Confirmed out of scope entirely** (don't touch `core.backtest.parser`,
or report no Sharpe at all): `MOMENTUM_TURNOVER_ABLATION_RESULTS.md` +
its diagnostics doc (daily equity-curve or unannualized bespoke calc),
`CANDLE_CONFIRM_MOMENTUM_GUTCHECK_RESULTS.md` and
`DARVAS_BOX_WIDTH_SENSITIVITY_RESULTS.md` (no Sharpe/PF reported at all).

Full per-row extraction (every split, every doc) done by a subagent and
verified spot-check by the parent session — not re-transcribed here to
keep this doc a living summary, not a data dump; re-derivable from the
formula above plus each doc's own committed trade counts/windows if ever
needed again.

**Track 1 is effectively closed** unless the user wants candidate 17's
window firmed up. Not spending further API budget on it without asking.

## How to resume this in a later session

Check git log for commits touching `docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md`
and anything under `docs/*_SHARPE_CORRECTION*` or a new
`core/backtest/equity_curve.py` to see how far either track got. This
document's own checklists (Phase 1a candidate list, Track 2's phase
order) are the state to pick back up from — update them in place as
work completes rather than creating a parallel status doc, since keeping
one live planning document per track (updated, not replaced) is easier
to resume from cold than reconstructing state from chat history or
memory alone.
