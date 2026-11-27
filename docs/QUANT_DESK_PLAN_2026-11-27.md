# QuantOS quant desk plan (2026-11-27)

Read at the start of any session about strategy or research, next to `docs/EXECUTION_PLAN_2026-11-19.md` (which it does not replace). Written by Claude at the user's request on 2026-11-27; the user reviews and amends it, and changes are committed with a dated note.

## 1. Mandate

The desk harvests **risk premia** and the **other side of documented flows** in NSE index and stock derivatives (NIFTY, BANKNIFTY, F&O stocks). It does **not** try to forecast NIFTY's direction from price.

- Research only until the user lifts the trading pause (2026-11-02). Nothing here changes capital, size or `dry_run`.
- Every order rule in CLAUDE.md stands: a model drafts, code checks, the user releases. Rule-driven exits are placed by code. No algo ever trades the son's account.

## 2. What the last ~25 tests taught us

| Family | Tests | Result |
|---|---|---|
| Direction from price (index) | ORB 18/18b, 10:10 breakout, Dow theory, trend-day filter, CCI/CPR, CCI-SMA cross, EMT VWAP, EMA8, candle confirm | Dead, or edge smaller than costs (`ORB_TIME_CONVENTION_RESULTS.md`, `BREAKOUT_1010_RESULTS.md`, `DOW_THEORY_TREND_RESULTS.md`, `TREND_DAY_FILTER_RESULTS.md`, `CCI_CPR_SIGNAL_AND_FILTERS_RESULTS_2026-11-07.md`, `EMT_VWAP_RESULTS.md`). 18b is still accruing toward its gate. |
| Timing short vol with vol signals | IV gate, term structure, skew, event proximity, vol spread | 5 for 5 FAIL (`VRP_IV_GATED_RESULTS.md`, `VOL_TERM_STRUCTURE_VALIDATION.md`, `VOL_SKEW_VALIDATION.md`, `EVENT_PROXIMITY_VALIDATION.md`, `VOL_SPREAD_VALIDATION.md`) |
| Unconditional weekly NIFTY short strangle | VRP 2023-26 | PF 1.03, Sharpe 0.09: thin (`VRP_BACKTEST_RESULTS.md`) |
| Map/zone levels vs placebo | 100-day zones, SMC order blocks 1H, bull-put follow-up | 3 for 3 no better than random levels (`NIFTY_SMC_OB_1H_RESULTS.md`, `NIFTY_SMC_OB_1H_BULLPUT_RESULTS.md`, price-map S3) |
| Momentum / trend stocks | Darvas variants, S8-3 rotation, S1 dual momentum, Alpha 50 rebuild (2 rounds) | Thin at best; the Alpha 50 ETF already gives the base (`ALPHA50_REBUILD_V2_RESULTS_2026-11-27.md`). Darvas ATR-stop and candidate 11 continue on paper under their own gates. |
| Relative value | Pairs v1/v2, PCA stat-arb, ML factor combination | FAIL (`PAIRS_TRADING_V2_RESULTS.md`, `STATARB_NIFTY50_RESULTS.md`, `ML_FACTOR_COMBINATION_RESULTS.md`) |
| Event drift (price) | Earnings gap drift, expiry-day effect | FAIL (`EARNINGS_GAP_DRIFT_GUTCHECK.md`, `EXPIRY_DAY_EFFECT_GUTCHECK_RESULTS.md`) |

**Rule:** no new test in a dead family without either a **new data source** or a **new structural reason** written in its pre-registration.

## 3. Data inventory

On disk (gitignored `data_cache/`):

- **NSE F&O bhavcopy, 2019-02-11 to now, ~1,900 days, every contract** (index and stock options, futures): EOD open/high/low/close/settle, OI, volume. Raw zips in `data_cache/nse_bhavcopy/raw`; the parser `core/options/vrp/bhavcopy.py` currently filters to NIFTY and needs widening. **The desk's main underused asset.**
- NSE equity bhavcopy 2015-2023 (split/bonus-adjusted loaders), and the L1 store (3,793 stocks plus NIFTY/BANKNIFTY index bars).
- Results broadcast timestamps: ~60,000 XBRL filings (`data_cache/pead_nse/`).
- Index closes: NIFTY 50/500 from 2015, NIFTY Alpha 50 from 2018-03 (`data_cache/indices/`).
- Corporate actions 2010-2026, symbol changes, sector lists, AMFI market-cap lists 2017-2023.
- Live minute option chains since 2026-09-30 (VM recorder): the only bid/ask history we have.

Missing, and what it limits:

- **No historical intraday option prices** (Fyers refuses expired contracts; `CANDIDATE15_OPTION_DATA_FEASIBILITY.md`). Anything intraday in options needs the recorder's own history.
- **No bid/ask before 2026-09-30.** Spreads in older tests are haircut estimates, calibrated from the recorder.
- EOD settles on thin stock-option strikes can be stale. Use traded contracts only (volume > 0), as the VRP addendum does.

## 4. The edge slate

Each edge runs in two phases:

- **Phase 1 measures the premium.** Descriptive statistics only, no trade rules, no P&L. It still gets a short pre-registration (what is measured, over what window, and the kill line).
- **Phase 2 trades it.** A separately pre-registered, defined-risk structure, written only if phase 1 clears its kill line.

### E3: overnight vs intraday (NIFTY/BANKNIFTY futures). First, cheapest

- **Who pays us:** holders demand a premium to carry overnight gap risk, documented in many markets. Whether India's is big enough after costs is the question.
- **Data:** near-month futures open/close from the F&O bhavcopy, 2019-26 (tradable prices, not the index print).
- **Phase 1:** mean and t-stat of close-to-open vs open-to-close returns, by year and by index, net of futures STT, charges and one tick of slippage per side.
- **Kill line:** net overnight mean ≤ 0, or a sign flip between 2019-22 and 2023-26.
- **Phase 2 (if alive):** a 1-lot buy-close/sell-open rule, with margin cost charged.
- **Capacity:** large. **Main risk:** costs. My prior is that they eat it. One day of work.

### E1: results-day vol (implied move vs realized). Largest sample

- **Who pays us:** retail buys stock options into results, so the straddle the evening before should price a larger move than the one that follows.
- **Data:** stock-option settles (bhavcopy), results timestamps (XBRL), and stock closes. Roughly 180 F&O stocks × 4 quarters × 7 years ≈ 3,000-4,000 events.
- **Phase 1:** implied move (ATM straddle ÷ spot at the last close before the broadcast; after-hours results use that day's close) vs the realized absolute close-to-close move. Report the ratio's distribution, by year and by market-cap tier.
- **Kill line:** median implied/realized ≤ 1.0 in either half, or the premium is smaller than the round-trip cost of the phase 2 structure at our recorded spreads.
- **Phase 2 (if alive):** a defined-risk iron fly sold at the close before results and closed at the next close; wings and sizing frozen in the pre-registration.
- **Capacity:** small per name, many names. **Main risk:** stock-option spreads, and pin/gap tails.

### E2: index vs stock vol (implied-correlation premium, dispersion). Hardest

- **Who pays us:** index options are where retail and hedgers crowd, so NIFTY implied vol should be rich relative to constituent vols and realized correlation.
- **Data:** NIFTY options plus options on its top constituents (bhavcopy), and stock closes for realized correlation.
- **Phase 1:** daily implied correlation (from index IV and weight-scaled constituent IVs, monthly tenor) vs subsequent realized correlation, 2019-26.
- **Kill line:** mean premium ≤ 0, or premium < 0 in either half.
- **Phase 2 (if alive):** monthly short NIFTY straddle vs long top-10 constituent straddles, vega-weighted, delta-hedged at EOD with futures.
- **Capacity:** moderate. **Main risk:** many legs × STT; margin. BANKNIFTY has monthlies only since Nov 2024, so the monthly tenor is the natural one.

## 5. Research standards

1. **Pre-register before any run**, signed off by the user. A failed test is reported as failed, never re-tuned in the same round.
2. **Multiple-testing tax.** ~25 trials are on record. A phase 2 pass also needs a **deflated Sharpe ratio** above 0 at 95%, counting every trial in this repo. The trial count is stated in each pre-registration.
3. **Costs at current rates:** 2026 STT (0.15% on option sell premium and on exercise intrinsic), `core/options/vrp/costs.py` for the rest, plus a spread haircut calibrated from the recorder's chains.
4. **Controls:** a placebo or random comparison wherever a level, date or event selects trades.
5. **Worked cases first**: 4-5 shown before any long or paid run.
6. **Commit results before reporting.** Results docs live in `docs/`, the trade-idea log via `scripts/trade_ideas.py`.

## 6. Risk framework (once anything passes phase 2)

- One **desk risk budget**, set by the user, with a maximum loss per strategy and for the desk. Defined-risk structures only: no naked short options.
- Correlation between live strategies checked before stacking. A new strategy enters at minimum size on paper first, then at real size only on the user's go-ahead.
- Orders through `core/orders/gateway.py`; exits by the position manager. A model never decides an exit.

## 7. Role of the maps

The v3 map is for **placing risk**: strikes, stops, hedge levels. It is not a source of edge unless v3 passes its own pre-registered test (map sprint, parked behind the execution plan). Sweeps are an execution detail on top of an edge, not an edge.

## 8. Sequence and tracker

| # | Item | Status | Prereg | Result |
|---|---|---|---|---|
| E3 | Overnight vs intraday, phase 1 | next | — | — |
| E1 | Results-day vol, phase 1 | after E3 | — | — |
| E2 | Implied-correlation premium, phase 1 | after E1 | — | — |
| — | Widen `bhavcopy.py` beyond NIFTY (BANKNIFTY, futures, stock options) | needed by E1/E2/E3 | — | — |

Parked (only when the user asks): MA cross run (`MA_CROSS_PREREG_2026-11-27.md`, code ready), Darvas exit pre-registration, map v3 test.
Due: NSE 2027 holiday list in December (else the CALENDAR fault fires on 2027-01-01).
