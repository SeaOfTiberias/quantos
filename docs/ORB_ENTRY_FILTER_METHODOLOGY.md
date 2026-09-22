# Candidate 18b — ORB Entry-Filter Methodology, Pre-Committed 2026-09-22 Before Any New Result Exists

Named "18b" rather than the next open number (21) at the user's explicit
request 2026-09-22: this is a distinct strategy in its own right — its
own live process, its own position store, its own dry-run log, its own
prospective verdict — not a parameter tweak inside candidate 18. The "b"
records that it's a direct, disclosed descendant of 18 (same signal,
same options mechanics, an entry gate layered on top) rather than an
unrelated idea starting fresh, the way 19/20 did.

## Why this exists

Three findings, each already committed with real numbers, motivate this:

1. `docs/ORB_PROFIT_BY_BUCKET_ANALYSIS.md`: candidate 18's entire net profit
   comes from the ~third of trades that arm the trailing stop (NIFTY +345%
   of total net profit, BankNifty +410%) — the other two-thirds are a real
   net LOSER on their own (NIFTY -811,320 PF 0.16, BankNifty -1,319,939 PF
   0.18), not merely a diluter.
2. `docs/ORB_ARM_THRESHOLD_RESULTS.md`: trying to fix this by loosening the
   arm trigger makes things WORSE on every metric — the trigger is doing
   real work as a classifier, not an arbitrary knob.
3. `docs/ORB_CONDITION_MINING_RESULTS.md`, run TWICE three weeks apart
   (2026-09-03 and 2026-09-21, each time with fresh trades folded in) with
   the SAME result both times: **NIFTY's `monday_or_friday` condition and
   BankNifty's `big_gap` condition each clear the pre-registered mining +
   holdout bar, replicated, not a one-shot fluke.**

The natural next question: if the losing majority can be filtered out
BEFORE entry using information already known that morning, does actually
gating candidate 18's entries on these two conditions produce a real
improvement? This document pre-registers exactly that, before any new
result exists.

## Scope

**Candidate 18 only, and ONLY the two already-mined-and-replicated
conditions — applied exactly as mined, one per index, no new search:**

- **NIFTY**: only take an entry if the entry date is a Monday or a Friday.
  Every other rule (opening range, initial stop, trailing arm at 1x
  range-width, ratchet, DTE floor, 25% premium stop) stays exactly as
  `docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md` locked it.
- **BankNifty**: only take an entry if `|gap_pct| > 0.3` (today's first
  5-minute candle's open vs. the prior trading day's daily close),
  `core/orb_scalping/conditions.py::gap_pct`'s existing definition,
  unmodified. Same "everything else frozen" rule.

**No cross-application.** NIFTY does NOT get the gap filter and BankNifty
does NOT get the day-of-week filter — `docs/ORB_CONDITION_MINING_RESULTS.md`
already tested both pairings and the other four combinations (stage2,
wide_range, narrow_range, and each condition on the OTHER index) did not
clear the bar. Applying an untested pairing now would be a new,
un-pre-registered hypothesis wearing this document's already-earned
credibility — explicitly not done here.

**No new filter, no threshold change to `0.3` or to "Monday/Friday", no
combining the two conditions with anything else.** Those exact values were
fixed in `docs/ORB_CONDITION_MINING_METHODOLOGY.md` before any mining
result existed; re-tuning them now, after seeing which values happened to
mine well, would be curve-fitting through the back door.

## The "same data" problem — addressed directly, not glossed over

**A fresh backtest of the filtered strategy over the same 2021/2022–2026
historical window is NOT an independent test.** The condition-mining
exercise's own `mining_true_metrics` and `holdout_true_metrics` already
report exactly what this filtered strategy would have shown on that data —
running it again and calling it a new confirmation would be circular, the
same shape of error `docs/VRP_METHODOLOGY.md` already bans in writing
("reporting a regime-filtered ... subset as the headline instead of the
full unfiltered sample"). This document does NOT propose a third backtest
run over the same window as if it were new evidence.

Two things happen instead, and only these two:

### 1. A full-sample descriptive number (not a validation step)

Combine each condition's mining-set and holdout-set trades (all of it —
the full 2021/2022–2026 history where the condition holds) into one
metric per index, purely so there is a single "what would this have
looked like" figure alongside the mining/holdout split already reported.
**Explicitly labeled as descriptive, not confirmatory** — it uses data the
mining process has already seen in full.

### 2. Prospective validation — the step that actually counts

The filter is wired into `scripts/run_orb_scalping_live.py` behind a new,
OFF-by-default flag (`agent/config.yaml`'s `orb_scalping.entry_filter_enabled`,
default `false` — every existing dry_run/enabled behavior is otherwise
unaffected). Once turned on (still `dry_run: true`, still paper, no
capital decision implied by turning it on), it accumulates GENUINELY NEW
trades — ones neither 2026-09-03 nor 2026-09-21's mining runs could have
seen — and only those count toward a verdict. This is the same discipline
already used twice in this project: the momentum-turnover candidate's
walk-forward (`quantos_momentum_turnover_walkforward_status`, deployed
live rather than re-backtested on the same window) and the stop-out
spread probe's own pre-registered N/time gate.

**Pre-registered stopping rule, fixed here before any new trade exists:**

- **N ≥ 20 new filtered entries per index, independent** (NIFTY and
  BankNifty never pooled, same as every other gate in this project).
- **AND ≥ 8 calendar weeks elapsed since the flag is turned on** — double
  the stop-out probe's 4-week gate, because this filter cuts trade
  frequency roughly in half per index (NIFTY trades ~2 of 5 weekdays;
  BankNifty's `big_gap` fired on roughly half of all historical trading
  days, 641 of 1280), so the same N takes proportionally longer to
  accumulate.
- **Both conditions required, neither alone** — blocks stopping early on a
  lucky burst, and blocks quietly declaring victory once enough calendar
  time has passed regardless of how few trades actually fired.
- Verdict method once both clear: compute Stratified PF/Sharpe on the
  NEW trades only (not blended with the historical mining/holdout sample)
  and compare against candidate 18's own unfiltered live performance over
  the same forward window — same index, same period, filter on vs. off,
  the only way to isolate the filter's own effect from whatever the
  market did generically over that window.

## Addendum, pre-registered 2026-09-22 (same day as enabling, before any
## 18b trade has closed): a ₹50,000 base-capital equity narrative, IN
## ADDITION to the PF/Sharpe check above

User's explicit ask: track what a ₹50,000 starting account would have
grown to by 2026-11-17 — a rupee-terms complement to the statistical
pass/fail bar, not a replacement for it. Fixed here, before any 18b trade
exists to peek at:

- **One combined ₹50,000 account for Candidate 18b as a whole** — NOT
  ₹50,000 per index. A real trader running 18b would fund it from one
  pot covering both the NIFTY and BankNifty legs, so the equity curve
  pools both indices' closed trades by exit order into a single running
  total. This is a deliberate departure from the "never pool NIFTY/
  BankNifty" rule used everywhere else in this document — that rule
  governs the STATISTICAL verdict (is there an edge, which must stay
  per-index to mean anything), not a capital-growth narrative, which is
  inherently about one account. The per-index PF/Sharpe pass/fail bar
  above is completely unaffected by this and stays per-index.
- **Reported strictly as of 2026-11-17** — the same date the ≥8-week
  half of the PF/Sharpe gate clears (2026-09-22 + 8 weeks = 2026-11-17,
  exactly). Unlike the PF/Sharpe verdict, this figure is NOT additionally
  gated on N≥20 per index — it is an honest answer to "how much would
  ₹50,000 have become by this date," not a significance test, and stays
  meaningful (with an honest small-sample caveat) even if one leg fired
  fewer than 20 times by then.
- **Realized P&L only**, computed from `core/orb_scalping/dry_run_log.py`'s
  closed-trade records (both variants' logs already exist for exactly
  this purpose): `(exit_premium − entry_premium) × quantity` per closed
  trade, Stressed-cost-adjusted (`core/orb_scalping/costs.py`'s
  `stressed_trade_cost` — chosen over the full Stratified expiry-day
  stratification for simplicity here; the PF/Sharpe verdict above still
  uses Stratified). A trade whose `exit_premium` is `None` (the dry-run
  log's own live-quote-fetch failure case) is excluded from the equity
  sum and its count reported separately — never treated as a zero-P&L
  trade.
- Equity path: ₹50,000 plus the running cumulative Stressed-cost-adjusted
  P&L, ordered by exit timestamp across both indices. Report the final
  value, the total return %, and each leg's own contribution (NIFTY vs.
  BankNifty P&L, disclosed even though the account itself is pooled) so
  a reader can see which leg drove the result.
- **No peeking before 2026-11-17** — same discipline as the PF/Sharpe
  gate: an interim check may confirm the dry-run log is accumulating
  correctly (row count, no malformed lines), but must not report the
  running rupee total or a partial return % before the date. Reporting a
  running total early and letting it influence whether the gate date gets
  moved would be exactly the "stop when favorable" pattern this
  project's whole post-hoc-analysis discipline exists to prevent.
- This is a DESCRIPTIVE figure, not a second pass/fail bar. It does not
  override, and is not overridden by, the per-index PF/Sharpe verdict —
  both are reported side by side. A strong equity number with a failing
  PF/Sharpe (or vice versa) is a real, reportable outcome, not a
  contradiction to resolve by picking whichever looks better.

## What this does NOT produce, even in the best case

Turning `entry_filter_enabled: true` on is a **paper-trading configuration
change**, not a capital decision, and does not by itself imply anything
about `dry_run`. A prospective pass (N≥20, ≥8 weeks, filtered forward
performance clears the bar and beats the unfiltered live baseline over the
same window) becomes grounds for a FRESH conversation about `dry_run:false`
— gated, as always, by `feedback_confirm_before_scaling_capital` and the
user's own explicit go-ahead, not implied by this document or by a passing
prospective result.

## What would make this untrustworthy after the fact

- Treating the full-sample descriptive number (section 1) as if it were a
  fresh validation, or citing it as the reason to skip prospective
  accumulation.
- Applying `monday_or_friday` to BankNifty or `big_gap` to NIFTY — both
  already tested and already failed in `docs/ORB_CONDITION_MINING_RESULTS.md`.
- Re-tuning the `0.3` gap threshold or widening "Monday or Friday" to a
  third day after seeing early prospective results look weak.
- Shortening the N≥20 / ≥8-week gate because the filtered trade rate is
  slower than hoped and the wait feels long.
- Turning `dry_run: false` on the strength of the prospective pass alone,
  without a fresh, explicit go-ahead from the user at that time.
- Pooling NIFTY and BankNifty's prospective results, or reporting only
  one index's.
