---
tags:
  - strategy/momentum
  - trading/stage-analysis
  - screening/trend-template
  - algo/feature-extraction
quantos:
  id: weinstein_stage2
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
   least double the recent average on the breakout week.
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

# 4. Volume expansion on the move: today at least 2x the 50-day average.
volume > volume_sma(50) * 2.0

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
- **Rule 4 fires on the breakout day only.** Volume at 2x the 50-day average is
  a same-session condition, so this note effectively audits *the day of* a
  Stage 2 entry, not "is this in Stage 2". If you want the latter, copy this
  note, delete rule 4, and give it its own `quantos.id`. Notes are cheap;
  overloading one with two meanings is not.

---

## 🔗 Relationship to the rest of the system

- [[Mark_Minervini_VCP_Strategy]] — the SEPA trend template is a stricter
  descendant of this. Minervini's `Close > SMA50 > SMA150 > SMA200` stack
  implies Weinstein's rule 1 and then adds two more moving averages.
  Auditing against **both** notes means a name has to satisfy both; that is a
  high bar and is meant to be.
- Weinstein's own weakness in this repo's terms: it is a trend-following
  breakout method, and every trend-following breakout candidate tested here so
  far has failed on turnover and cost grounds (Darvas S7-3, Dow theory, 10:10
  breakout). Treat a `PASS` as "this name matches what Weinstein described",
  which is a statement about structure — not evidence of an edge. Nothing in
  this vault has been backtested.
