---
tags:
  - strategy/momentum
  - trading/stage-analysis
  - screening/trend-template
  - algo/feature-extraction
quantos:
  id: weinstein_stage2
  label: Weinstein
  timeframe: daily
---

# Stan Weinstein's Stage Analysis

*Secrets for Profiting in Bull and Bear Markets* (1988). Weinstein's claim is
that every stock cycles through four stages, and that essentially all worthwhile
long exposure lives in one of them. The instrument is the **30-week moving
average** and its slope.

## 🔄 The four stages

```
                                    ╭──╮      Stage 3
                              ╭─╮ ╭─╯  ╰─╮   (Topping)
                          ╭───╯ ╰─╯      ╰╮
              Stage 2  ╭──╯                ╰──╮
            (Advance) ╭╯                       ╰─╮  Stage 4
                    ╭─╯                          ╰──╮ (Decline)
    ╮             ╭─╯                                ╰───
     ╰──╮  ╭───╮╭─╯   ◄── 30-week MA turns up = the Stage 1→2 line
        ╰──╯   ╰╯
      Stage 1 (Basing)
```

| Stage | Name | 30-week MA | Price vs MA | What to do |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Basing | Flat | Oscillating around it | Watch. No position. |
| **2** | Advancing | **Rising** | **Above** | The only buy zone. |
| **3** | Topping | Flattening | Chopping across | Tighten stops, take profit. |
| **4** | Declining | Falling | Below | Out. Short candidates only. |

The single most important line in the method: **never buy a stock below a
flat-or-falling 30-week moving average**, regardless of how good the story is.

---

## 📋 Stage 2 entry conditions

1. Price is trading **above** the 30-week MA.
2. The 30-week MA has **flattened out and turned up**.
3. Price has broken out **above the Stage 1 base's resistance ceiling**.
4. The breakout came on a **meaningful volume expansion** — Weinstein wants at
   least double the recent average on the breakout week, and volume to stay
   elevated on the advance that follows.
5. **Relative strength versus the market index is positive** and ideally has
   itself broken out.

---

## ⚙️ Machine-checkable rules

```quantos-rules
# 1. Above the 30-week average. 30 weeks x 5 sessions = 150 trading days.
close > sma(150)

# 2. That average is rising. Compared against itself 25 sessions (~5 weeks)
#    ago, which is long enough that a single volatile fortnight cannot fake
#    a turn.
sma(150) > sma(150)[25]

# 3. Broken out of the base. Approximated as "today's close is above the
#    highest high of the preceding six months, measured as of 5 sessions ago"
#    -- the lag stops the breakout bar itself from setting the ceiling it is
#    supposed to be clearing. See the caveat on base detection below.
close > high(126)[5]

# 4. Volume is confirming the advance. Two ways that shows up, either of
#    which counts:
#      a) today IS the breakout bar — 2x the 50-day average, Weinstein's
#         literal condition; or
#      b) the breakout already happened and volume has stayed up — the last
#         ~5 weeks averaging at least 10% above the last ~10 weeks, which is
#         the signature of a base being left on real participation.
#    Until 2026-08-14 this was arm (a) alone, which is a same-session test
#    and therefore false on every day except one. See the caveat below.
volume > volume_sma(50) * 2.0 or volume_sma(25) > volume_sma(50) * 1.1

# 5. Relative strength positive. Requires an injected cross-sectional rating;
#    without one this is UNEVALUABLE and the audit blocks.
rs_rating >= 60
```

### Caveats that matter when reading a verdict

- **Daily bars stand in for weekly.** Weinstein works on a weekly chart with a
  30-week MA. QuantOS holds daily bars, so `sma(150)` is the substitution.
  These are close but not identical: a daily 150-SMA reacts to intra-week
  noise a weekly 30-SMA smooths away. Expect this note to flip state slightly
  earlier and slightly more often than Weinstein's own charts would.
- **Rule 3 is an approximation, not base detection.** Weinstein draws the
  Stage 1 ceiling by eye across a specific consolidation. `high(126)[5]` is a
  mechanical proxy for "cleared six months of overhead supply". A genuine base
  detector already exists in this repo — `core/darvas/weekly_discovery.py`'s
  box state machine — and is a better instrument for this if you want to
  invest in it. It is not wired in here because the DSL evaluates scalars, not
  state machines.
- **Rule 4 used to fire on the breakout day only** — `volume > volume_sma(50)
  * 2.0` is a same-session test, so it was false on every day but one, and a
  name that broke out three weeks ago and is unambiguously in Stage 2 failed
  it every morning. That made this note audit *the day of* an entry while its
  own name, id and subject all say **stage** — a persistent state. Changed
  2026-08-14 to accept either the breakout bar itself or sustained expansion
  since, so the note now answers the question it is named for.

  The `volume_sma(25) > volume_sma(50) * 1.1` arm is a proxy, not Weinstein.
  He describes volume expanding on rallies and drying up on pullbacks within
  Stage 2; the DSL cannot separate up-days from down-days, so this compares
  the recent window against the base window and accepts the aggregate. A name
  can therefore satisfy it on heavy *distribution*, which is the opposite of
  what Weinstein means. Reading a PASS here as "volume confirms" is only safe
  alongside rules 1–3, which establish that price is advancing.

- **If you want the strict breakout-day auditor back**, copy this note, keep
  arm (a) alone, and give it its own `quantos.id` — e.g. `weinstein_entry`.
  Notes are cheap; overloading one with two meanings is not.

---

## 🧭 Stage classification

The rules above answer *"is this name in Stage 2 right now?"* — one PASS/FAIL.
This block answers the different question the method is actually named for:
**which** stage, out of four. It is a classifier, not a gate. Nothing in
`core/vault/gates.py` reads it, and no execution path branches on it.

The block is evaluated **first match wins**, top to bottom, so line order here
is load-bearing in a way the `quantos-rules` block's order never is.

```quantos-stages
# ── Falling 30-week average ────────────────────────────────────────────────
# Checked first because it is the only unconditional exit. Price above or
# below the average does not rescue it: a rally into a falling 30-week is
# what a Stage 4 bounce looks like, not a Stage 2.
stage 4 when sma(150) < sma(150)[25] * 0.99

# ── Rising 30-week average = Stage 2, split into its phases ────────────────
# The phase labels are the resolution of the Minervini/Weinstein volume
# contradiction documented below: they are consecutive, not competing.
#
# 2 · pivot — volume dried up, the quiet zone before a breakout. Minervini's
#             sixth rule, same 0.40 threshold as his note uses.
stage 2 pivot when sma(150) > sma(150)[25] * 1.01 and volume_sma(5) / volume_sma(50) < 0.40

# 2 · pullback — advance intact, price has come back to or under the average.
#                Still Stage 2: Weinstein treats a pullback to a RISING
#                30-week as the buy zone, not a breakdown. The topping call
#                waits for the slope to flatten, which the next clauses make.
stage 2 pullback when sma(150) > sma(150)[25] * 1.01 and close < sma(150)

# 2 — advancing, nothing special about the volume or the position.
stage 2 when sma(150) > sma(150)[25] * 1.01

# ── Flat 30-week average — the hard case ───────────────────────────────────
# Everything reaching here has a flat average, which describes Stage 1 and
# Stage 3 EQUALLY. They are distinguishable only by what came before: a base
# follows a decline, a top follows an advance. Hence the lag — this compares
# the average five weeks ago against fifteen weeks before that.
#
# The lag is 100, not 125, and the reason is measured rather than chosen:
# sma(150)[125] needs 275 warmed-up bars and the live fetch returns 271.
# See the history note below.
stage 3 when sma(150)[25] > sma(150)[100]

# Terminal default: flat average, prior trend not up. A base.
stage 1
```

### Reading this block

- **The 1% band over 25 sessions is the load-bearing number.** It is what
  separates "rising" from "flat", and therefore where every boundary falls.
  Widen it and Stages 1/3 swallow everything; narrow it and they vanish,
  because a 30-week average is almost never exactly flat.

  Measured across 499 Nifty 500 names, 2026-08-17
  (`scripts/calibrate_stage_band.py`, results in
  `results/stage_band_calibration.json`):

  | band | S1 | S2 | S3 | S4 | ? | churn |
  |---:|---:|---:|---:|---:|---:|---:|
  | 0.00% | 0 | 275 | 0 | 221 | 3 | 0.43 |
  | 0.50% | 45 | 239 | 15 | 196 | 4 | 0.51 |
  | **1.00%** | **84** | **209** | **34** | **166** | **6** | **0.52** |
  | 2.00% | 151 | 162 | 60 | 116 | 10 | 0.50 |
  | 3.00% | 202 | 122 | 87 | 77 | 11 | 0.44 |
  | 5.00% | 257 | 56 | 140 | 31 | 15 | 0.28 |

  **The intended selection rule failed, and the honest version is worth
  writing down.** The plan was to pick the band that minimised churn — how
  often a name flips stage — on the reasoning that a band exists to buy
  stability. But churn is low at *both* ends and flat across the entire
  usable middle. That is not a stability curve; it is a count of how many
  stages are in play. At 0% there is no flat region, so nothing can cross
  into Stages 1 or 3. At 5% Stage 1 has absorbed half the market and there
  are few boundaries left to cross. The metric is confounded with the very
  collapse it was meant to be independent of, so its minimum is an artifact
  and the script now refuses to pick from it.

  **What 1% actually rests on is annualised slope.** The band is a move of
  the 150-day average over 25 sessions, so it scales by 252/25 ≈ 10x: 0.5%
  ≈ 5%/yr, 1% ≈ 10%/yr, 2% ≈ 20%/yr. An average creeping up slower than the
  risk-free rate (~6–7%) is not "advancing" in a sense worth acting on, and
  requiring 20%/yr files ordinary uptrends as bases. 1% clears cash by a
  meaningful margin without demanding a strong trend, and lands where all
  four stages are populated and the largest holds 42%.

  That is a **judgement with its reasoning attached**, not a measurement.
  The distinction is the point: this note has been burned by an unexamined
  threshold once already — the 2.00-vs-1.25 caveat in
  [[Mark_Minervini_VCP_Strategy]], which silently voided that entire
  template — and the fix for that is not pretending a number was derived.
  Do not change this one without re-running the distribution.

- **The history requirement is not flat, because first-match-wins
  short-circuits.** A name with a clearly rising or falling average matches on
  `sma(150)[25]` and needs only **175 bars**; the Stage 3 clause's
  `sma(150)[100]` — **250 bars** — is reached only by names already in the
  flat band. So the deep lag binds exactly where the hard question is, and
  nowhere else.

- **The lag was 125 until the first calibration run, and that was a silent
  kill.** `sma(150)[125]` needs 275 warmed-up bars. The live fetch —
  `FETCH_WINDOW_DAYS = 400` calendar days — returns **271** trading bars, so
  *no symbol in the Nifty 500 could ever satisfy it*. Measured 2026-08-17:
  median 271, max 271, minimum 255. Every name that reached the flat band
  came back unclassified, and Stages 1 and 3 were **empty at every band
  width** — 0 of 499 names, at all nine widths tested.

  This is the same failure shape as the 2.00-vs-1.25 bug in
  [[Mark_Minervini_VCP_Strategy]]: a threshold that looks reasonable in
  prose, is off by a hair against real data, and voids the rule it belongs to
  without erroring. It survived unit tests because the synthetic series there
  are 400 bars long. **Only the live run caught it.** The lag is now 100,
  which needs 250 and clears even the 255-bar minimum with margin.

- Names with too little history come back **unclassified**, not Stage 1 — the
  classifier stops rather than falling through, for the same fail-loud reason
  the auditor separates INSUFFICIENT_DATA from FAIL. A newly listed stock is
  not "basing"; it is unknown.

- **Stage is price structure only.** `rs_rating` is deliberately absent: it
  is injected, not computed, and letting it in would make every symbol
  without a supplied rating unclassifiable. Relative strength stays a
  trend-template concern.

- **Daily bars again.** Same 150-for-30-weeks substitution as the rules
  above, with the same consequence — this will flip stage slightly earlier
  and slightly more often than a weekly chart would.

- **There is a chart for this.** `pine/weinstein_stage_journey.pine` draws
  the same classification on TradingView: background shaded by stage, the
  30-week average coloured by slope, and a label at every transition. It
  pulls everything at daily resolution regardless of the chart's own
  timeframe, so the label describes the security rather than your zoom
  level, and so it stays comparable with this note.

  It is a hand transcription, and `tests/unit/test_stage_pine_mirror.py`
  asserts the two produce identical timelines — including that the check
  itself notices injected drift. `pine/darvas_breakout_alert.pine` diverged
  from its Python counterpart for months without anything noticing; this is
  the mechanism that stops a repeat.

---

## 🔗 Relationship to the rest of the system

- [[Mark_Minervini_VCP_Strategy]] — the SEPA trend template is a stricter
  descendant of this on the *price* rules. Minervini's
  `Close > SMA50 > SMA150 > SMA200` stack implies Weinstein's rule 1 and then
  adds two more moving averages.

  **On volume the two are opposed, and this is not a detail.** Minervini's
  sixth rule wants volume *drying up* (`volume_sma(5)/volume_sma(50) < 0.40`);
  rule 4 here wants it *expanding*. Those describe consecutive phases — the
  quiet pivot before a breakout, and the breakout and advance after it — so a
  name satisfying both at once is rare by construction, not merely by
  strictness. Measured 2026-08-14 across 482 Nifty 500 names: **5 cleared
  Minervini, 11 cleared this note, 0 cleared both.**

  An earlier version of this section called auditing against both "a high bar
  and is meant to be". That was wrong: it is closer to a contradiction than a
  bar, and reading a combined score as "how good is this name" conflates two
  disciplines that cannot both fire. Read the two verdicts side by side. The
  cockpit shows them as separate columns for exactly this reason and never
  sums them.
- Weinstein's own weakness in this repo's terms: it is a trend-following
  breakout method, and every trend-following breakout candidate tested here so
  far has failed on turnover and cost grounds (Darvas S7-3, Dow theory, 10:10
  breakout). Treat a `PASS` as "this name matches what Weinstein described",
  which is a statement about structure — not evidence of an edge. Nothing in
  this vault has been backtested.
