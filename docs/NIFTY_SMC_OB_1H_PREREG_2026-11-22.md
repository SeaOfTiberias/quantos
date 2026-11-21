# NIFTY 1H bullish SMC order block + session POC, ITM-2 calls: pre-registration (2026-11-22)

**Status: SIGNED OFF by the user 2026-11-22, committed before any data was fetched or evaluated.** From here it changes only by a dated amendment at the end, and never after a result is seen.

**Source:** the user's spec, "Strategy Specification: NIFTY 1H Bullish SMC Order Block + Session POC Options Strategy (v3)". It is copied verbatim to `docs/research/NIFTY_1H_SMC_OB_SPEC_V3.md`.

**Evidence that came with it:** the user's TradingView export, `NIFTY_1H_ATM_Call_Strategy_v3_..._2026-11-22.csv` saved as `backtest_results/SMC-OB-1H_TV_NSE_NIFTY_2026-11-22.csv` (sha256 c9fab18b…95cfae).
- It trades the **spot index**: 39 units, ₹80 commission per trade. It does not trade options.
- Over 2015-01 to 2026-07 it has 93 trades, +2,047 gross index points, 59% winners.
- Mean +22.0 points per trade (median 6.7); bootstrap 95% CI of the mean +2.0 to +41.8.
- 2026 so far: 4 trades, all losers (−₹19.0k).
- That export is the hypothesis's origin. It is not evidence for the options version.

**Plan rules this test runs under** (`docs/EXECUTION_PLAN_2026-11-19.md`): E1–E3 are ticked, so a new signal pre-registration is allowed; any pass must also pass a held-out confirmation period. Trading is paused: even a pass leads only to paper.

**Prior, stated before the run:**
- SMC zones (the v3 map's OB/FVG zones) and three intraday NIFTY-direction ideas (ORB 18, the trend-day filter, the 10:10 breakout) are already on the failed list.
- Back of the envelope:
  - Gain: an ITM-2 call (Δ ≈ 0.65) turns +22 spot points into ≈ +14 option points.
  - Decay: about 10–13 points per session at 7–8 DTE.
  - Friction: 2–4 points of spread and costs per round trip.
- **Expected result: FAIL.** The test is run to find out, not to confirm that.

---

## 1. Hypothesis

H1. Long ITM-2 NIFTY calls taken on the spec's frozen v3 rules earn a positive net return on premium per trade after costs, under the frozen option-pricing convention. They beat a daily-uptrend, time-matched placebo, in discovery and again in confirmation.

## 2. Data (fetched and hashed before the run)

**Fyers keeps a rolling 9-year intraday window.** Probed 2026-11-22: the first NIFTY 50 1H bar accepted is **2017-11-22 09:15 IST**. Every day of waiting loses a day of history, so the bars are fetched once and frozen. Each file below is cached under `~/.quantos/research/smc_ob_1h/`, with its sha256 entered in `docs/RESEARCH_DATA.md`, before any rule is evaluated.

| Series | Source | Span |
|---|---|---|
| NIFTY 50, 60-minute | Fyers `NSE:NIFTY50-INDEX`, resolution 60 (bars stamped 09:15, 10:15, …, 15:15; the last bar is 15 minutes long) | 2017-11-22 to 2026-11-20 |
| NIFTY 50, 5-minute | Fyers, resolution 5 (exit fills, and the hour-aligned grid in §4) | same |
| India VIX, 60-minute and 5-minute | Fyers `NSE:INDIAVIX-INDEX` | same |
| NIFTY 50, daily | `~/.quantos/index_bars/NIFTY.csv` (NSE index file, from 2012) | EMA warm-up from 2012 |
| Sessions | `core/reference/calendar.py` (observed to 2026-11-20) | — |

Days with fewer than 5 one-hour bars (Muhurat and special sessions) produce no signals. Their bars still advance open trades.

## 3. Periods

**The split is fixed by the data start and by the start of NIFTY weekly options.**
- Fyers' intraday data starts 2017-11-22.
- NIFTY weekly options began trading on **2019-02-11** (first expiry Thursday 2019-02-14). Before that, NIFTY had only monthly contracts.
- **Pre-weekly entries are not scored (user, 2026-11-22, decided before any data was fetched).** The nearest monthly with ≥ 6 DTE sits anywhere from 6 to about 35 DTE. That makes it a different trade (a slower decay rate and more vega) from the 7–8 DTE contract the spec is built for. The frozen pricing convention was also calibrated only on 4–8 DTE NIFTY quotes.

| Period | Span | Role | TradingView trades in span |
|---|---|---|---|
| Warm-up | 2017-11-22 to 2017-12-31 | Indicators only | 1 |
| Pre-weekly | 2018-01-01 to 2019-02-08 | **Not scored.** Spot-only result reported (§8); used in the reproduction gate (§6), which never prices options | 5 |
| **Discovery** | **2019-02-11 to 2022-12-31** | Scored (Gate A, options, placebo) | 35 |
| **Confirmation** | **2023-01-01 to 2026-11-20** | Untouched until the discovery table is written | 30 |

A trade belongs to the period of its entry date.

## 4. Rules (the spec's defaults, frozen; no grid search)

**Every parameter is the spec's default:**

| Parameter | Value |
|---|---|
| `swingLen` | 5 |
| `atrLen` | 14 (Wilder, on 1H bars) |
| `atrBufferMult` | 0.3 |
| `minRiskAtrMult` | 0.8 |
| `maxRiskAtrMult` | 1.8 |
| `rrRatio` | 2.0 |
| `beTriggerR` | 1.0 (stop to entry + 5 points) |
| `trailTriggerR` | 1.4 |
| `trailAtrMult` | 1.4 |
| `maxHoldBars` | 14 |
| `strikeOffset` | −100 (ITM-2) |
| `minDTE` | 6 calendar days |

**The spec's §6 grid is not run.** Neither are ITM-1 and ATM as alternatives; they are reported only (§8).

**Readings fixed where the spec is ambiguous** (written before reproduction):
1. **HTF filter:** the previous completed session's daily close, EMA9 and EMA40, from the NSE daily file. Bullish = close > EMA40 and EMA9 > EMA40.
2. **Pivots:** bar t−5 is a pivot high if its high is strictly above the highs of the 5 bars before it and the 5 bars after it; pivot lows mirror this. A pivot is known at the close of bar t.
3. **Structure:**
   - Bullish BOS/CHoCH means Close_t > Last_Swing_High and Close_{t−1} ≤ Last_Swing_High; it sets Market_Trend = 1.
   - The bearish shift mirrors this with Last_Swing_Low; it sets Market_Trend = −1.
   - The state persists between events.
4. **Order block:** on each bullish BOS bar, search i = 1..8 for the most recent bearish candle (default i = 1). Its high and low become the OB, which is active. A new BOS replaces the OB. It is invalidated by a close below its bottom, and consumed on entry.
5. **Session POC:** cumulative HLC3 weighted by (high − low + 0.05), resetting at 09:15. Index volume is zero, so the spec's proxy always applies.
6. **Signal at the close of bar t,** all six conditions as in spec §4. Entry is at the open of bar t+1, with one position at a time.
7. **Signal windows, on two candidate grids:**
   - **(a) Fyers 09:15 grid:** signal bars 10:15–11:15 and 14:15–15:15; entries at 11:15 and 15:15.
   - **(b) Hour-aligned grid** built from 5-minute bars (09:15–10:00, 10:00–11:00, …, 15:00–15:30): signal bars 10:00–11:00 and 14:00–15:00; entries at 11:00 and 15:00.
   - The TradingView export's timestamps (entries at 11:00 and 15:00, exits at 09:00–15:00) look like grid (b).
   - **The reproduction gate (§6) picks the grid on trade-date match only, never on P&L**, before any option is priced.
8. **Levels:**
   - Risk = Entry − (OB_bot − 0.3·ATR), clamped to [0.8, 1.8]·ATR.
   - Stop = Entry − Risk; target = Entry + 2·Risk.
9. **Stop management:**
   - Updates are computed at a bar's close and apply from the next bar, never inside the bar that triggered them.
   - Breakeven: once the high reaches entry + 1.0R, stop = max(stop, entry + 5).
   - Trail: from +1.4R, stop = max(stop, close − 1.4·ATR).
   - Structure trail: on a new bullish BOS while in the trade, stop = max(stop, OB_bot − 0.3·ATR). A stop never moves down.
10. **Exits:**
    - Within each 1H bar, the 5-minute bars locate the first touch of the stop or the target.
    - If one 5-minute bar touches both, the stop is taken.
    - A bar that opens beyond a level fills at its open.
    - Time stop: the close of the 14th 1H bar, counting the entry bar as bar 1.

## 5. Option leg (frozen)

**Contract:**
- Strike = round(Entry/50)·50 − 100.
- Expiry = the nearest NIFTY expiry with at least 6 calendar days left at entry.
  - **From 2019-02-11, weeklies:** Thursday expiries until 2025-08-28, Tuesday from 2025-09-02, holiday-adjusted (`core/orb_scalping/expiry.py`).
  - Entries before 2019-02-11 are not priced at all (§3).

**Premium** (Black-Scholes, theoretical: real intraday prices of expired contracts are not fetchable from Fyers):
- **Pricer:** `core/orb_scalping/premium.py` and `core/options/greeks.py`, unchanged.
- **Time convention:** the frozen holdout-validated ORB convention (`docs/ORB_TIME_CONVENTION_RESULTS.md`), applied with `effective_days_to_expiry`:
  - session 1.85, weeknight 0.0, weekend 0.4 calendar-day-equivalents;
  - implied vol = **0.74 × India VIX**, taken at the 5-minute bar of entry and of exit;
  - risk-free rate: the module default.
- **Prices taken at those moments:**
  - **Entry:** spot at the open of bar t+1, priced at that bar's open time.
  - **Exit:** spot at the fill level, or the bar's open if it gapped, priced at the end of the 5-minute bar that filled. For the time stop, the 1H close is used.

**Costs** (`core/orb_scalping/costs.py`):
- **Scored:** `stratified_spread_trade_cost`, the locked final ORB variant, from real sampled NIFTY spreads, with expiry-day stratification.
- **Also reported:** Stressed (+15 bps per leg).
- **Lot size:** 75 for every year. It only scales the flat brokerage; every result is per unit of premium.

**Scored measure:** net return on premium per trade, (exit − entry − cost per unit) / entry.

## 6. Order of work (stops for the user at step 2)

1. Fetch, cache and hash the data (§2).
2. **Reproduction gate.** Spot rules only, both grids, over the TradingView trades whose entries fall from 2017-12-01 onwards (71 trades). A TradingView trade is matched when this engine enters on the same date and in the same window.
   - The grid with the higher match rate is used. If both are within 2 points, grid (a) is used, as it is Fyers' native grid.
   - **Gate: ≥ 80% matched** on the chosen grid.
   - Below 80%, nothing more runs. The mismatches go to the user, and any rule reading changed to fix them is a dated amendment made before step 3, judged on match rate only.
   - **4–5 worked trades** are sent to the user side by side with TradingView. They cover both windows, a Friday entry, and one each of a stop, target and time-stop exit.
3. On the user's go-ahead: the full run (§7–8), discovery first. The confirmation numbers are computed only after the discovery table is written to the results doc.

## 7. How a pass is decided

**Gate A, model-free (spot):** the discovery mean net index points per trade must be > 0. The net is after a futures-equivalent round trip of 0.04% of entry spot: STT, exchange charges and about one point of slippage.
- If Gate A fails, H1 FAILS. Options are a delta wrapper less decay, so a spot loss can't become an options gain.
- The options numbers are still reported.

**Placebo** (daily-uptrend, time-matched), built for each period:
- Each real trade gets a placebo entry drawn at random among the same period's bars that meet three conditions:
  - the same window (the 11:15 or 15:15 entry, or 11:00/15:00 on grid b);
  - HTF_Bullish true;
  - the same calendar year.
- No structure, POC or OB condition applies.
- The placebo trade copies the real trade's Initial_Risk in ATR units and runs the same exit rules. Its structure trail uses the same BOS events. Contract, pricing and costs are the same.
- There are 2,000 placebo sets. p = the share of placebo set means ≥ the real mean.

**Discovery, 2019-02-11 to 2022:** H1 goes on to confirmation only if all three hold:
- the mean net return on premium is > 0;
- one-sided t ≥ 2.0;
- placebo p ≤ 0.05.

**Confirmation, 2023 to 2026-11-20:** H1 passes only if both hold:
- the mean net return on premium is > 0;
- placebo p ≤ 0.10.

**Anything else FAILS.**
- **No re-tuning:** a failure is reported as failed, with no parameter, window or strike changes in this round.
- **A pass means** a pre-registered paper forward test with real quotes from the option-chain recorder. It is not capital: trading is paused, and capital changes need the user.

## 8. Reported, not scored

**Friday and weekend holds, broken out separately:**
- Groups: intraday-only holds; holds over one weeknight; **holds over a weekend or holiday gap**, with Friday entries shown on their own within that group.
- Per group: n, mean spot points, mean option net, and the decay paid (the option's change at constant spot and VIX).
- Each group is priced under all three time conventions: frozen, calendar and 252-day. The weekend weight (0.4) is the least-identified part of the frozen fit, so this table shows how much of any weekend result depends on it.

**Other splits:**
- 11:15 vs 15:15 entries.
- Exit-reason mix.
- Per year.
- The pre-weekly stretch (2018-01 to 2019-02-08): spot only, no options.
- ITM-1 and ATM strikes.
- Clean and Stressed costs.
- Spot-only results against the TradingView export.

**Pricing checks:**
- **Against NSE end-of-day option closes** (`data_cache/nse_bhavcopy`, 2023-07 to 2026-07): for each 15:15 or 15:00 entry, the model's price of its contract at 15:30 spot against the bhavcopy close. Report the median absolute percentage error.
- **Against real recorded quotes:** for any trade since 2026-09-30, compared with the option-chain recorder.

**What would make the result untrustworthy (stated now):**
- Model premiums: a real 15:15 fill pays the ask and sells at the bid; Stratified covers the spread but not size impact.
- The ITM-2 strike sits outside the ATM-calibrated vol scale (skew), and the weekend weight is weakly identified.
- Only about 35 and 30 trades: a real but small edge can fail here. A pass on n ≈ 30 is still weak evidence.
- The engine reproduces TradingView's spot entries only as far as the gate measures.

## Amendments

_None._
