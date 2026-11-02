# Market Map Engine: design (draft 2026-11-03)

Status: **draft for the user's review.** Nothing here is built yet beyond the price map that
already exists (`core/price_map/`, fba727f, 2026-10-28).

## 1. Why

On 2026-11-02 trading was paused, after a ~Rs 16k loss on a HDFCBANK futures short. The user
summed up the problem as "amazing inference, data mining, insight, but no trading intelligence":
we were "steering by the trees without a map of the forest".

Two concrete failures:

1. **The map was too short-sighted.**
   - HDFCBANK was shorted at about 678, with a target of 665.
   - The weekly and monthly charts show the stock back inside its 2021-24 base, about 640-840. That base is a multi-year demand zone in a stock index funds own.
   - Smart Money Concepts (SMC) marks a strong low near 665, which is exactly where the target was.
   - Our own map for 2026-10-28 said "nearest strong zone below: none". It looks back only 100 days, and its slowest pivot is monthly.
2. **The map wasn't on the decision path.**
   - The tools used to shortlist and plan trades are `levels`, `pick_structure`, `screener` and `ideas`. None of them return the map.
   - So the map existed and was still forgotten. Memory notes don't fix that, because they are an index, not a gate.

**Principle:** whatever matters when a decision is made must come back in the output of the
tools used to make it, every time, computed by code.

The strategy backtest engine answers "does this rule make money?". The Market Map Engine answers
"where are we, and what does that mean for this trade?". It becomes the backbone of the filters
and of execution.

## 2. What the engine is, and isn't

- **It describes structure. It doesn't predict or decide.**
  - Its outputs are deterministic facts: "price is inside the weekly 640-840 base", "SMC strong low at 665", "Bank Nifty is at its monthly value area low".
  - Each fact is reproducible from the data that existed at that moment.
- **Turning facts into filters needs evidence.**
  - A fact or situation becomes a hard filter (blocking a trade or a shortlist entry) only after a pre-registered test shows it separates outcomes.
  - Until then it is shown, labelled **untested**, for the user to judge.
  - Anything that fails its test is shown as "failed its test" and never filters.
- **No hand-tuned composite score.** A weighted "conviction score" would be another untested model. The engine speaks in a small, fixed vocabulary of named situations (section 4), and each one is testable on its own.
- **One code path for live and backtest.**
  - The same functions build the map for today and for any past day D, from data before D only.
  - That way what we test is exactly what we use.

## 2b. Decisions (user, 2026-11-03)

- **Swing first, intraday later.**
  - The first build works on monthly, weekly and daily bars, plus composite profiles built from daily bars.
  - Opening range, initial balance and open types wait for the intraday phase.
  - This also removes most of the dependence on Fyers 5-minute history.
- **Frameworks apply at both levels.** Each framework below is applied to indices and stocks alike:
  - Ochoa (classical and Camarilla pivots, CPR, pivot width, two-day relationships, money zone, market structure);
  - Dalton market profile;
  - SMC.

  The Nifty CPR is the most-watched pivot in India, so pivots belong in the market layer too.
- **SMC and pivots combine as confluence, not as rival systems.**
  - SMC says where structure and liquidity are: trend state, order blocks, equal highs/lows, strong lows.
  - Pivots and profile give fixed reference prices.
  - A zone where an SMC level and a pivot or value-area edge agree is exactly the "two families agree" rule the existing map already uses.
  - Some ideas appear in more than one framework; these count as one family, not two, so agreement isn't double-counted:
    - Dalton's poor highs and lows (unfinished auctions) and SMC's equal highs and lows are the same idea: resting orders at a clean edge;
    - an SMC order block is close to the origin of a profile imbalance.
- **Golden set:** the user annotates charts in Zerodha (Kite) and TradingView. Process in section 6.
- **OI and positioning:** added as an independent witness, not as "smart money" (section 3, L0 and L3).

## 3. The map: four layers, top-down

Each layer reads the one above it first: the forest, then the trees.

### L0. Market

The market layer covers these instruments:

- Nifty 50, Nifty 500, Bank Nifty, Midcap 150, Smallcap 250;
- the sector indices: Bank, IT, Pharma, FMCG, Auto, Metal, Realty, Energy, PSU Bank, Fin Services, and others.

It reads:

- **Structure,** for each index, with the same engine as a stock (L1 and L2): multi-timeframe trend, zones, SMC state, and where price sits in its range.
- **Breadth,** from the daily bhavcopy:
  - share of stocks above their 50-day and 200-day averages;
  - advance/decline;
  - 52-week new highs minus new lows;
  - share of stocks inside their own HTF demand or supply.
- **Sector rotation:** relative strength of each sector against the Nifty 500 on two speeds (for example 13 and 52 weeks), giving quadrants: leading, weakening, lagging, improving.
- **Volatility, as context only:** the India VIX level and its percentile.
  - Five volatility-conditioning signals have already failed, so VIX never filters on its own.
- **Positioning:**
  - NSE participant-wise OI: FII, DII, Pro and Client long/short in index futures and options. This is the one public dataset that says *who* holds positions.
  - Nifty and Bank Nifty option OI by strike (put-call ratio, max-OI strikes) and FII/DII cash flows.

  Positioning is read as "who is positioned where, and who is trapped", not as smart money's direction. Every open contract has a buyer and a seller, and most index option volume is retail.

### L1. Stock: higher timeframe (monthly and weekly)

- **Multi-year swing structure:** higher highs and higher lows (HH/HL) versus lower highs and lower lows (LH/LL), on the monthly and weekly charts.
- **Multi-year demand and supply zones:** the bases price left with force, plus levels tested more than once.
- **SMC layer**, written to our own published definitions, not LuxAlgo's code:
  - BOS / CHoCH, giving trend state and the latest change;
  - order blocks;
  - EQH / EQL, which are stop clusters (liquidity pools);
  - strong and weak highs and lows;
  - premium or discount within the current dealing range.
- **Long-horizon volume profile:**
  - composite POC and value area over 1-3 years;
  - built from daily bars (volume spread evenly over the day's range), and labelled as an approximation;
  - the 5-minute profile stays for the last 100 days.
- **Quarterly and yearly pivots,** alongside the existing monthly ones.

### L2. Stock: tactical (daily and intraday)

- The existing price map: 100-day swings, 5-minute volume profile, naked POCs, daily Camarilla, weekly and monthly pivots.
- Ochoa's pivot work (*Secrets of a Pivot Boss*):
  - **CPR** and its width, a forecast of a trend day versus a range day;
  - **two-day pivot relationships:** higher value, lower value, inside or outside;
  - the developing pivot and value for the session.
- Intraday auction context, from Dalton's *Mind Over Markets* as Ochoa uses it: initial balance, open type, and acceptance or rejection at a level (closes inside value versus wicks through it).

### L3. Relationship: stock to sector to market

- Relative strength of the stock against its sector and against the Nifty 500.
- **Index-heavyweight flag:** the stock's weight in the Nifty and in its sector index. For a stock like HDFCBANK, index flows matter at major levels.
- **Alignment:** is the stock moving with its sector and the market, or against them? For example, on 23 Oct HDFCBANK held at -0.2% while Bank Nifty fell 1.4%. That is a stock absorbing selling at support, and it was noted and then ignored.
- **OI at location.** Stock futures OI build-up is read against the map, not on its own:
  - short build-up into HTF supply means shorts are positioned with structure;
  - short build-up into HTF demand means late shorts who are fuel for a squeeze.

  Two examples from our own record:
  - HDFCBANK, 10-23: +5.4% OI short build-up at its multi-year base. We read it as confirmation for the short; it was the crowd selling into demand.
  - RELIANCE: +56% OI short build-up in the week before the 11-02 results gap of +6%.

  Whether "positioning agrees with structure" improves outcomes is a situation to test (`POSITIONING`), not an assumption.

### F. Fundamentals and ownership (added 2026-11-03)

Point-in-time only: a figure counts from the day after it was published. This layer reuses the
techno-funda pipeline (`core/techno_funda/fundamentals.py`, NSE results XBRL).

- **Quality and growth:**
  - profit growth (quarter on the same quarter a year ago);
  - TTM operating margin;
  - their trend over the last 4 quarters.
- **Event risk:** the next results date from NSE board meetings. A swing trade across results is a different trade.
- **Ownership: who holds it and who is adding.**
  - NSE quarterly shareholding patterns: promoter, FII, mutual fund, insurance, retail;
  - the change on the quarter;
  - index membership and weight.

  This tests the HDFCBANK thesis directly: institutional holders adding at a multi-year base.
- **The techno-funda backtest decides how much of this filters.** If fundamentals add nothing there, they stay context.

### Noise assessment (2026-11-03, before any test)

Expected to be the weakest for swing trades. All are still tested, but none gets a place on
trust:

- **Daily pivots and daily Camarilla:** intraday tools. Out of the swing phase.
- **Weekly and monthly classical pivots:** formulas of the last period's high, low and close, so largely redundant with swing highs and lows. Expected weak.
- **Order blocks:** definitions vary and there are many candidates, so the overfit risk is high. Strict test.
- **Premium and discount:** depends on which dealing range is chosen, which is arbitrary.
- **Option put-call ratio, max-pain, and day-to-day FII/DII cash flows:** noisy for a swing decision. Context, at most a weekly trend.
- **VIX:** five volatility-conditioning signals have already failed. Context only.

Expected to be the strongest:

- multi-year HTF zones and structure;
- ROOM (pure risk:reward geometry);
- timeframe alignment;
- relative strength;
- fundamentals and ownership.

## 4. Inference: from levels to situations

The "intelligence" is here, and it is code: a fixed, named vocabulary computed for any symbol, on
any day, and for any proposed trade. These are first drafts, to be refined with the user.

| Situation | Meaning (all computed, point-in-time) |
|---|---|
| `LOCATION` | at HTF demand / at HTF supply / mid-range / no-man's land; premium or discount in the dealing range |
| `ALIGNMENT` | monthly, weekly and daily structure agree, or which one conflicts |
| `MARKET_BACKDROP` | the index and the sector: their own LOCATION and ALIGNMENT, breadth state, sector quadrant |
| `ROOM` | for a proposed trade, distance in R to the first opposing strong zone (`first_obstacle` exists already) |
| `STOP_PLACEMENT` | the stop sits behind a zone (protected), inside one (noise), or inside a stop cluster (likely to be swept) |
| `LIQUIDITY_SWEEP` | price traded through an EQL/EQH or a strong low/high and closed back inside |
| `STRUCTURE_SHIFT` | a CHoCH on a named timeframe, plus its direction and age |
| `ACCEPTANCE` | at a zone: closes and value building inside (acceptance), or wicks and quick rejection |
| `RELATIVE_STRENGTH` | the stock holds or leads while its sector or index falls, or the reverse |
| `POSITIONING` | OI build-up (stock futures; participant-wise OI for indices) with structure, or against it (trapped side) |

**Trade verdict.** For a proposed trade (side, entry, stop, target), the engine returns:

- with structure or against it, on each timeframe;
- ROOM in R;
- STOP_PLACEMENT;
- the market backdrop;
- each line labelled with its test status.

Worked example, HDFCBANK short on 2026-10-23, written as the engine should have read it:

- LOCATION: at monthly and weekly demand (the 2021-24 base), deep discount.
- ROOM: 0.3R to the SMC strong low at 665.
- RELATIVE_STRENGTH: held while its sector fell.
- So: against the higher-timeframe structure, with no room.

## 5. Use at decision time: the backbone

One entry point, `map_read(symbol, trade=None, as_of=None)`, returns L0 to L3 plus the
situations and, when a trade is given, the trade verdict. Everything below calls it. Nobody has
to remember it.

| When | Where | What happens |
|---|---|---|
| Pre-market | morning brief (Telegram and cockpit) | market map first: indices, breadth, sector quadrants, what changed overnight; then the watchlist |
| Shortlisting | `screener` (MCP and cockpit) | each candidate carries LOCATION, ROOM and MARKET_BACKDROP columns. Tested situations filter; untested ones are shown and labelled |
| Forming an idea | `levels`, `pick_structure` (MCP) | `levels` leads with the map read. `pick_structure` gets location flags next to R1-R6: target through a strong zone, stop inside a zone or stop cluster, against HTF structure, no room |
| Logging an idea | `scripts/trade_ideas.py` | the map read is computed and stored with the idea, frozen. No map read means the idea is not logged. This is the learning record |
| Order ticket | `scripts/qorder.py` | the ticket shows the trade verdict above the confirm line |
| In a trade | position manager, trade watcher | they subscribe to map events for open positions: entering an opposing strong zone, a sweep, a CHoCH against the position, the market backdrop flipping. **Alerts only.** An exit rule built on a map event needs its own pre-registration and the user's go-ahead (CLAUDE.md: exits are rule-driven code, never a model) |
| Any session | CLAUDE.md | one standing line: "Any trade discussion starts from `map_read`." This is a backstop; the wiring above is the real fix |

## 6. How we know it works

1. **Fidelity: does it see what the user sees?**
   - A golden set of charts the user annotates (HDFCBANK and SUPREMEIND first, from the 2026-11-02 screenshots), each marking zones, structure, strong lows and stop clusters.
   - The engine must reproduce those labels.
   - It is also compared with LuxAlgo SMC on the same charts, for verification only.
   - These become unit tests.
   - **How to annotate:**
     - one screenshot per chart (symbol, timeframe, date visible);
     - a short note listing each level: price or zone, type (demand/supply, strong low, EQL, order block, pivot, value area...), and why.
     - Crop out any positions, holdings or order panels from Zerodha first. Account data never goes into the repo.
2. **Signal: does a fact turn price?**
   - A pre-registered test per family and per situation, against placebo levels.
   - The first one exists and has not been run: `docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md`. It is run as frozen.
   - Then one test each for the HTF layer, the SMC layer and the market backdrop, with every family scored separately so we learn which ones carry information.
3. **Usefulness: does it change trade outcomes?**
   - Two sources: the frozen map snapshots in the idea log, and the strategy backtests rerun with a map filter (for example "no shorts at HTF demand" on the put-retest plan's history).
   - Each is pre-registered, and a failure is reported as a failure.
4. **Point-in-time.** Every test rebuilds the map from data before day D only. There is one code path for live and test.

## 7. Data

| Need | Source | Status |
|---|---|---|
| Daily OHLCV, all NSE stocks, 2000- | NSE bhavcopy cache | have; split/bonus adjustment in `core/techno_funda/prices.py` (reuse) |
| Index OHLC, all NSE indices | NSE `ind_close_all_DDMMYYYY.csv` (fetchable); TradingView to cross-check | Nifty 500 / MidSmall 400 / Smallcap 250 closes on hand (d0d2c39); others to fetch |
| Intraday 5-min bars | Fyers history from the VM | 100-day window works; depth for a 1-year test to be measured (rate limits seen before) |
| Index weights | NSE index factsheets / constituents files | to check |
| Option chain / OI | VM recorder (since 09-30), bhavcopy F&O | have; context only |

## 8. Build order

Each phase is small, unit-tested and committed. Every phase from P2 on extends `map_read`, so
it is used the day it lands.

- **P0 (fix the forgetting):**
  - add `map_read` over the existing map;
  - wire it into `levels`, `pick_structure` (location flags), the idea log and `qorder`;
  - add the CLAUDE.md line.
  - Everything is labelled untested.
- **P1:** run the 2026-10-28 zone test as frozen.
- **P2:**
  - L1 higher-timeframe layer and SMC layer on adjusted daily, weekly and monthly bars;
  - quarterly and yearly pivots;
  - long-horizon profile;
  - the golden set with the user.
- **P3:**
  - L0 market map: index structure, breadth, sector rotation;
  - the pre-market brief.
- **P4:**
  - situation vocabulary and trade verdict;
  - pre-registered tests per situation (section 6.2-6.3).
- **P5:**
  - in-trade map events in the position manager and trade watcher (alerts);
  - any exit rule built on them gets its own pre-registration and go-ahead.

Trading stays paused through all of this unless the user decides otherwise.

## 9. Open questions for the user

1. Which frameworks first, and in what form?
   - Ochoa: CPR, two-day relationships, Camarilla, money zone.
   - Dalton: market profile, open types.
   - SMC.
   - Your own reading: which levels do you actually act on?
2. Timeframe of the trades the engine should serve first: positional/swing (weeks) or intraday.
3. The golden set: about 10-20 charts you annotate, or we review together, to pin down definitions (what counts as a demand zone, a strong low, acceptance).
4. Should the market backdrop also include FII/DII cash flows and the Nifty futures/options positioning (PCR, OI at strikes)? These are available, and context only.
