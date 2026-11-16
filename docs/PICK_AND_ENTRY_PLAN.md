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
   - the nearest opposing level (supply, protected high, strong zone) at least **1 ATR** above the pick-day price;
   - if there is none overhead (a breakout at highs), **2R** from the entry.
7. **No trade if:**
   - at the entry open the target is less than **1R** away;
   - the open is already beyond the stop or at the target;
   - the target was reached before any sweep (the move ran without us).
8. **One re-try.** After a stop, or a skip at the open, the same level gets one more sweep-and-reclaim.
9. **Waiting and holding.** The plan waits up to **20 sessions** for a sweep. After entry it holds at most **15 sessions**, then exits at the close.

Puts are the mirror image: a sweep above a high and a close back below it.

## 4. Darvas starter (Darvas picks only)

A breakout that never pulls back is the cost of this plan (DIVISLAB +16% in our sample). To keep a foot in:

- **Trigger:** the session after the breakout closes **green and above the breakout day's close**.
- **Entry:** a small starter at the next open.
- **Stop:** 0.1 ATR under the lower of the two sessions' lows.
- **Target:** same rule as the main entry.

If there is no follow-through, there is no starter. The main size comes only from the sweep entry. Starter size against main size is not yet set.

## 5. Evidence so far (be skeptical of it)

- **8 Darvas paper picks**, Sep–Nov 2026, replayed day by day with no lookahead:
  - Sweep entries: GLAND 2858.9 → 3248.8 (**+3.94R**), ZYDUSLIFE 1155 → 1258 (**+1.6R**), PERSISTENT 5742 → 6190 (**+1.68R**).
  - No entry: CYIENT (the level broke) and PTCIL (never swept). The other three are still waiting.
  - Starters: −1R, −1R, +3.07R, and two still open.
  - **The rules in section 3 were adjusted on these same 8 picks** to match a human chart read. This shows the code reads charts the way the human does. It is not evidence of an edge.
- **194 F&O calls, 9 Oct–13 Nov**, which these rules were never adjusted on: *replay running, result to be added here.* The previous version of the rules entered 47 of them, at a mean of −0.29R.
- **Project history:** about 20 strategy candidates tested since July 2026, most failed. The map's older 100-day zones failed a placebo test. The current higher-timeframe map is untested as a predictor.

## 6. How it will be judged

Paper only. Every plan and event is journalled before the outcome. The plan gets no real capital before at least 20 closed sweep trades, scored in R against the picks as sent (entered at the pick-day close). Starters are scored separately.

## Questions for reviewers

1. Is the definition of "structural level" sound, or does it let in levels that are mostly noise?
2. Are the 0.25 ATR sweep depth, the 3-session reclaim window and the 0.1 ATR stop reasonable, or are they fitted to 8 cases?
3. Is locking the level at the pick day right, or should the level follow new structure more freely?
4. Is the 2R target with nothing overhead sensible for breakouts at all-time highs?
5. What would make this plan look good in replay but fail live? Consider survivorship, fills at the open, gaps and costs on options.
6. Is 20 closed trades enough to decide anything? If not, what is?
