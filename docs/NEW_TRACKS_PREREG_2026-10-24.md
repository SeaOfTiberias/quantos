# New tracks: surge bull put credit spreads and EUR/USD–GBP/USD cointegration. Pre-registration (2026-10-24)

Written and committed before any of these tests ran. Nothing below has been computed on the data.

## Why, and what was left out

The user brought a multi-track spec ("Master task specification: multi-asset backtesting & go-live validation"). Checked against the strategy record, the user chose two tracks:

| Spec track | Decision |
|---|---|
| 2.2b Bull put credit spread on surges, IV rank > 70 | **Tested here (track A).** New. Consistent with candidate 23 Stage 1: non-52-week-high surges keep going. |
| 1.1 EUR/USD vs GBP/USD cointegration | **Tested here (track B).** The tradable variant: RBI allows residents EUR-USD and GBP-USD on Indian exchanges. |
| 1.1 AUD/USD vs CAD/USD, 1.2 USD/CAD | Not tested. Residents can't legally trade them (RBI: INR pairs plus EUR-USD, GBP-USD, USD-JPY only, on recognised Indian exchanges). |
| 2.1 Surge bear call spread (S19) | Not tested. Candidate 23 Stage 1 (2026-10-15) found no reversal after surges; there's nothing to fade. |
| 2.2a Bull call debit on 20-day breakouts | Not chosen by the user. |
| 3.1 StatArb PCA "duckling" | Not tested. Failed twice under pre-registration on 2026-10-13 (Bank Nifty PF 0.92, Nifty 50 PF 0.86); family retired. A re-run with different parameters would be re-tuning. |

## Shared definitions

- **Per-trade return** = net P&L ÷ the capital the trade puts at risk (track A: the spread's max loss; track B: margin, defined below). Trades are equally weighted.
- **Profit factor (PF)** = sum of positive per-trade returns ÷ |sum of negative ones|.
- **Sharpe** = annualised (×√252) mean ÷ standard deviation of the **daily mark-to-market P&L** of a book that holds every signal at one unit of risk. Days with nothing open count as zero.
- **Halves**: each track's trades split by entry date at the stated midpoint.
- **Bootstrap**: resampled by entry week, 10,000 draws, seed 20261024. Two tracks, so the bound is the **2.5th percentile** (one-sided 0.05 / 2).

### Stage 1 (per-trade screen). A track passes only if all hold:
1. PF > **1.20**, Stressed costs.
2. Sharpe > **0.80**.
3. Win rate > **50%** (both tracks are high-win-rate structures: a credit spread and a mean reversion).
4. PF > 1.0 in **each half**.
5. Bootstrap 2.5th percentile of the mean per-trade return > 0.
6. At least 100 trades (track A) / 30 trades (track B).

### Stage 2 (real-NAV quarter-Kelly). Only for a Stage 1 pass; reported for both regardless.
- Chronological simulation from starting NAV **₹1,00,000**, **₹2,50,000** and **₹5,00,000**.
- **Kelly fraction** at each entry, from trades **closed before that entry date** only: f = W − (1 − W) ÷ R, with W the win rate and R the average win ÷ average loss of per-trade returns. The first 30 closed trades are a warm-up: not taken, and no NAV change.
- **Lots** = ⌊ NAV × 0.25 × f ÷ margin per lot ⌋.
  - f ≤ 0: no trade (the edge has gone; counted, not a lockout).
  - f > 0 and lots = 0: a **lot-lockout event**; the trade is skipped.
  - Margin already in use + new margin > NAV: skipped as "capital busy" (counted).
- **Daily kill switch**: if a day's mark-to-market P&L ≤ −5% of the prior day's NAV, every open position is closed at that day's close and no entry is taken the next session. Counted.
- **Stage 2 pass at a tier**: max NAV drawdown < **20%** and **zero** lot-lockout events. **Capital floor** = the smallest tier that passes.

**Go-live status** = PASS only if Stage 1 passes and Stage 2 passes at one or more tiers. A PASS leads to **paper** first, and to the order gateway only on the user's go-ahead. Track B would also need the NSE currency segment enabled on the account.

## Track A: bull put credit spread on non-52-week-high surges

- **Events**: candidate 23's events unchanged (`core/surge/events.py::find_events`, cached futures panel, results dates), branch `breakout52 = FALSE`: 2,571 events, 2020-03-02 to 2026-09-24 (event count checked before writing this; no outcome looked at).
- **IV**: each F&O stock's daily ATM implied vol, from the cached NSE F&O bhavcopy (2019-02-11 to 2026-10-12):
  - expiry: the nearest with ≥ 5 trading days left; F = that expiry's futures close (or, if missing, the near-month futures close);
  - ATM = the listed strike nearest F; IV = mean of the CE and PE Black-76 IVs (r = 0) from their closes (settlement price when the option didn't trade);
  - **IV rank** on day t = (IV_t − min) ÷ (max − min) over sessions t−251 … t; needs ≥ 200 valid IV days.
- **Gate**: IV rank ≥ **0.70** on the surge day.
- **Expiry**: the nearest listed PE expiry with ≥ **10** trading days after t.
- **Strikes** (puts listed and traded on t, contracts > 0), deltas by Black-76 from each strike's own IV:
  - short leg: |Δ| in [0.30, 0.40], nearest 0.35;
  - long leg: |Δ| in [0.10, 0.15], nearest 0.125, strike below the short.
  - None available → skipped (counted).
- **Entry**: close of surge day t. Credit = short close − long close; needs 0 < credit < width.
- **Exits**, checked on each later close (close, else settlement, else intrinsic from the futures close):
  - take profit: spread value ≤ 50% of the credit;
  - stop: spread value ≥ 2.5 × credit (a loss of 1.5 × credit);
  - time: the close of the last trading day before expiry (stock options settle physically).
  - Checks are on closes only, so intraday breaches fill at that day's close. Disclosed, not fixable on daily data.
- **Costs**: candidate 23's table (`core/surge/spreads.py`): STT on sold premium by date, exchange, SEBI, stamp, GST, ₹20 × 4 orders. Bid-ask per leg per side max(c × price, ₹0.05). **Stressed c = 2% gates**; Base c = 1% is reported.
- **Margin per lot** = max loss = (width − credit) × lot. NSE's lot from 2024 on; before that, the symbol's earliest 2024 lot, else candidate 23's ₹5L-notional fallback. Real SPAN margin for a spread can be higher: disclosed.
- **Halves**: entry before / from 2023-07-01.

## Track B: EUR/USD vs GBP/USD cointegration

- **Data**: FRED daily DEXUSEU (USD per EUR), DEXUSUK (USD per GBP), DEXINUS (INR per USD); policy rates DFF (USD), ECBDFR (EUR), IUDSOIA (GBP SONIA), forward-filled. Signals from 2000-01-03 (after a 252-observation warm-up) to 2026-10-16.
- **Each day t**, on the last 252 observations of x = ln EURUSD and y = ln GBPUSD:
  - Johansen (constant, 1 lag difference): trace statistic for r = 0 above its 95% critical value; hedge vector = the first eigenvector scaled so x has weight 1: s = x + b·y;
  - ADF on s over the window (constant, lag by AIC): p < 0.05;
  - half-life λ from Δs_t = a + φ·s_(t−1): λ = −ln 2 ÷ ln(1 + φ), needs 1 ≤ λ ≤ 126.
  - **Entry requires all three.**
- **Z-score**: L = clip(round(λ), 5, 126); z = (s_t − mean) ÷ sd of the last L values of s.
- **Entry**: z < −1.5 → long the spread; z > +1.5 → short it. One position at a time.
  - At entry, b, L and the half-life are frozen; z keeps being computed with the frozen b and L.
- **Exit**: z crosses 0, or after 4 × λ sessions, whichever is first.
- **Position**: one unit = $10,000 in EUR and b × $10,000 in GBP (b < 0 means short GBP), USD P&L converted at DEXINUS.
- **Carry**, per calendar day held: each leg's dollar exposure × (its currency's rate − the USD rate) ÷ 365.
- **Costs** per leg per side: **Stressed 4 pips (0.0004 in price) gates**; Base 1 pip is reported; plus ₹20 per order. NSE's cross-currency futures are thinly traded, so the spread assumption is the main risk to the result.
- **Margin per unit** = 3.5% of gross notional (both legs), in INR.
- **Halves**: entry before / from 2013-07-01.

## Excluded, stated now

- **Intraday data.** Exits use daily closes only. No volume-profile filter (spec 2.1 needed value area high, which isn't available historically).
- **Execution integration.** No order code is written for either track in this round, whatever the result.

## After the run

- Results are appended to this file. The script is `scripts/backtest_new_tracks.py`; strategy code is in `core/surge/put_credit.py`, `core/fx_coint/` and `core/backtest/evaluator.py`.
- A failed test is reported as failed and not re-tuned in this round.
- The vault gets the result (ingest, compile, report).
