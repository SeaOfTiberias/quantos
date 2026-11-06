# CCI + monthly CPR signal, and CCI / RSI entry filters (pre-registration, APPROVED by the user 2026-11-07)

Written 2026-11-07, before any code or outcome. **Approved and frozen 2026-11-07.** Any
change is a dated amendment written before the data it touches is seen.

**Where the ideas came from (disclosed):**
- **Part A** came from two charts the user picked after the move: HDFCBANK and ADANIPORTS, late
  October to early November 2026. Both fall after the data used here ends (2026-10-23), so
  neither is in the test.
- **Part B** came from the user's post-trade notes on HDFCBANK and SUPREMEIND (golden set,
  2026-11-06).

**History:** the CCI(34)/EMA52 cross alone failed as a signal on 2026-10-26 (0 of 12,
`docs/CCI_SMA_CROSS_SIGNALS_RESULTS_2026-10-26.md`), and CCI vs its EMA added nothing as a
screener filter (`docs/FNO_INDICATOR_FILTER_RESULTS_2026-10-26.md`). Part A must therefore show
that the added conditions do work the CCI cross alone did not.

---

## Part A: the combined signal

### A1. Data and universe

- **Bars:** NSE daily bhavcopy, split- and bonus-adjusted (`core/techno_funda/prices.py`), from
  2010-01-01 to 2026-10-23. A new SEGMENT in `prices.py` (an unexplained jump) restarts every
  indicator.
- **Universe on date D:** NSE EQ-series stocks in the top 500 by median daily traded value
  (`TOTTRDVAL`) over the 60 sessions before D. Delisted and renamed stocks are included while
  they qualify.
- **Signals:** 2013-01-01 to 2026-09-22, leaving 20 sessions of outcome before the data ends.
- **Point in time:** everything is computed from bars up to and including the signal day's
  close. The monthly CPR uses the previous completed calendar month only.

### A2. Indicators (fixed)

- **CCI(34):** typical price TP = (H + L + C) / 3; CCI = (TP − SMA34(TP)) / (0.015 × mean
  absolute deviation of TP over 34).
- **CCI average:** the **simple** 52-period moving average of CCI, as on the user's Zerodha
  chart. The 10-26 test used an EMA.
- **Slope, long:** the CCI average today is at most 5 points below its value 5 sessions earlier
  (flat or rising).
- **Slope, short:** the mirror: at most 5 points above (flat or falling).
- **Monthly CPR** from the previous calendar month's adjusted high, low and close:
  - P = (H + L + C) / 3;
  - BC = (H + L) / 2;
  - TC = 2P − BC;
  - CPR top = max(TC, BC), bottom = min(TC, BC).
  - Check: HDFCBANK October 2026 (H 734.90, L 669.20, C 692.80) gives 702.05 / 698.97 /
    695.88, which match the user's Zerodha chart.
- **SMA5:** the 5-day simple average of the close.

### A3. The signal

**Long:**
1. **CCI cross up** on day c: CCI(c) > avg(c) and CCI(c−1) ≤ avg(c−1). The slope condition
   holds on day c.
2. **CPR cross up** on day p: SMA5(p) > CPR top and SMA5(p−1) ≤ CPR top. Both days are
   compared with the CPR in force on day p, so a month change alone never makes a cross.
3. |c − p| ≤ 3 sessions.
4. The signal is on day max(c, p), entry at the next session's open.

**Short:** the mirror image: CCI crosses down with a flat-or-falling average, and SMA5 crosses
below the CPR bottom.

- One signal per stock per side. A new one is skipped if the same stock and side signalled in
  the previous 10 sessions.

### A4. Outcome

- **Return:** entry at the next open, exit at the close of the **10th session** (primary).
  The 5- and 20-session returns are reported only.
- **Excess return:** the trade's return minus the equal-weighted average return of the
  day's universe over the same open-to-close window. Market drift isn't credited. Shorts take
  the negative.
- **Cost:** 0.25% round trip (cash delivery, which is costlier than futures).
- **Shorts:** measured across the whole universe as a test of the signal. In practice only
  F&O stocks can be shorted overnight, so the short side is also reported for the stocks in
  the current F&O list. That split is reported only, and it carries survivorship bias.

### A5. Comparison arms (same rules, same window)

1. **CCI cross alone** (SMA52, no slope, no CPR).
2. **Full rule without the slope condition.**
3. **Full rule without the CPR condition.**

These arms are reported, and arm 1 is also part of the pass bar. None can pass on its own: the
CCI cross alone already failed in the 10-26 round, and switching its EMA to an SMA is a re-tune,
not a new test.

### A6. Measures

- Mean net excess return per trade, longs and shorts separately (2 tests: A-long, A-short).
- **Bootstrap:** 10,000 resamples of calendar weeks, seed 20261107, giving a 95% interval and a
  two-sided p-value. Weeks are resampled because signals across stocks move together.
- **Holm–Bonferroni** across A-long and A-short at α = 0.05.

### A7. Pass (each side separately; all must hold)

1. Mean net excess return of **at least +0.50% per trade** over 10 sessions.
2. Its p-value passes Holm.
3. The mean is above 0 in **both halves**, split at the side's median signal date.
4. It beats the **CCI cross alone** (arm 1, same side) by **at least 0.30 percentage points**,
   with a bootstrap 95% interval for the difference that excludes 0.
5. At least **300 trades**.

A fail is reported as a fail. Thresholds, windows, indicator settings and the universe are not
re-tuned in this round.

### A8. Reported only

- Per year.
- By Weinstein stage at entry.
- By whether price was above the monthly CPR before the signal.
- By ATR% tercile.
- Win rate.
- The 5- and 20-session horizons.
- The comparison arms of A5.
- The F&O-only short split.

---

## Part B: CCI and RSI as entry filters

### B1. Trades filtered (unchanged from `docs/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md`)

- **Trades:** the F&O screener backtest's trades (`~/.quantos/bt_fno/outcomes.jsonl`), on 213
  stocks, signals from 2025-09-02 to 2026-10-23.
- **Exit:** the same futures exit and the same 0.1% cost.
- **Deduplication:** one trade per breakout episode.
- **Three entry sets:** CE baseline, PE baseline, PE H1 retest.

### B2. Filters (daily, read at the signal day's close; each stock's own bars)

- **F1 CCI:** a put (short) is blocked when CCI(34) < −50; a call (long) is blocked when
  CCI(34) > +50.
- **F2 RSI:** a put is blocked when RSI(14, Wilder) < 40; a call is blocked when
  RSI(14) > 60.

2 filters × 3 entry sets = 6 tests.

### B3. Pass (per test; all must hold)

1. The kept trades number at least 100.
2. The kept mean is above 0 in both halves, split at the median signal date.
3. The kept mean has a day-clustered t of at least 2.7.
4. The kept mean beats the unfiltered mean in both halves.
5. The filter blocks at least **10%** of trades. The 10-26 CCI filter removed 1–7% and so
   could not matter.
6. The blocked trades' mean is lower than the kept trades' mean by at least **0.30 percentage
   points**.

A pass makes the filter a **label** on the screener first: shown, not gating. The pick log then
judges it before it ever removes a pick.

---

## Order of work

1. The user approves this document, and it is committed as APPROVED.
2. The runner is written, with unit tests on synthetic bars covering:
   - the CCI and RSI values;
   - the CPR numbers (including the HDFCBANK October check above);
   - the cross and slope rules;
   - the 3-session window;
   - the skip rule.
3. The test runs once. The results are committed before they are reported.
4. Pass or fail, the vault strategy page and the register are updated.
