# ORB Options Scalping — Arm-Threshold Methodology, Pre-Committed 2026-09-21 Before Any Result Exists

## Why this exists

`docs/ORB_ARM_GIVEBACK_ANALYSIS.md` (measurement only, no parameter
touched) found that candidate 18's trailing stop only arms after price
moves a FULL opening-range width in its favor — and that bar is high
enough that **29.1% of NIFTY trades and 35.4% of BankNifty trades never
clear it**, riding un-protected to the 15:20 IST flatten. In that bucket,
NIFTY keeps just 6% of its aggregate peak profit and BankNifty keeps 0%;
roughly half of those trades close net NEGATIVE despite having been in
profit intraday. Trades that DO arm keep ~73% of their peak in both
indices — the mechanism works, the trigger is just too far away for a
third of all trades to ever reach it. Prompted directly by a real live
paper trade (BankNifty, 2026-09-21, +143pt intraday rally, never armed,
gave it all back).

**This is different from every prior post-hoc pass on this candidate.**
Every cost-model variant (Clean → Stressed → Harsh → Real-spread →
Sampled-spread → Stratified) left `core/orb_scalping/signal.py` completely
untouched — only how a trade's P&L was COSTED changed. The condition-
mining methodology (`docs/ORB_CONDITION_MINING_METHODOLOGY.md`) layers a
FILTER on top of an unchanged signal. **This document proposes changing
the signal itself** — the trailing-stop arm trigger, a real trading rule —
for the first time in this candidate's entire history. That is a bigger
step and gets the same discipline as everything else here, applied with
extra care because of it: a fixed candidate grid pre-registered before any
result exists, a mining/holdout split, and an independent review before
anything currently running (`quantos-orb-scalping-live.timer`, dry_run
paper trading) is touched.

## Scope

**Candidate 18 (ORB) only, and ONLY the arm-threshold constant.** Every
other rule stays exactly as `docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md`
locked it: opening-range definition (first three 5-minute candles),
initial stop (opposite side of the range), the trailing-stop RATCHET
formula and its 3-candle lookback once armed (`TRAIL_LOOKBACK_CANDLES`,
unchanged), the 25%-premium secondary stop, the DTE floor, premium
reconstruction, and the Stratified (locked-final) cost model. Only
`core/orb_scalping/signal.py::trail_arm_level`'s implicit `1.0 ×
range_width` multiplier is varied. One variable at a time — same
principle the condition-mining doc uses for its own five conditions.

**Both indices, reported independently, never pooled**, and **the SAME
candidate multiplier is evaluated identically on both indices** — NIFTY
and BankNifty are not allowed to each pick their own best-looking value.
Letting them diverge independently would double the number of chances to
find a value that merely fits one index's own noise, the same
extra-degree-of-freedom risk the condition-mining doc's ban on combining
two failing conditions into an AND already warns against in this project.

## Candidate grid (pinned before any code runs)

`{0.25, 0.5, 0.75, 1.0}` × range-width. Four points, not a continuous
sweep or an optimizer — a finer search multiplies the number of chances to
land on a value that fits this specific historical sample's noise rather
than a real effect, the same multiple-comparisons risk
`docs/ORB_CONDITION_MINING_METHODOLOGY.md` limits by testing only two
sub-values per condition. `1.0` is the existing, already-tested baseline
(`docs/ORB_SCALPING_RESULTS.md`'s Stratified numbers) and is re-run here
only so every point in the grid is measured the same way, on the same
mining/holdout split, in the same pass — not read from the old report,
which used the full sample undivided.

`trail_arm_level(direction, entry_price, range_width, multiplier=1.0)`
gains a `multiplier` parameter (default `1.0`, so every existing caller —
the live script, the stop-out probe, the original backtest — is
byte-for-byte unchanged unless it explicitly passes a different value).
No other function in `signal.py` changes.

## Mining / holdout split

**Identical rule to `docs/ORB_CONDITION_MINING_METHODOLOGY.md`**, reused
rather than reinvented: time-based, not random (a random split lets
regime state leak across the boundary). Cutoff: the most recent 20% of
each index's trade history by calendar date, computed once the real data
is fetched. Mining set = earliest 80%; holdout = most recent 20%.
Reported separately per index — NIFTY and BankNifty do not share a cutoff
date.

## Pass bar for a candidate multiplier

A multiplier from the grid (`1.0` excluded — it is the baseline being
compared against, not a candidate for adoption) is only reported as
**adoptable** if ALL of the following hold, checked in this order, ON
BOTH INDICES:

1. **Minimum sample size**: at least 30 trades in the mining set AND at
   least 30 in the holdout set. This grid only changes WHEN a trade's
   trailing stop arms, never whether a trade happens at all, so the trade
   COUNT itself will not move between multipliers — this is really a
   floor on the underlying sample, already comfortably cleared by both
   indices' full history (1049 NIFTY / 1280 BankNifty trades total).
2. **Mining-set improvement, by a material margin, not just technically
   ahead**: the multiplier's Stratified metrics on the mining set clear
   `has_positive_edge` (PF>1.0, Sharpe>0.5) AND beat the `1.0×` baseline
   ON THE SAME MINING SET by at least **+0.10 Sharpe AND a positive PF
   delta** — both metrics, not one moving favorably while the other
   doesn't. A one-hundredth-of-a-point edge is exactly the kind of
   "barely ahead" result this project's history (the Sampled-spread
   reversal, the momentum-turnover ablation) has repeatedly shown is not
   trustworthy without more.
3. **Holdout confirmation**: the SAME multiplier, evaluated on the
   untouched holdout set, ALSO clears `has_positive_edge` AND beats the
   holdout's own `1.0×` baseline in the same direction (Sharpe and PF
   both, same margin rule as step 2 — the holdout sample is smaller, so
   the same absolute bar is deliberately not relaxed for it). A
   multiplier that passes step 2 and fails step 3 is reported as **not
   adoptable**, full stop, not iterated on or re-tested with a nearby
   value.

Every one of the four grid points gets evaluated and reported on both
mining and holdout, whether it passes or fails.

**If more than one multiplier clears both indices' mining and holdout
bars**, the one closest to the current `1.0×` (i.e. the smallest change)
is preferred over cherry-picking whichever looks best — a deliberate
parsimony rule, fixed here before any result exists, so a good-looking
number two grid points away cannot later be argued for over a more
conservative one that also passed.

## What this does NOT produce, even in the best case

A multiplier that clears every bar above becomes a **proposed change to
candidate 18's live paper-trading script**
(`scripts/run_orb_scalping_live.py`, currently dry_run on the VM) — not an
automatic flip. Same standing rule as every other decision in this
project: independent (Fable) review of the actual grid results before
treating a pass as real, then the user's own explicit go-ahead before the
constant changes anywhere outside a backtest
(`feedback_confirm_before_scaling_capital` — this gates code changes to
the paper-trading script too, not just capital, given it changes what a
running system does). No change to `dry_run`/`enabled` in
`agent/config.yaml` is implied by this document regardless of outcome.

## What would make this untrustworthy after the fact

- Adding a fifth grid point, or narrowing the grid around whichever point
  looked best, after seeing mining-set results.
- Moving the 80/20 mining/holdout cutoff after seeing a weak holdout
  result for a multiplier that looked good on the mining set.
- Letting NIFTY and BankNifty each adopt a different multiplier.
- Lowering the +0.10 Sharpe / positive-PF materiality bar because nothing
  in the grid clears it at the original bar.
- Reporting only the multiplier that passed and omitting the other three.
- Pooling NIFTY and BankNifty, or reporting only one index's result.
- Treating a mining+holdout pass as sufficient to flip `dry_run` or
  `enabled` on the live script without a fresh Fable review of the actual
  grid results and the user's own explicit go-ahead.
- Re-deriving `range_width` or the trailing-lookback formula "while we're
  in there" — this document is scoped to the arm multiplier alone; any
  other signal.py change is a separate, separately pre-registered
  proposal.
