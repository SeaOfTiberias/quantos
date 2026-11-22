# NIFTY 1H SMC order block, bull put credit spread: pre-registration (2026-11-22)

**Status: SIGNED OFF by the user 2026-11-23 ("lets run it"), committed before any spread was priced.** After that it changes only by a dated amendment at the end, and never after a result is seen.

**What this is:** a follow-up to `docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md` (826574a). That test is archived as FAIL (`docs/NIFTY_SMC_OB_1H_RESULTS.md`). **Only the option expression changes.** The spot signal, its parameters, the data, the periods and the placebo design stay the same.

**Plan rules:** E1–E3 are ticked, so a new pre-registration is allowed. Trading is paused, so even a pass leads only to paper.

---

## 0. What this test can and cannot show (read before signing)

1. **The data has been seen. Neither period is truly held out.**
   - The spot outcome of every trade in both periods is already known and in the results doc:
     - discovery: +10.5 points per trade, t 0.68; the spot placebo's p was 0.53;
     - confirmation: +10.9 points per trade; the spot placebo's p was 0.32.
   - A put spread's P&L is mostly that spot path plus time decay. So "confirmation" here is a second look at known data, not a blind test.
   - **A pass earns only a pre-registered forward paper test from the live data onwards**, which is the first unseen data. It earns no capital.
2. **Expected result: FAIL against the placebo.**
   - At spot level the SMC entries did no better than random daily-uptrend entries at the same hour (spot p 0.53 / 0.32).
   - A bull put spread earns the same time decay on a placebo entry as on a real one.
   - The likely outcome is that both earn something, and the real trades don't beat the placebo. That would mean "selling put spreads in a daily uptrend": a different strategy with no SMC content, which would need its own pre-registration.
   - The test is run to find out, not to confirm that.
3. **Why the call variant failed.**
   - Its 69 scored trades pooled give PF 1.05, with −16.4 points of modelled decay per trade.
   - Placebo p was 0.590 in discovery and 0.389 in confirmation. The p = 0.88 in the request doesn't come from our runs.
   - Decay was not the main cause: the placebo paid the same decay and still did as well or better.
   - Under the frozen convention weeknights carry zero time weight, so the modelled decay fell during market sessions, not overnight.
4. **The model error is larger for a spread.**
   - The spread's value is the difference of two modelled prices. Single-leg errors (median 7–9% against NSE closes for the calls) don't cancel.
   - Step 1 measures this for the spread (§6).

## 1. Hypothesis

H2. A NIFTY bull put credit spread on every frozen SMC-OB spot signal earns a positive mean net return on maximum risk per trade, after 3.0 points of round-trip costs, under the frozen pricing convention plus a frozen put skew. It also beats a daily-uptrend, time-matched placebo using the identical spread, in discovery and again in confirmation.

## 2. Signal and data (unchanged, frozen)

- **Signal:**
  - engine: `core/backtest/smc_ob_1h.py` (grid b, the hour-aligned grid chosen at the reproduction gate);
  - parameters: every default in prereg §4, items 1–10;
  - exits: spot stop, 2.0R target, breakeven at +1.0R, ATR trail at +1.4R, structure trail, 14-bar time stop.
  - No grid search.
- **Trades:** the same 69 scored entries, 37 in discovery and 32 in confirmation. Their spot entry and exit times are fixed, and the spread opens and closes at those times.
- **Data:**
  - Fyers 5-minute NIFTY and India VIX, frozen at 0f3192a.
  - NSE bhavcopy option closes, `data_cache/nse_bhavcopy/parsed/` (2019-02-11 to 2026-10). Used for the skew calibration and the pricing check only.
- **Periods:**
  - discovery: 2019-02-11 to 2022-12-31;
  - confirmation: 2023-01-01 to 2026-11-20;
  - pre-weekly entries are not scored.

## 3. The spread (frozen)

| Item | Rule |
|---|---|
| ATM | round(entry spot / 50) × 50 |
| Short put (sell) | ATM − 50 (OTM-1; delta about −0.42) |
| Long put (buy) | short strike − **250** (scored); short strike − 300 (reported, §8) |
| Expiry | the nearest holiday-adjusted NIFTY weekly with ≥ 6 calendar days left at entry (Thursday until 2025-08-28, Tuesday from 2025-09-02). The same `expiry_for` walk as the call test, not `next_nifty_weekly_expiry` (loop bug). |
| Entry | at the spot entry: the first 5-minute bar of the 11:00 or 15:00 hour; VIX at that bar's open |
| Exit | at the spot exit: the end of the filling 5-minute bar, or the 1H close for the time stop; VIX at that bar's close |
| Expiry inside a hold | impossible (≤ 14 one-hour bars against ≥ 6 days to expiry); the script asserts it |

**Pricing:**
- Black-Scholes puts (`core/options/greeks.py`, `OptionType.PUT`).
- Time convention: the frozen ORB convention (session 1.85, weeknight 0.0, weekend 0.4).
- ATM implied vol = **0.74 × India VIX**, as before.
- **Each leg's IV = 0.74 × VIX × s(z):**
  - z = ln(K / S) / (σ_ATM · √T) is the strike's standardised moneyness;
  - s is the put-skew multiplier, calibrated and frozen in step 1 (§6) before any spread is priced.

**Measures per trade (points per unit):**
- credit C = P_short − P_long at entry;
- debit D = the same at exit;
- cost = **3.0 points per round trip** for the whole spread (4 fills: slippage, brokerage, STT);
- net = C − D − cost;
- maximum risk at entry M = 250 − C.
- **Scored measure:** net return on maximum risk, R = net / M.

**Also reported:**
- Costs:
  - our own Stratified model (`stratified_spread_trade_cost`, summed over both legs);
  - our own Stressed model (summed over both legs).
- Rupees: net × the **historical NSE lot size** on the entry date. The table is built in step 1 from NSE circulars, each date cited.
- Lot size never enters R. The rupee figures are for reading, not scoring.

## 4. Placebo (identical structure)

The same design as the call test (prereg §7), with only the contract changed:
- For each real trade, draw one entry at random from the same period's bars that are:
  - in the same window (11:00 or 15:00 entry);
  - on a day with the daily uptrend filter true;
  - in the same calendar year.
- No structure, POC or OB condition.
- The placebo copies the real trade's Initial_Risk in ATR units and the same spot exits.
- It is priced with the identical spread: the same strikes rule, expiry rule, skew, convention and costs.
- 2,000 sets, seed 20261122. p = the share of placebo set means ≥ the real mean R.

## 5. How a pass is decided

**Gate A (spot)** is already known and passed (discovery +10.5 net points). It is not re-run as a gate.

**Discovery, 2019-02-11 to 2022:** H2 goes on to confirmation only if all three hold:
- mean R > 0;
- one-sided t ≥ 2.0;
- placebo p ≤ 0.05.

**Confirmation, 2023 to 2026-11-20:** H2 passes only if both hold:
- mean R > 0;
- placebo p ≤ 0.10.

**Anything else FAILS.**
- No re-tuning: no change of strikes, width, profit-take, cost or skew in this round.
- A pass leads only to a pre-registered forward paper test using live option-chain recorder quotes (see §0, point 1).

## 6. Order of work (stops for the user after step 1)

1. **Before any spread is priced:**
   - **a. Put-skew calibration from the bhavcopy.** Market quotes only; no trade outcome is used.
     - Take every session from 2019-02-11 to 2026-10, not only trade days.
     - On each, use the nearest weekly with 6–10 calendar days left.
     - Use the bhavcopy close and underlying close, priced at 15:30 under the frozen convention.
     - σ_ATM = the mean IV of the ATM call and put.
     - Take puts from ATM to ATM − 500 in 50-point steps, keeping those with volume ≥ 100 contracts and close ≥ 0.5.
     - Bucket the ratio IV_put / σ_ATM by z in steps of 0.25, from 0 to −3.
     - s(z) = the bucket median, linearly interpolated, flat beyond the ends.
     - The 2019–22 and 2023–26 halves are reported side by side, but the pooled table is used whatever they show.
     - Committed as a frozen table.
   - **b. Lot-size table** from NSE circulars, with each change date cited.
   - **c. Spread pricing check.**
     - For each scored trade's two contracts on its entry date: model credit at 15:30 against the bhavcopy close credit.
     - Report the median absolute error in points and as a share of the credit, plus the count where a leg is missing.
     - This is a pricing check, not a P&L check.
   - **d. 5 worked spreads drawn from placebo-pool entries, not real trades,** so no real result is seen. They show strikes, both legs' IV, credit, debit, cost, M and R.
   - **Stop for the user.**
2. **On the user's go-ahead:**
   - discovery first;
   - the discovery table is written to the results doc;
   - then confirmation;
   - then the diagnostics (§8).

The spread arithmetic (credit, maximum risk, R, profit-take trigger, lot lookup) is deterministic code with unit tests on synthetic values before step 2.

## 7. Code

- **Script:** `scripts/research/smc_ob_1h_bullput.py`. It reuses `World`, `manage` and the placebo pools from `scripts/research/smc_ob_1h_step3.py` unchanged, and asserts that the 69 spot trades match the export `backtest_results/SMC-OB-1H_QUANTOS_NSE_NIFTY_2026-11-22.csv`.
- **Output:** a per-trade CSV like that export, with both legs' strikes, IVs and prices, credit, debit, costs, M, R and rupees.

## 8. Reported, not scored

- **Early profit-take at 70% of the credit (secondary check).**
  - At each 5-minute close between entry and the spot exit, the spread is revalued (with VIX at that bar's close).
  - If its value is ≤ 0.30 × C, it exits there.
  - Reported: mean R, t, the placebo p with the same rule, and how often it fires.
- **The 300-point wing:** the same table as the scored 250-point wing.
- **Costs:** Stratified and Stressed (both legs) next to the 3.0-point result.
- **Pricing conventions:** calendar and 252-day time conventions next to the frozen one. Also flat IV (no skew) next to the calibrated skew.
- **Holds:** intraday, weeknight, and weekend/holiday holds, Friday entries apart, under all three conventions.
- **Breakdowns:** by window, by exit reason and by year.
- **Rupees per lot:** totals by period with the historical lot sizes.

## Amendments

**1. 2026-11-23, during step 1a, before any spread was priced.** Two readings were added.
- **Missing spot in early files.** The bhavcopy's `underlying_close` is blank in every file before 2023, which left the 2019–22 half of the calibration empty. Where it is blank, the spot is now filled with NSE's official NIFTY close from the frozen daily file (`NIFTY_daily.csv`, sha256 89ed6631…).
  - It is the same quantity: on all 680 sessions where both exist, they agree to 0.00 points.
  - The skew table, the pricing check and step 2 all use the filled value.
- **Rounding.** ATM rounds half up (`bull_put.atm`), not with Python's banker's rounding. This matters only when spot ends exactly in 25.00 or 75.00.
