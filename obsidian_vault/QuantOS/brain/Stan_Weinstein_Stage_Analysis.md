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
