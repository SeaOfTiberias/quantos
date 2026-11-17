# Pick and entry plan (one page, for review)

**Status, 2026-11-16:** the plan is in code (`core/market_map/call_plan.py`, commit d06b88d) and runs paper only. Nothing in it places an order. Trading is paused. This page is for reviewers, human or model: the questions at the end are what we want judged.

## The idea in one line

A screener picks the stock and the side. A price map picks the entry. We don't buy the breakout itself: we wait for price to come back and take out the liquidity under a structural level, then close back above it.

**Why:** our Darvas paper picks bought every breakout at 92–98% of the 20-day range and lost −10.9% over 8 trades. Most of those stocks first came back to a level that was already on the map, then rallied.

## 1. Picks: where stocks come from (unchanged)

| Source | What it selects | Side |
|---|---|---|
| **Darvas scan** (evening, Nifty 500) | A fresh close above a Darvas box ceiling, with box width 35–50% (Bucket B) | Long only |
| **F&O screener** (evening, stock F&O universe) | Near the 52-week high, a weekly Darvas box breakout up to 5 sessions old, EMA9 above EMA21, not a momentum laggard. Puts use the same test on price-inverted bars. | Calls and puts |

Futures OI build-up is shown for context but filters nothing. The pick says only *which stock, which way*. It is never the entry.

## 2. The map: what counts as a level

Each pick gets a card built from daily, weekly and monthly bars over six years (the L1 store). A level is **structural liquidity** only:

- D/W/M **protected** swing lows (highs for puts);
- **equal lows**: two minor swing lows within 0.25 ATR of each other;
- **multi-touch** levels;
- the edge of a **strong or protected** higher-timeframe order block or FVG.

A single minor swing low, a daily FVG, CPR lines and weak highs do **not** count on their own. The plan's level is the nearest structural level 0.2–4 ATR below the price; levels within 0.5 ATR of each other form one pool, and the plan uses the pool's far edge. ATR is the 14-day daily ATR.

## 3. Entry conditions (all must hold)

1. **Level locked at the pick.** The level comes from the card on the pick day. A later evening's map may move it only to a newer *protected* level that is nearer the price. It never moves to a zone edge and never further away.
2. **Sweep.** A daily low trades at least **0.25 ATR below** the level. A smaller poke is not a sweep.
3. **Reclaim.** Within **3 sessions** of the sweep, a daily close back above the level. No reclaim means the level broke: no trade, watch the other side.
4. **Entry** at the next session's open.
5. **Stop** 0.1 ATR below the lowest low since the sweep.
6. **Target**:
   - the nearest level of any kind on the card at least **1 ATR** above the price on the evening the level locked (usually the pick day). Any kind means: a supply zone edge, a protected or weak high, a W/M CPR line, or a daily zone edge. Weak highs and CPR lines don't count as sweep levels but do count as targets;
   - if there is none overhead (a breakout at highs), **2R** from the entry.
7. **No trade if:**
   - at the entry open the target is less than **1R** away;
   - the open is already beyond the stop or at the target;
   - the target was reached before any sweep (the move ran without us).
8. **One re-try.** After a stop, or a skip at the open (R:R, or opened beyond the stop), the same level gets one more go, with a fresh 20-session wait:
   - **after a stop**, the stop-out bar counts as the new sweep, and the 3-session reclaim window starts there;
   - **after a skip**, the new sweep must trade beyond the first sweep's low.

   A 2R target is recomputed for the new entry.
9. **Waiting and holding.** The plan waits up to **20 sessions** for a sweep. After entry it holds at most **15 sessions**, then exits at the close.
10. **Results.** No entry if the company's results are due within 5 sessions of the entry day. An open trade exits at the close of the session before results, because a results gap jumps any stop. Dates come from NSE's board-meetings feed. Replays have no history of that feed, so this rule acts only on live picks.

Puts are the mirror image: a sweep above a high and a close back below it.

## 4. Continuation starter (Darvas picks only, unproven)

A breakout that never pulls back is the cost of this plan (DIVISLAB +16% in the Darvas sample). On the 194 F&O calls, 27 of the 39 picks the plan missed but a plain trade won were breakouts that never came back.

The starter was switched on for F&O picks on 2026-11-16 and switched off the same day. On those 194 calls it made +0.46R on calls, but October was a rally. Over 2021–2026 on the same 79 F&O stocks it made +0.06R on calls (1,403 cases, −0.04R in 2024–26) and −0.15R on puts (327 cases). That is no edge before option costs. It stays on Darvas picks as a paper starter, scored separately, and counts as unproven. To keep a foot in:

- **Trigger:** the session after the breakout closes **green and above the breakout day's close**.
- **Entry:** a small starter at the next open.
- **Stop:** 0.1 ATR under the lower of the two sessions' lows.
- **Target:** same rule as the main entry.

If there is no follow-through, there is no starter. **The starter risks 25% of the main entry's risk** (if it is stopped, that costs 0.25 of a main-trade R). The main size comes only from the sweep entry. Starters are scored apart from main entries, so they don't muddy the test of the sweep entry.

## 5. Evidence so far (be skeptical of it)

- **8 Darvas paper picks**, Sep–Nov 2026, replayed day by day with no lookahead:
  - Sweep entries: GLAND 2858.9 → 3248.8 (**+3.94R**), ZYDUSLIFE 1155 → 1258 (**+1.6R**), PERSISTENT 5742 → 6190 (**+1.68R**).
  - No entry: CYIENT (the level broke) and PTCIL (never swept). The other three are still waiting.
  - Starters: −1R, −1R, +3.07R, and two still open.
  - **The rules in section 3 were adjusted on these same 8 picks** to match a human chart read. This shows the code reads charts the way the human does. It is not evidence of an edge.
- **194 F&O calls, 9 Oct–13 Nov**, which these rules were never adjusted on. The previous version of the rules entered 47 of them (46 in commit c0e2213's note; the replay log says 47), at a mean of −0.29R.
  - With the NIFTY guard and the weekly cap (fno_l12) it entered 9, and 8 closed at −0.28R. The guard cancelled 55. Without them it was 17 closed at −0.01R.
- **History replays (2026-11-17), the 20:00 job's code run day by day:**

  **F&O screener picks, Sep 2025 – Nov 2026 (870 picks).**

  | Half | Main entries closed | Mean R |
  |---|---|---|
  | First | 56 | −0.19 |
  | Second | 64 | −0.32 |

  - Paired over every pick: the plan made −0.06% vs +1.03% for the picks as sent in the first half, and −0.11% vs −1.12% in the second.
  - Starters: −0.02R and −0.13R.
  - **The F&O call plan FAILS section 6.** Its entries average below 0R in both halves. The picks' side selection is the problem; the entry can't fix it.

  **Darvas Bucket B, 2016–2023 (922 picks, against the real ATR-stop trades).**

  | Period | Main entries | Mean R | Picks entered |
  |---|---|---|---|
  | 2016–19 | 45 | +0.16 | 39 of 347 |
  | 2020–23 | 90 | +0.30 | 72 of 575 |

  - On the picks it entered, the map turned losers into winners: +1.13% vs −4.14% as traded (2016–19), and +0.82% vs −3.07% (2020–23).
  - But it enters only about 12% of the picks. Per pick, the plan made +0.13% / +0.10%. The Darvas trades as actually taken made +0.74% / +3.74%.
  - **The map entry must not replace the Darvas trade.** It works as a second chance on picks that pull back, which is a lead for its own test.
  - NIFTY guard: in the Darvas history, CE entries with NIFTY's D up made +0.42R (n 68); with D down, +1.06R (n 7). The guard cancelled 114 Darvas and 164 F&O pending entries. There was no no-guard history run, so the guard is kept but unproven.
- **Project history:** about 20 strategy candidates tested since July 2026, most failed. The map's older 100-day zones failed a placebo test. The current higher-timeframe map is untested as a predictor.

## 6. How it will be judged

**The constants are frozen at commit d06b88d, plus the review fixes, until the forward sample closes.** These are the 0.25 ATR sweep depth, the 3-session reclaim, the 0.1 ATR stop, the 1 ATR minimum target, 1R minimum, 2R with nothing overhead, a 20-session wait and a 15-session hold.


Paper only. Every plan and event is journalled before the outcome.

The report scores four things:
- main sweep trades and starters separately;
- closed trades separately from open ones;
- exits by type (target, stop, time) and entries by level type;
- **every pick, paired**: the plan's result (0 if it never entered) against the pick as sent, from the pick-day close over the same 35 sessions (20-session wait plus 15-session hold).

The paired number decides. If the plan's entries average at or below 0R, and the plan's total doesn't beat the picks as sent, the plan stays a reading aid and we stop tuning it.

Twenty closed trades only catches a disaster: at about ±0.4R on the mean, it can't show an edge.

## Questions for reviewers

1. Is the definition of "structural level" sound, or does it let in levels that are mostly noise?
2. Are the 0.25 ATR sweep depth, the 3-session reclaim window and the 0.1 ATR stop reasonable, or are they fitted to 8 cases?
3. Is locking the level at the pick day right, or should the level follow new structure more freely?
4. Is the 2R target with nothing overhead sensible for breakouts at all-time highs?
5. What would make this plan look good in replay but fail live? Consider survivorship, fills at the open, gaps and costs on options.
6. Is 20 closed trades enough to decide anything? If not, what is?
