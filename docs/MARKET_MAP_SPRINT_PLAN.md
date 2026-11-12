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
- **Before the runner exists,** commit amendment 1 to the pre-registration: a macro-context split, reported only, not part of pass or fail.
  - Rejection rate by the stock's Weinstein stage on the day (`core/vault/stages.py`: stage 2 = HTF up, stage 4 = HTF down), crossed with support or resistance.
  - Each cell is labelled "with the HTF trend" (support in an uptrend, resistance in a downtrend) or "against it".
  - The pass criteria and zone definitions stay frozen.
- Write the runner for `docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md`: point-in-time maps, the event and outcome rules, placebo and weak-zone controls, and the session bootstrap.
- Run it and report pass or fail on criteria 1-5. No re-tuning.
- If the history isn't deep enough for about 300 events: report that and stop. Don't shorten the test.
- **Done when:** the results doc is committed and the user has the verdict.

### S2b. Screens: the stock map page, the trade check, the map on Ideas

Spec: `docs/MARKET_MAP_SCREENS.md` (screens 1-6, with mockups). This session builds screens 1, 2 and 4; screens 3, 5 and 6 are built inside S7, S6 and S9.

- **API:** `GET /map/{symbol}` returns `map_read` for a symbol; `POST /map/{symbol}/check` returns it for a trade (side, entry, stop, target).
  - Both are read-only. A model never feeds them; the numbers come from code.
  - Add the new prefix to the VM's nginx allowlist by hand: deploy doesn't sync it.
- **Stock map page (`#/map/SYMBOL`):**
  - a vertical price ladder: zones as bands (strong/weak, families), the current price, distances in ATR and %;
  - a test-status badge on every element (untested, passed, failed its test);
  - a banner naming what isn't built yet ("lookback 100 days; HTF layer from S5"), shown until S5 lands.
- **Trade check panel** on the same page: side, entry, stop, target in; R, ROOM to the first obstacle, stop placement and flags out. Advisory, places nothing.
- **Ideas page:** each idea shows its frozen map read.
- Every screen states which layers it shows and which aren't built yet. A screen never presents an untested line as a signal.
- **Done when:** on the VM's cockpit, `#/map/HDFCBANK` draws the ladder, the trade check flags the 10-23 short's stop inside the 688.77–693 zone (on the 11-02 map), and the Ideas page shows a logged idea's frozen read.

### S4. Definitions, golden set and pre-registration (with the user)

Order changed by the user 2026-11-04: **the rules come from the concepts, not from the marks.**

- Write `docs/MARKET_MAP_DEFINITIONS.md` v1 from the concepts already agreed (design §2b, §3; Ochoa, Dalton, SMC): exact, codeable rules for
  - HTF swing structure, multi-year demand and supply zones;
  - SMC (BOS, CHoCH, order block, EQH/EQL, strong and weak highs/lows, premium and discount);
  - weekly, monthly, quarterly and yearly CPR, two-period relationships, Camarilla, money zone;
  - long composite profile;
  - families, with overlapping ideas counted as one (poor highs/lows = EQH/EQL).
- v1 carries its own fidelity test (recall and precision against the marks, pass criteria fixed) and is frozen **before any chart is seen**.
- **Golden set:** the user marks 10-20 charts without reading v1 (template `docs/golden_set/README.md`), cropped of any account panels, and hands them over after v1 is committed. HDFCBANK and SUPREMEIND were discussed before v1, so they illustrate and are never scored.
- Pre-register the signal test of the HTF and SMC layers (zones turn price versus placebo, each family separately) **before any L1 code**. S3's lessons apply: placebo feasibility on counts first, width-matched controls.
- **Done when:** definitions v1 (with its fidelity test) and the signal pre-registration are committed and approved by the user. Scoring the golden set needs L1 code, so the fidelity verdict is part of S5's done.

### S5. P2: L1, the stock's higher-timeframe layer

- **Daily data refresh (VM job, after the close):** append the day's bhavcopy and corporate actions, and keep the adjusted series current (design §7). L1 and the universe ranking read it.
- **Universe:** the top 500 NSE EQ stocks by 60-day median traded value, refreshed daily; any other symbol on demand, labelled "outside the tested universe" (design §3 L1).
- Build weekly and monthly bars from the adjusted daily bhavcopy, reusing `core/techno_funda/prices.py` adjustment.
- Code exactly per the definitions doc:
  - swing structure and multi-year zones;
  - the SMC layer;
  - quarterly and yearly pivots;
  - weekly and monthly CPR with Camarilla;
  - long composite profile from daily bars, labelled as an approximation;
  - period profiles, both kinds: Ochoa's price-based money zone (time at price) and the volume profile (VPOC), with their virgin levels.
- **Joining L1 and L2** (design §3): L1 owns the week, month, quarter and year pivots, and L2 keeps only the daily ones; every level carries its price source; check that Fyers and bhavcopy agree on recent closes, and flag pre-split L2 levels.
- **The new map becomes the map (slice 7; replaces "price map v2", user 2026-11-08):** the L1 read built in slices 2–6 is what `map_read` leads with and what the stock map page draws. The old 100-day price map is retired from the screen; its 2026-11-04 FAIL stays in the record, attached to it. The new map is labelled "untested" until the §9 fidelity test and the S8 tests run. Slice 7 also:
  - draws the daily structure beside the weekly and monthly (state, last BOS/CHoCH, protected and weak levels), as display only: adding daily levels to the strong-zone rule is a definitions change (v2), not done here;
  - reports map events as they happen: BOS and CHoCH per timeframe, and sweeps. A sweep of an EQH/EQL is v1 §3.4's `LIQUIDITY_SWEEP`. A sweep of a weak or protected high/low (design §4's table) is shown but labelled "definition not frozen" until S7 freezes it;
  - keeps L2 to the daily pivots and the 5-minute profile (definitions §4 naked-level window, age recorded, no 20-session cutoff), from the full 5-minute history rather than 99 days.
- Unit tests on synthetic fixtures for every rule. The golden set is scored by the §9 fidelity test, never used as a fitting target.
- Extend `map_read` with L1, so it's used the day it lands.
- **Done when:** the definitions v1 fidelity test (§9) has run on the golden set and its verdict is reported (a fail is reported, then v2 per §9), and `levels HDFCBANK` shows the 640-840 base and the strong low near 665 as at 2026-10-23 (an illustration check, not a score: those levels were known before v1).

### S6. P3: L0, the market map

- **Index OHLC history:**
  - fetch NSE `ind_close_all_DDMMYYYY.csv` for all indices (broad and sector) from 2010;
  - cross-check sample dates with TradingView.
- Run the same L1 and L2 engine on the indices.
- **Breadth from the bhavcopy:** share above the 50- and 200-day averages, advance/decline, 52-week new highs minus new lows.
- **Sector rotation:** relative strength against the Nifty 500 on 13 and 52 weeks, with quadrants.
- **Positioning:** NSE participant-wise OI (FII, DII, Pro, Client) and FII/DII cash flows. Context only.
- **Pre-market brief** (Telegram and cockpit): market first, then sectors, then the watchlist.
- **Screen 5 (market page, `#/market`):** indices, breadth, sector quadrants, positioning as context; the same content as the brief.
- On the stock map page, the market backdrop strip sits above the ladder.
- **Done when:** the brief runs on the VM, `map_read` includes the market backdrop, and `#/market` shows it.

### S6b. Layer F: fundamentals and ownership

- Reuse the techno-funda point-in-time fundamentals: growth, OPM and their trend.
- Fetch NSE quarterly shareholding patterns (promoter, FII, MF, insurance, retail; change on the quarter) and index weights.
- Add the results date (event risk) from NSE board meetings.
- **Results-season refresh (VM job):** fetch new filings and parse their XBRL, storing each figure with its publication date (design §7). Log Piotroski inputs from now on, where filed (not backtestable before about 2023).
- Extend `map_read` with layer F.
- How much of it filters depends on the S1 techno-funda verdict and the S8 tests.
- The stock map page gets a layer-F panel (growth, OPM, ownership trend, next results date).
- **Done when:** `map_read HDFCBANK` shows growth, OPM, the FII/MF holding trend and the next results date, all as of the day.

### S7. P4: situations and the trade verdict

- Code the situation vocabulary (design section 4):
  - LOCATION, ALIGNMENT, MARKET_BACKDROP, ROOM, STOP_PLACEMENT;
  - LIQUIDITY_SWEEP, STRUCTURE_SHIFT, ACCEPTANCE (daily-bar version), RELATIVE_STRENGTH, POSITIONING.
- Code the trade verdict in `map_read`.
- Add screener columns for LOCATION, ROOM and MARKET_BACKDROP.
- Pre-register the situation tests and the usefulness test. Example: on the put-retest plan's history, do shorts at HTF demand or with no room do worse?
- **Screen 3 (map columns on Picks):** LOCATION, ROOM and MARKET_BACKDROP per candidate, each with its test status.
- The trade check panel shows the full verdict (situations per timeframe).
- **Done when:** the verdict appears everywhere `map_read` is wired, including the Picks columns and the trade check, and the pre-registrations are committed.

### S8. Run the tests

- Run the S4 and S7 pre-registered tests. Report each family and each situation as pass or fail.
- **Added 2026-11-08 (user), each pre-registered before it runs:**
  - **History window:** the same zone rule built from 99 days of 5-minute data vs the full history since 2017-12, both against width-matched placebos. Answers whether the 2026-11-04 FAIL came from the short window or from the zone idea.
  - **Sweep then shift:** a weak low (or EQL) swept inside a strong HTF zone, followed by a daily CHoCH back the other way within a window fixed in the pre-registration, and the mirror for highs. Does price move in the CHoCH direction more often than after a plain break? HDFCBANK and SUPREMEIND (2026-10) prompted this and are excluded from scoring.
- Promote passing items to filters, in the screener and as `pick_structure` flags that affect ranking. Failed items stay shown, labelled "failed its test".
- **Done when:** the results are committed, and the filters reflect only what passed.

### S9. P5: map events inside a trade

- Wire map events into the position manager and the trade watcher for open positions, as Telegram alerts:
  - entering an opposing strong zone;
  - a sweep;
  - a CHoCH against the position;
  - the backdrop flipping.
- L1 levels are on cash prices: shift them by the current futures basis before a futures position's alert uses them, and show the shift (design §3).
- Any exit rule built on these needs its own pre-registration and the user's go-ahead.
- **Screen 6 (in-trade card):** an open position drawn against its zones, with the map events as they fire. Alerts only, no exit controls.
- **Done when:** alerts fire on a replayed past trade (HDFCBANK, SUPREMEIND), the in-trade card shows them, and the code is deployed.

### S10. Re-look at failed candidates with HTF conditioning

Re-testing about 20 failed strategies under several conditions makes a pass by luck likely, so
the discipline here is stricter than for a fresh candidate.

- **The list is fixed by a rule, before looking at any conditioned result.**
  - Candidates that failed on direction or edge, not on data or liquidity.
  - Each needs at least 200 trades in its original test.
  - Only HTF conditions that S8 showed carry information are used.
- **One pre-registration covers them all,** with:
  - a multiple-testing correction across every candidate × condition (Bonferroni or Holm);
  - a held-out period that none of the original tests touched;
  - pass bars at least as strict as the originals.
- **Each candidate's original FAIL stays on record.** A conditioned pass is a new, narrower strategy, not a reversal of the old verdict.
- **Done when:** the results are committed and each candidate is reported pass or fail, corrected.

### Later: intraday on the same engine (not in this sprint)

- Intraday reads use `map_read` with intraday as-of times and **inherit the swing bias**: macro sets the direction, micro sets the location.
- Every intraday test is pre-registered with the HTF split.
- The failed intraday candidates (ORB 18 and others) can be re-looked at with HTF-structure conditioning, as new pre-registered tests.

### Gate: resume trading?

This is the user's decision, made after S8, on the evidence. It is not automatic.

## Tracker

- [x] S1 techno-funda close-out: **STOP at D4** (coverage 43.8% in 2019, 57.3% in 2020, bar 70%); D1/D3/D5 pass, D2 reported. Backtest not run, nothing substituted. `docs/TECHNO_FUNDA_DATA_GATES.md`, 1e332e2
- [x] S2 P0 wiring: deployed 1668cd5 + bfbcb1c. On the VM, `levels HDFCBANK` leads with the map read (11-03 close 725.5: inside strong zone 725–728.73, below 712.13–718.25, above 731.5–736, all untested). An idea with no map read is refused. bfbcb1c fixes the read being taken at a reused map file's older close.
- [x] S3 zone test: **FAIL** (fd2d5e6). Strong zones 60.1% rejection vs placebo 61.1% (−1.1 pp, CI [−4.2, +2.1]), 22,620 events, 218 stocks; criteria 1-3 fail. Criterion 4's pass is band-width geometry. The HTF split gives no lead. map_read now labels these zones "failed its test" (af01025, deployed). Amendments 1-2 committed before any outcome (2 = the user's placebo rule C).
- [ ] S2b screens: built and deployed 4ddbd23, nginx `/map` added by hand. On the VM, 2 of 3 done checks pass: `GET /map/HDFCBANK` serves the 11-02 map (27 zones, 6 strong, all "failed its test", banner layers), and the trade check on the 10-23 short (678 / stop 690 / target 660) flags "stop 690 is inside the strong zone 688.77–693". **Open:** the Ideas page shows a frozen read only for ideas logged since 11-03, and none has been logged on the VM yet (verified locally on a synthetic idea). Tick when the first real idea is logged and shows its read.
- [x] S4 definitions + signal pre-registration: **v1 FROZEN 11-05** (0067700; Ochoa Ch. 3–11 checked, 4bc7f17..bb65366, user's R3/S3 choice 39c089c). Signal pre-registration **APPROVED 11-06** (`docs/MARKET_MAP_SIGNAL_PREREG_2026-11-05.md`): 9 hypotheses, mirrored width-matched placebos, side-balanced, Holm. Golden-set charts still to come: filed, not scored, until S5.
- [ ] S5 L1 stock HTF + SMC
  - [x] Slice 1, data (72ceb28, 7860f18; deployed 11-07):
    - **Store:** `core/market_map/l1_store.py`, one CSV per stock in `~/.quantos/l1_store` on the VM. It holds 3,793 stocks from 2010, adjusted when read. Its adjusted closes and segments match the techno-funda panel exactly on 300 sampled stocks.
    - **Refresh:** `quantos-l1-refresh.timer` runs at 14:00 UTC (19:30 IST) on weekdays and is enabled. Each run adds the day's NSE prices, the PR-bundle splits and bonuses, the renames, and the top 500, which now leaves out NSE's ETF list.
    - **First run:** it added 26 Oct to 6 Nov, 29 corporate actions (24 Jun to 6 Nov) and 2 renames.
    - **Fyers check:** 494 of the top 500 agree. The 6 that don't (VEDL, HEGAM, GUJENERGY, HCC, ADANIENT, GENUSPOWER) are demergers and rights issues, which v1 §0 doesn't adjust (splits and bonuses only).
  - [x] Slice 2, structure (11-07): `core/market_map/structure.py`, definitions §0, §1, §2, §7. ISO-week and calendar-month bars from completed periods only. Swings and the 1-ATR zig-zag run bar by bar, so a test checks that events never change when later bars arrive. BOS/CHoCH, protected and weak levels, age, M/W/D alignment. The choices v1 leaves open are fixed in the module docstring before any golden-set chart. `map_read` adds `l1` (labelled untested) and its lines. Top-500 sweep: 0 errors, about 0.3 s a stock; 25 read from their latest segment. Monthly is `none` only for young listings (24 to 37 months).
    - HDFCBANK at 2026-10-23 (illustration, not scored): M down since the March 2026 CHoCH below 812.15, protected high 1020.5; W down, protected high 843, weak low 681.9; D up since the 15 Sep CHoCH at 716.5, protected low 681.9. Not aligned: D conflicts.
  - [x] Slice 3, zones (11-07): `core/market_map/zones.py`, definitions §3.1 to §3.5 on W and M. Demand and supply bases, multi-touch levels (W), order blocks from each BOS/CHoCH's protected bar, EQH/EQL with swept or broken status, premium/discount per timeframe. The choices v1 leaves open are fixed in the module docstring. `map_read`'s L1 lines add the nearest zones below and above price and those around it, labelled untested. Sweep of 273 random stocks: 0 errors, 0.37 s a stock, median 27 zones.
    - **HDFCBANK, against the done check (illustration, not scored):** v1 §3.1 does **not** make the 640–840 base. A §3.1 base is 1 to 6 bars each within 1 ATR, and the 2021–24 range was many wide months. The range shows instead as weekly multi-touch levels at 639, 682, 707, 730, 768, 780, 820, 835 and 861, plus an active weekly EQL at 681.77 (swing lows in 2022, 2024 and 2026). v1 is not changed for this; slice 6's families decide whether `levels` shows the range.
  - [x] Slice 4, period pivots (11-08): `core/market_map/pivots.py`, definitions §4 for week, month, quarter (labelled not Ochoa) and year.
    - **Levels:** floor pivots to R4/S4, CPR and Camarilla to H5/L5, the hidden layers only when the Camarilla width reads wide, and the previous period's high and low.
    - **Readings:** width % and the percentile among the last 20 periods (at least 8), the two-period relationship with Ochoa's bias for CPR and for Camarilla L3–H3, the close half, the close against the CPR in force, and the CPR trend run (W, M).
    - **Map levels:** each level carries `in_map` per §4 (week and quarter R3/R4/S3/S4, H5/L5 and the hidden layers are shown only).
    - **Left for slice 5:** money zone and VPOC, their relationships and virgin levels.
    - HDFCBANK's September 2026 monthly pivots were checked by hand (P 713.3, CPR 711–715.6, H3 727.24). Sweep of 264 random stocks: 0 errors, 0.39 s a stock. The week to 23 Oct read weekly-wide on 60% of stocks (a market-wide one-way week); four other weeks give a normal mix.
  - [x] Slice 5a, profiles from daily bars (11-08): `core/market_map/profiles.py`.
    - **Per period (month, quarter and year, the last two labelled not Ochoa):** the money zone (one TPO per daily bar, v1's own adaptation) and the volume profile (VPOC). Both carry width, percentile and the two-period relationship; the month also gets the VPOC relationship and its unchanged run.
    - **Virgin levels:** POC, VAH and VAL of both kinds, retired by a later bar that spans them, with age, distance and Ochoa's two `watch` flags.
    - **Long profiles (250 and 750 sessions), labelled approximation:** POC and value area, HVN shelves, and LVNs between shelves.
    - **Checks:** the fast profile matches `price_map.levels.profile` exactly. Sweep of 261 stocks: 0 errors, 0.78 s a stock, the read's JSON 46 KB median (87 max).
  - [x] Slice 5b, weekly profiles from 5-minute bars (11-08; backfill complete):
    - **Store:** `core/market_map/m5_store.py`, `m5/<SYM>/<YEAR>.csv.gz` under the L1 store. `scripts/fetch_m5.py` backfills from 2017-12-01 in 99-day requests (resumable), and the 19:30 refresh (step 7) backfills new symbols and tops up daily.
    - **Fyers sends 5-minute history already split-adjusted** up to the fetch day. The first read adjusted it twice (HDFCBANK showed 2,471 weekly virgin levels), which was caught and fixed in bc1a1d5 before any read was used. Only actions after each symbol's fetch basis are applied now.
    - **Weekly money zone:** TPOs from 30-minute brackets of 5-minute bars, as in the book. A week needs 5-minute bars for every session. The weekly VPOC, relationships and virgin levels are as for the month.
    - **Backfill (started 11-08 01:20 IST):** top 500 plus HDFCBANK and SUPREMEIND, ~15 s and ~2.3 MB a stock. The first pass lost about 20 symbols to `no_data` before listing (fixed in 31afa99) and 3 to one minute over Fyers' rate limit. A second pass starts automatically when the first ends.
    - **Second pass (11-08):** 202 of 217 backfilled, 15 failed, all on Fyers' rate limit (-360). A third pass collects them.
    - **Third pass (11-08, after a token refresh):** 15 of 15, 0 failed. All 500 symbols (the top 500 plus HDFCBANK and SUPREMEIND) are backfilled, 746 MB on the VM.
    - **Tick when:** a pass reports 0 failures.
  - [x] Slice 6, HTF zones (11-08): `core/market_map/htf.py`, definitions §6 and §6.1.
    - **Elements:** every L1 element as a point (a band contributes its two edges), with tf, family, kind and period.
    - **Clustering:** the existing map's rule at 0.3 ATR(W). Strong = 2 or more families.
    - **Hot zones:** DPZ and MTZ clusters of §4 levels, and GPZs, recorded beside the families.
    - **L1/L2 join in `map_read`:** price sources named; the Fyers close is checked against the bhavcopy close; a split or bonus inside L2's 365-day lookback is flagged. Moving L2's week and month pivots out of L2 is part of price map v2 (slice 7). The map page's banner says L1 is in the levels read and not yet drawn.
    - **Finding (reported, rule unchanged):** v1's strong flag barely selects. Across 79 stocks the median share of HTF zones that are strong is 73% (p10 47%, p90 88%), with a median of 11 strong zones within 3 ATR(W) of price, which is close to continuous cover. HDFCBANK: 50 of 59. The §9 fidelity test and the S8 signal test decide whether that matters; any change is v2.
    - **HDFCBANK done check, as at 2026-10-23 (illustration):** "strong low near 665": yes, a 5-family strong zone at 669–682.5 (22 members, including the active weekly EQL 681.77) and one at 652–664.4. "640–840 base": **not as one zone**. v1 shows the range as an unbroken ladder of strong 10–15-point zones from 600 to 887. The wording of this check is the user's call.
  - [x] Slice 7: the new map becomes the map (11-08)
    - [x] 7a (11-08): `map_read` leads with the L1 map in the same output shape (inside/below/above, the trade check, the ladder of every HTF zone), status untested. The old 100-day map is only a fallback for stocks outside the L1 store, labelled with its FAIL. The map page draws the L1 ladder in amber (untested), a structure card (M/W/D state, last BOS/CHoCH, protected and weak levels, last sweep) and a banner per map. The engine records sweeps of the weak level (a wick beyond it that closes back inside), display only, labelled "definition not frozen". The `levels` tool, `pick_structure`, `qorder` and CLAUDE.md wording updated.
    - [x] 7b (11-08, 297367c): `core/market_map/daily.py`, L2's daily layer. Daily floor pivots, CPR with Ochoa's absolute daily width reading and the two-day relationship, Camarilla H3/H4/L3/L4; a money zone (30-minute brackets) and a volume profile per session from the full 5-minute history (2,213 sessions since 2017-12 on the stocks checked); virgin session levels by §4's rule, no age cutoff. Definitions v1 §8 keeps these out of the v1 map, so they are shown beside the HTF zones (`levels` read and a map-page card) and never clustered or counted as a family. Untested.
      - **Observations (reported, no change):** the nearest virgin levels are usually the last session's own, which no later bar has had the chance to span; 181–255 virgin session levels per stock, most far from price. A read takes 5.4–6.4 s on the VM (was ~4 s).
    - **Not changed:** the position manager's in-trade zone alert still reads the old map files (`~/.quantos/price_maps`). It is alerts only and a live job; moving it to the L1 map is S9 (in-trade map events).
  - [ ] Slice 8: fidelity test (needs the golden-set charts)
    - [ ] Round 1 (user, 11-08): 15 random engine reads reviewed by the user, the user's model judge and Fable before the fidelity test; protocol pre-registered in `docs/MARKET_MAP_REVIEW_ROUND1.md`. Nothing built changes during the round. Fable done 11-09 (`docs/review_round1/findings_fable.md`): 0/525 items break v1, 81% match the chart, all 15 "partly"; 2 small code bugs (bucket-edge float, unfiltered bad 5-min bars) held for approval; main v2 gaps: stale structure states, non-selective strong flag, equal highs never swings, sweeps unnamed. User's R01 KEI + R02 DMART in 11-11 (Gemini-written; `docs/review_round1/findings_round1.md`): 70/70 Chart Y, no new code bug or gap; its W-structure flags fall under gap 1, now raised by all three reviewers; forward walk-throughs filed as S8 notes (`s8_forward_notes.md`). 11-11 user: fix both bugs (cd98683; 80 bad 5-min rows of 64.1M, 34 stocks) and put all six gaps in v2 (`docs/MARKET_MAP_DEFINITIONS_V2.md`, committed a46b218 before the code; code 0a819d7, G2 rev 1 f76482f after the first regeneration showed band chaining, tie rule e8aee97). The 15 reads regenerated under v2 (`docs/review_round1/v2/`, changes in `changes.md`; strong share median 78% -> 53%). v2 NOT deployed to the VM (the deploy was blocked by a permission check; live map_read still runs v1). 11-13 user: further review rounds skipped (they check drawing, not edge); the v2 hand review is closed.
    - [x] ~~Round 2: the user's golden-set charts, scored by §9 as pre-registered~~ SKIPPED by the user 2026-11-13. The map stays "untested" until S8.
    - [ ] v3 (user, 11-13): zones still tile the range under v2. Definitions `docs/MARKET_MAP_DEFINITIONS_V3.md`, committed before any code, with 4 changes: (H1) zones from price action only, pivots and volume become a levels layer; (H2) mitigation, removed on a daily close through or on the second touch; (H3) strong = fresh, at a BOS/CHoCH, with a levels-layer confluence; (H4) coverage reported, not targeted. 11-13 user added (H5) fair-value gaps on W/M (ba6825c), before code. Code f7bfa2b. 15 reads regenerated (`docs/review_round1/v3/`, `changes.md`), medians v2 → v3: coverage of price ± 3 ATR(W) 87.9% → 38.0%, strong coverage 74.2% → 13.5%, near strong zones 5 → 1, strong share 53% → 36%. Finding: H3's confluence condition selects nothing (765/766 zones pass); fresh + at-a-break do all the selecting. Next: side-by-side charts against the SMC indicator on 3–4 stocks, deploy, then S8.
- [ ] S6 L0 market map + brief
- [ ] S6b layer F: fundamentals + ownership
- [ ] S7 situations + verdict + pre-registrations
- [ ] S8 tests run, filters promoted
- [ ] S9 in-trade map events
- [ ] S10 re-look failed candidates with HTF conditioning (corrected for multiple tests)

## Changes to the plan

_Dated notes on anything a session changed for later sessions._

- **2026-11-08 (user, after slice 6):**
  - **Slice 7 rewritten:** the L1 map replaces the old 100-day map on screen instead of patching it. The old map's 99-day 5-minute window came from reading Fyers' per-request limit as a history limit; Fyers holds 5-minute bars from 2017-12. Its swings used a year of daily bars and its pivots were period-based, so the window covered only the volume part.
  - **SMC is the core of the map; Ochoa's hot zones are a side record.** Structure, imbalance and liquidity are three of the five families; hot zones never make a zone strong.
  - **Illustrations (not scored).** The engine matches LuxAlgo SMC on the user's daily charts:
    - **HDFCBANK:** weekly protected high 843.0, weak low 669.2, daily CHoCH up at 749.3 on 11-05. As at 10-23 the weak low was 681.9. Price closed below it on 10-27 (daily CHoCH down), swept to 669.2 inside the 669–682.5 strong zone, and reversed.
    - **SUPREMEIND:** monthly EQL 3140 (Dec 2025, Jul 2026) was the monthly and weekly weak low. It was swept on 10-30 (low 3127, a weekly BOS down at 3270), bounced to 3300, and made a new low at 3078.5 on 11-06. There was no daily CHoCH up: the daily protected high stays 3653.9. Price around 3200 sat inside the 3135–3227.6 strong zone (structure, liquidity, volume, pivot), one of five stacked strong zones from 3035 to 3540 (2.3 ATR(W)), which is the non-selectivity finding again.
    - Both prompted the S8 "sweep then shift" test and are excluded from its scoring.

- **2026-11-07 (S5 start, intraday data for the weekly profile):**
  - The weekly money zone and volume profile (definitions §4) use Fyers 5-minute bars, fetched on the VM in chunks of up to 100 days. Fyers' "100 days" is the limit **per request**, not the depth. Probed on HDFCBANK and SUPREMEIND: full weeks (375 bars) back to January 2018. Intraday history starts on **2017-12-01**; earlier start dates are refused (code −50).
  - So weekly profiles exist from December 2017, and the definitions are unchanged (they name 5-minute bars). Weekly profile records start there; month, quarter and year profiles come from daily bhavcopy bars from 2010.
  - Also checked, not used:
    - **TradingView** caps intraday history at about 5,900 bars: 30-minute bars back to 2025-01-01, 5-minute bars to late July 2026. It is PC-only.
    - **Breeze** has no history client in the repo.
  - VM memory is 956 MB, so the 1.7 GB techno-funda panel can't load there. L1 reads a per-symbol store (slice 1).

- **2026-11-06 (user, closing S4):**
  - **L1 universe:** the top 500 by traded value (the same as the signal test), plus indices (S6), plus any symbol on demand, labelled "outside the tested universe".
  - **Joining L1 and L2:** L1 owns the W/M/Q/Y pivots and L2 keeps the daily ones (part of price map v2); every level carries its price source; L1 levels are shifted by the futures basis for futures positions (S9).
  - **Data:** nothing refreshed the bhavcopy or fundamentals caches. A daily price refresh goes into S5 and a results-season fundamentals refresh into S6b.
  - **Techno-funda (outside this sprint):** the next step is a re-scoped 2021–2026 backtest pre-registration. No returns have been computed, so this is not a re-tune of a failed test. A paper scanner, on the Darvas pattern, follows only if the backtest passes. Real money stays the user's call.
  - **Darvas and 18b** are not changed by the map while they are being measured. A map-filtered variant would run as a separate, pre-registered paper variant beside the original.

- **2026-11-05 (S4, Ch. 9–11 checked):** the whole book is now checked. Seven commits (4bc7f17..bb65366):
  - **Periods:** Ochoa's are weekly (swing), monthly (position and swing) and yearly (investors). The quarter is not his; v1 keeps it, labelled. The monthly money zone has no construction rule in the book, so the M/Q/Y one-TPO-per-day rule stays v1's own.
  - **Width:** long-period width is read relative to earlier periods. The percentile needs at least 8 previous periods, so yearly readings start in 2019.
  - **Correction, close against the CPR:** the close against the CPR a period creates only says which half of the range it closed in (algebra, checked numerically). The CPR trend uses the CPR in force. The next open goes to S7 (ACCEPTANCE).
  - **Correction, Camarilla hidden layers:** H1/H2/L1/L2 are shown when the period's width reads wide (Ch. 8; Ch. 9 Fig. 9.12).
  - **Added:** the weekly and monthly VPOC relationship; the previous period's high and low (pivot family, because R1 − H = CPR width).
  - **Added, Ochoa's hot zones (DPZ, GPZ, MTZ):** recorded beside the families, not strong zones. A same-period H3/L3 GPZ is the close in the bottom or top 22.5% of the range. **S4's signal pre-registration should test the hot zones as Ochoa defines them, and the GPZ against that close-position control.**
  - **Placement:** the flight plan is the S6 brief. Acceptance, the trend filter and triggers go to S7; trailing stops to S9. Sizing up at hot zones and pivot-responsive watch lists are not adopted.

- **2026-11-05 (S4, still open):** Ochoa Ch. 9 (higher timeframe analysis: monthly, quarterly, yearly) and Ch. 10–11 (the trading plan) are to come from the user and must be checked before v1 is frozen. The user is also preparing the 10–20 golden-set charts.
- **2026-11-05 (S4, book check complete):** every Ochoa item in definitions §4 is now checked against the book (Ch. 3–8, Appendices A and B). Ch. 5 confirms the floor pivots, which match the existing map, and adds R4/S4. Ch. 3 confirms 30-minute TPOs and the POC tie rule; it gives no value-area growth procedure, so v1 keeps the Market Profile convention. Appendix B shows the Pivot Range Histogram is raw width %, with 0.25 and 0.75 as absolute daily thresholds. v1 applies it as written to daily CPRs (intraday layer); for week and longer, v1 uses its own percentile rule, labelled as not Ochoa's. Appendix A's touch counts are frequencies with no placebo, so they don't substitute for the S8 tests.

- **2026-11-05 (user, S4):** Ochoa's Money Zone is price-based (time at price); QuantOS had only volume-based profiles. The user chose to follow his price-based method and keep the volume one too. Definitions §4 now carries both, as one family. S5 builds both for L1 and adds them to the L2 price map as v2. The 11-04 FAIL stays on v1, and v2 is untested until its own test. Ch. 3, Ch. 5 and Appendix B of the book are still to be checked; the TPO conventions (30-minute brackets, the tie rule, the growth rule) may change when Ch. 3 is read.

- **2026-11-04 (user, S4):** the definitions come from the concepts and are frozen before the golden set is seen; the golden set tests them (fidelity, pre-registered in the definitions §9) and is never used to fit them. A miss leads to v2, scored on fresh charts. HDFCBANK and SUPREMEIND are unscored (already discussed). S5's done gains the fidelity verdict.

- **2026-11-04 (S2b):** the map page reads at the live Fyers price, falling back to the map's close (labelled). Weak zones carry "failed its test" too (they were S3's control and did worse). `map_read(zones=True)` returns the ladder with per-zone distances and `LAYERS` (shown/missing); later layers (S5, S6, S6b) update `LAYERS` so the banner shrinks as they land.

- **2026-11-04 (S3):** the L2 strong zones (the 100-day price map) failed. For later sessions:
  - The zones stay on the map as markers, labelled "failed its test". No alert, trigger or filter is built on them. The S2b screens draw them in the failed style, not the untested one.
  - S4's pre-registration covers the HTF/SMC zones as a **new definition** with its own placebo test. Two lessons from S3 apply:
    - check placebo feasibility on counts before freezing the clearance rule;
    - width-match every control, since a wider band rejects more often by construction (rejection is measured from the near edge, a break from the far edge).
  - S10: no HTF condition came out of S3's split; S10's conditions still come only from S8.

- **2026-11-04 (user):** screens added. S2b builds the stock map page, the trade check and the map on Ideas, after S3. The market page (S6), the Picks map columns (S7) and the in-trade card (S9) are part of those sessions' "done", so a screen never runs ahead of the layer it shows.

- **2026-11-03 (S2):** the HDFCBANK map from 11-02 shows **no strong zone below** 692.8. This is the gap the design names: 100-day lookback, slowest pivot monthly. The 640-840 base and the 665 strong low arrive with L1 in S5.
  - Until then, `map_read` reads "below: no strong zone" as "nothing within ~100 days", not "nothing there".
  - The idea log now needs a map read for every idea. With the Fyers token expired and no map file under 7 days old, ideas can't be logged. That is by design: refresh the token, or run `scripts/price_map.py SYMBOL`.
- **2026-11-03 (S1):** techno-funda stopped at gate D4, so there is no techno-funda verdict on fundamentals.
  - S6b: layer F is shown as context, labelled untested. No fundamentals filter can come from S1.
  - Point-in-time fundamentals are thin before 2021: 43,865 non-financial filings have no parsed figures. Any later test that uses layer F must start its sample in 2021, or first close that gap as a separate, user-approved data task.
