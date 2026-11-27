# NIFTY Alpha 50: rebuild, then two changes (skip-month, market filter) (pre-registration, 2026-11-27)

Written **before any code for it exists and before any run**. Research only: trading is paused, nothing live changes, whatever the result.

Nifty Alpha 50 is the bar our momentum candidates lost to (S8-3 by 16.5 pts of CAGR, S1 by 12, candidate 11 closed ~40% of the gap). It can be bought as an ETF, so a rebuild is only worth anything if a **change** beats it. The changes were chosen by the user on 2026-11-27: rank on alpha that **skips the most recent month(s)**, and a **market filter** that holds cash when the market is below its trend. Monthly rebalancing was ruled out (more trading, more cost and tax). Entry timing from the v3 map is a separate, later test (step 3, its own pre-registration), not part of this one.

## Data

- **Stocks:** NSE daily equity bhavcopies 2016-01-01 to 2023-12-31, EQ series, including later-delisted names, split/bonus-adjusted, with the loaders of `scripts/backtest_darvas_atr_stop_oos.py` imported unchanged. Prices only: dividends are not in the data, so every return here is a **price return**, like the NIFTY Alpha 50 price index it is compared to.
- **Indices** (`scripts/fetch_index_history.py`, Fyers, pulled 2026-11-27): NIFTY 50 and NIFTY 500 daily closes from 2015-01-01; NIFTY Alpha 50 price index from **2018-03-14** (the start of Fyers' history).

## Base version: the index's own rules (NSE's "Methodology Document of NIFTY Alpha 50 Index", September 2019, supplied by the user)

At each review:

- **Cut-off:** the last trading day of February, May, August and November.
- **Eligible:** among the 300 stocks with the highest **average daily traded value** over the 6 months to the cut-off. NSE also ranks on free-float market cap, which we don't have; traded value alone is the proxy. A stock must also have bars from at least one year before the cut-off, and a bar on **every** session of the year to the cut-off (100% trading frequency).
- **Alpha:** an OLS regression of the stock's daily simple returns on NIFTY 50's daily returns over the sessions of the year to the cut-off (`r_i = a + b·r_m + e`). Alpha = `a × 252`. The NSE document doesn't give the formula; this is the standard Jensen form with the risk-free rate left out (it changes no ranking much, since betas cluster near 1). Whether it is close enough is what the tracking check below tests.
- **Selection:** stocks with alpha ≤ 0 are not selected. Ranked by alpha, an existing constituent ranked within the top 100 is kept (the 100% buffer); the remaining places up to 50 go to the highest-ranked non-constituents.
- **Weights:** proportional to alpha, no cap (the document gives none). The largest weight at each review is reported.
- **Effective date:** the portfolio changes at the **close of the F&O expiry day** of March, June, September and December (the last Thursday of the month that is a session, else the session before), so it is held from the next session, as the index is. Between reviews the holdings drift with prices (no re-weighting).
- **A constituent that stops trading** (delisted or merged) is sold at its last close; the money is spread over the other holdings pro rata.
- First review: cut-off 2017-02-28, effective from the close of 2017-03-30.

## Step 1: tracking check (gate)

The base version, **before costs**, against the NIFTY Alpha 50 price index over **2018-03-14 to 2023-12-29**:

- the correlation of daily returns is **≥ 0.90**, and
- the CAGR differs by **no more than 3.0 percentage points**.

If either fails, the rebuild doesn't track the index, every change measured on it means little, and **the test stops there**: reported as a failed rebuild, no step 2.

## Step 2: the grid (12 versions)

- **Skip:** alpha is computed on a window that ends **S months** before the cut-off (S × 21 sessions), with **lookback L months** (L × 21 sessions). S ∈ {1, 2}, L ∈ {9, 12}.
- **Market filter:** none, or **NIFTY 500 above its N-day SMA**, N ∈ {150, 200}. Checked at **each month-end close** only. Below → everything is sold at that close and held as cash, earning nothing (conservative; a liquid fund would earn ~6%). Back above at a later month-end → the current target portfolio (the latest review's stocks and alpha weights) is bought at that close. A review that falls while in cash only updates the target.
- 2 × 2 × 3 = **12 versions**. Everything else is the base version's rules.

The base version (S = 0, L = 12, no filter) is the comparator, not a grid member.

## Costs

Every rupee traded pays the per-side rate of `STRESSED_COST_MODEL` (`scripts/backtest_darvas_box_width.py`: STT, exchange, SEBI, stamp, GST, 25 bps slippage): half the round-trip cost of a ₹1,00,000 position at ₹1,000, as a fraction of the rupees traded. The rate is printed in the report. A ₹10,00,000 portfolio, fractional shares (lot rounding ignored). Taxes are not in the score (see Reported).

## Measures

From each version's daily value, **net of costs**, over **2017-03-31 to 2023-12-29**:

- **Score:** Sharpe ratio of daily returns, annualised (√252), risk-free 0.
- CAGR and maximum drawdown.
- **Median version:** the 12 versions ranked by score lowest to highest; the median is the **6th** (the lower of the two middle ones).

## Pass (all must hold)

1. **Better risk-adjusted:** the median version's Sharpe is above the base version's, and in a **block bootstrap of paired monthly returns** (3-month blocks, 10,000 draws, seed 20261127) the median version's Sharpe beats the base version's in **at least 90%** of draws.
2. **Smaller worst fall:** the median version's maximum drawdown is smaller than the base version's.
3. **Breadth:** at least **9 of 12** versions have a Sharpe above the base version's.
4. **Both halves:** the median version's Sharpe is above the base version's in 2017-03-31 to 2020-06-30 and in 2020-07-01 to 2023-12-29.
5. **Walk-forward:** for each calendar year 2019 to 2023, the version with the best Sharpe from 2017-03-31 to the end of the year before is chosen, and its daily returns for that year are kept. The stitched series' Sharpe is above the base version's over 2019-23. (Switching costs between versions are ignored.)

Anything else is a FAIL, reported as failed and not re-tuned this round.

## Reported, not scored

- All 12 versions and the base: CAGR, Sharpe, maximum drawdown, time in cash, turnover per year.
- The median version and the base against the real NIFTY Alpha 50 price index and NIFTY 500 (2018-03-14 on).
- Per-year returns of the median version, the base and the index.
- **Tax view:** the share of sold rupees held under one year (short-term, 20% on gains) vs one year or more (long-term, 12.5% above the exemption), for the median version and the base.
- The walk-forward's choice each year.
- The largest single-stock weight at each review.
- 2024-26 on the newer price store (survivorship-biased): base and median version, reported only, run later on the VM.

## Before the full run

Shown to the user, mechanics only:
- the first review (cut-off 2017-02-28): eligible count, and the top 10 by alpha with beta, alpha and weight;
- the second review: which constituents stayed on the buffer, which left, which came in;
- one month-end where the 200-day filter switches, with the NIFTY 500 close and its SMA.

Then step 1 runs. Step 2 runs once, only if step 1 passes.

## If it passes

The median version becomes a candidate for a quarterly paper portfolio, scored on its own, beside candidate 11's walk-forward (which it does not replace or touch). Real money still needs the user's go-ahead, and trading stays paused until the user lifts it.

## Amendment 1 (2026-11-27, before any code was written or run; mechanics only)

- **Stock data starts 2015-01-01**, not 2016-01-01, so every version's alpha window is complete at the first review (S = 2, L = 12 needs about 14 months before 2017-02-28). NSE's corporate-actions list on hand starts in 2016, so 2015 splits and bonuses are caught only by the loader's standard-fraction jump fix. Measurement still starts 2017-03-31.
- **Order of the eligibility rules:** the 300 by average traded value are ranked among all stocks that traded in the 6 months; the one-year listing and 100% trading-frequency rules are then applied to those 300.
- **Alpha windows that start before the trading-frequency year** (the skip versions): returns are taken over consecutive sessions where both bars exist; a stock needs bars on at least 95% of the window's sessions, else it is not eligible for that version at that review.
