# Sprint: Market Map Engine (swing first)

Started 2026-11-03. Design: `docs/MARKET_MAP_ENGINE_DESIGN.md`. **Trading is paused** (2026-11-02)
until the user decides otherwise. Nothing in this sprint places, sizes or changes an order.

## How every session runs

**Start:**

1. Read this file, then the design doc, then the tracker below.
2. Do the first unchecked session.

**During:** follow the standing rules in CLAUDE.md.

- Pre-register before any test, and report a failure as a failure.
- Use synthetic fixtures; household data never goes into the repo.
- Deploy only with `scripts/deploy-vm.ps1`, outside 09:15-15:30 IST.

**End:**

1. Tick the tracker and write one line of outcome with the commit hash.
2. Note anything that changes later sessions under "Changes to the plan".
3. Commit and push, then update memory.

A session that can't finish says so in its tracker line. It isn't ticked.

**Kickoff prompt** (the user pastes this to start or resume):

> Continue the Market Map Engine sprint. Read docs/MARKET_MAP_SPRINT_PLAN.md and
> docs/MARKET_MAP_ENGINE_DESIGN.md, then do the next unchecked session. Before you build anything,
> tell me which session it is and what "done" means for it.

## Sessions

### S1. Close out techno-funda (carried over)

- Check the fetch finished cleanly (`logs/techno_funda_fetch.stderr.txt`). Re-run `--stages xbrl` to retry the failures.
- Run `python scripts/techno_funda_gates.py --refresh`.
- Report D1-D5 to the user. Any stop means the backtest does not run, and nothing is substituted.
- Only if every gate passes: run `python scripts/backtest_techno_funda.py`, then commit and push the results before reporting them.
- **Done when:** the gates (and the results, if the gates pass) are committed, and the user has the verdict.

### S2. P0: put the existing map on every decision path

- Add `core/market_map/read.py: map_read(symbol, trade=None, as_of=None)` over the existing `core/price_map`.
  - It returns the nearest strong zones above and below, the first obstacle in R, and whether the stop sits inside a zone.
  - Every line is labelled "untested".
- Wire it into four tools:
  - `levels` (MCP) leads with the map read;
  - `pick_structure` gets location flags next to R1-R6: target through a strong zone, stop inside a zone. They are advisory; they don't change the ranking yet;
  - `scripts/trade_ideas.py` stores a frozen map read with every idea, and an idea is refused without one;
  - `scripts/qorder.py` shows the map read above the confirm line.
- Build maps on demand: when no map file younger than N days exists, build one.
- Add the CLAUDE.md line: "Any trade discussion starts from `map_read`."
- Unit tests on synthetic bars. Deploy (outside market hours).
- **Done when:** `levels HDFCBANK` on the VM shows the map, and an idea can't be logged without one.

### S3. P1: run the 2026-10-28 zone test, as frozen

- Measure how much Fyers 5-minute history the VM can pull, and at what rate, before committing to the full pull.
- Write the runner for `docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md`: point-in-time maps, the event and outcome rules, placebo and weak-zone controls, and the session bootstrap.
- Run it and report pass or fail on criteria 1-5. No re-tuning.
- If the history isn't deep enough for about 300 events: report that and stop. Don't shorten the test.
- **Done when:** the results doc is committed and the user has the verdict.

### S4. Golden set and definitions (with the user)

- **Input:** the user's annotated charts from Zerodha and TradingView. HDFCBANK and SUPREMEIND first, 10-20 in all, cropped of any account panels.
- Store them under `docs/golden_set/` as screenshot plus note. No account data.
- Write `docs/MARKET_MAP_DEFINITIONS.md`: exact, codeable rules for each item below, settled against the user's marks and the user's copy of Ochoa:
  - HTF swing structure, multi-year demand and supply zones;
  - SMC (BOS, CHoCH, order block, EQH/EQL, strong and weak highs/lows, premium and discount);
  - weekly and monthly CPR, two-day relationships, Camarilla, money zone;
  - long composite profile.
- Mark which ideas overlap (poor highs/lows = EQH/EQL), so they count as one family.
- Pre-register the test of the HTF and SMC layers (zones turn price versus placebo, each family separately) **before any L1 code**.
- **Done when:** the definitions and the pre-registration are committed and the user has approved them.

### S5. P2: L1, the stock's higher-timeframe layer

- Build weekly and monthly bars from the adjusted daily bhavcopy, reusing `core/techno_funda/prices.py` adjustment.
- Code exactly per the definitions doc:
  - swing structure and multi-year zones;
  - the SMC layer;
  - quarterly and yearly pivots;
  - weekly and monthly CPR with Camarilla;
  - long composite profile from daily bars, labelled as an approximation.
- Golden-set unit tests: the engine must reproduce the user's marks within tolerance.
- Extend `map_read` with L1, so it's used the day it lands.
- **Done when:** the golden-set tests pass, and `levels HDFCBANK` shows the 640-840 base and the strong low near 665 as at 2026-10-23.

### S6. P3: L0, the market map

- **Index OHLC history:**
  - fetch NSE `ind_close_all_DDMMYYYY.csv` for all indices (broad and sector) from 2010;
  - cross-check sample dates with TradingView.
- Run the same L1 and L2 engine on the indices.
- **Breadth from the bhavcopy:** share above the 50- and 200-day averages, advance/decline, 52-week new highs minus new lows.
- **Sector rotation:** relative strength against the Nifty 500 on 13 and 52 weeks, with quadrants.
- **Positioning:** NSE participant-wise OI (FII, DII, Pro, Client) and FII/DII cash flows. Context only.
- **Pre-market brief** (Telegram and cockpit): market first, then sectors, then the watchlist.
- **Done when:** the brief runs on the VM, and `map_read` includes the market backdrop.

### S6b. Layer F: fundamentals and ownership

- Reuse the techno-funda point-in-time fundamentals: growth, OPM and their trend.
- Fetch NSE quarterly shareholding patterns (promoter, FII, MF, insurance, retail; change on the quarter) and index weights.
- Add the results date (event risk) from NSE board meetings.
- Extend `map_read` with layer F.
- How much of it filters depends on the S1 techno-funda verdict and the S8 tests.
- **Done when:** `map_read HDFCBANK` shows growth, OPM, the FII/MF holding trend and the next results date, all as of the day.

### S7. P4: situations and the trade verdict

- Code the situation vocabulary (design section 4):
  - LOCATION, ALIGNMENT, MARKET_BACKDROP, ROOM, STOP_PLACEMENT;
  - LIQUIDITY_SWEEP, STRUCTURE_SHIFT, ACCEPTANCE (daily-bar version), RELATIVE_STRENGTH, POSITIONING.
- Code the trade verdict in `map_read`.
- Add screener columns for LOCATION, ROOM and MARKET_BACKDROP.
- Pre-register the situation tests and the usefulness test. Example: on the put-retest plan's history, do shorts at HTF demand or with no room do worse?
- **Done when:** the verdict appears everywhere `map_read` is wired, and the pre-registrations are committed.

### S8. Run the tests

- Run the S4 and S7 pre-registered tests. Report each family and each situation as pass or fail.
- Promote passing items to filters, in the screener and as `pick_structure` flags that affect ranking. Failed items stay shown, labelled "failed its test".
- **Done when:** the results are committed, and the filters reflect only what passed.

### S9. P5: map events inside a trade

- Wire map events into the position manager and the trade watcher for open positions, as Telegram alerts:
  - entering an opposing strong zone;
  - a sweep;
  - a CHoCH against the position;
  - the backdrop flipping.
- Any exit rule built on these needs its own pre-registration and the user's go-ahead.
- **Done when:** alerts fire on a replayed past trade (HDFCBANK, SUPREMEIND), and the code is deployed.

### Gate: resume trading?

This is the user's decision, made after S8, on the evidence. It is not automatic.

## Tracker

- [ ] S1 techno-funda close-out
- [ ] S2 P0 wiring
- [ ] S3 zone test (frozen)
- [ ] S4 golden set + definitions + pre-registration
- [ ] S5 L1 stock HTF + SMC
- [ ] S6 L0 market map + brief
- [ ] S6b layer F: fundamentals + ownership
- [ ] S7 situations + verdict + pre-registrations
- [ ] S8 tests run, filters promoted
- [ ] S9 in-trade map events

## Changes to the plan

_Dated notes on anything a session changed for later sessions._
