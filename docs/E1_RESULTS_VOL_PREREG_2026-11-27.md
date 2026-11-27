# Desk edge E1, phase 1: is the stock straddle overpriced across results? (pre-registration, 2026-11-27)

**Status: signed off by the user 2026-11-27**, before any P&L was computed. Written after the code and a data check (event and contract counts only, no P&L), before any P&L was computed. Research only: trading is paused, nothing live changes. Plan: `docs/QUANT_DESK_PLAN_2026-11-27.md` §4 E1.

## Question

Retail buys stock options into results. If that demand makes the straddle overpriced, **selling the at-the-money straddle at the last close before a results broadcast and buying it back at the next close** earns money on average, after today's costs, more than the same trade on an ordinary day.

### Change from the desk plan

The plan's phase 1 compared the implied move (straddle ÷ spot) with the realized move. That comparison is distorted by the option's remaining life: a straddle with 20 days left prices 20 days of ordinary movement as well as the results. So the measure here is the **straddle's own round trip** (sell at P, buy at R). The implied/realized ratio is reported, not scored.

## Data

- **Results events** (`core/fno/results_events.py`): NSE's corporate financial-results filing metadata (`data_cache/pead_nse/metadata_raw`, and from April 2025 the integrated-filing feed `if_metadata_raw`). An event is the **first broadcast** of a company's results for a period (symbol + period end), from the broadcast's timestamp. Window: broadcasts **2019-02-11 to 2026-10-31**.
- **Stock options and stock futures** from the cached NSE F&O bhavcopy (`core/fno/bhavcopy_options.py`, `bhavcopy_futures.py`, both NSE file generations).
- **Data check** (before any P&L): see the counts at the end.

## Definitions

- **P and R:**
  - Broadcast after a session's 15:30 close, or on a non-session day: P = that session (or the last one before), R = the next session.
  - Broadcast before 15:30 on a session day (pre-open or intraday): P = the session before, R = that day.
  - Weekend sessions are excluded from the list.
- **Spot:** the stock future with the nearest expiry **after** R, closing price at P. The futures close is NSE's last-30-minute VWAP. Older files carry no spot price, so the future keeps the source uniform; carry over one day is negligible.
- **Straddle:**
  - Expiry: the nearest option expiry **after** R, so the position is closed before expiry and no exercise STT arises.
  - Strike: the one nearest the spot at P where **both** call and put traded at P (volume > 0); ties go to the lower strike.
  - Exit: bought back at R's close on the same strike, and both legs must have traded at R. Otherwise the event is dropped, and the drop is counted.
  - Prices are last traded closes.
- **P&L (short straddle)** = straddle(P) − straddle(R), in bps of the spot.
- **Cost at 2026 rates on every event** (`core/options/vrp/costs.py`):
  - STT 0.15% on the sold premium;
  - exchange, SEBI and brokerage charges plus GST on both sides;
  - stamp duty 0.003% on the buy;
  - **plus a spread haircut**: `h × (straddle(P) + straddle(R))`, where h is the half-spread per leg per side as a fraction of the premium, calibrated as below **before** the run.
- **Control:** the same stock and structure with P' = 10 sessions before P and R' = the session after. It is used only if no results event of that stock has its P within 5 sessions of P' or R'. Controls are paired one-to-one with events.

## Spread calibration (before the run, no P&L)

On **2026-11-30** (Monday) during market hours, take live quotes (Fyers, read-only) at 10:30, 12:30 and 14:30 IST:
- **Stocks:** every 5th stock of the current F&O stock list in alphabetical order.
- **Quote:** each stock's ATM call and put on the nearest monthly expiry.
- **h** = the **mean** over all sampled legs of (ask − bid) / 2 / mid. Legs with no bid or no ask are excluded and counted.

h is committed with the sample table **before** any P&L is computed, and is not changed afterwards.

Known limitation: spreads the evening before results may be wider than on an ordinary Monday. So h is a floor, and the result at **2 × h** is reported.

## Verdict

Phase 1 is **ALIVE** only if all three hold:

1. **Net mean > 0** over all usable events, with a t-statistic ≥ **2.0** computed on **calendar-month means** (results cluster in seasons; months with ≥ 5 events).
2. **Net mean > 0 in both halves**: P before 2023-01-01, and from 2023-01-01.
3. **A results-day effect, not the general premium:** the event's gross P&L beats its paired control's gross P&L on average, with a paired t ≥ **2.0**.

Otherwise it is **DEAD**, reported as failed, and not re-tuned: no other strike, expiry, timing, cost, haircut, window or stock filter is tried afterwards. If dead, E1 closes and the desk moves to E2.

## Reported, not scored

- Gross and net by year.
- Result at 2 × h.
- As % of premium.
- By days to expiry (≤ 10, 11–20, > 20).
- By broadcast timing (after hours vs during or before hours).
- By stock (top and bottom 10 by count-weighted mean).
- The implied/realized ratio distribution.
- The 10 worst events.
- The control's own net P&L (the ordinary-day straddle).

## Before the run

1. Spread calibration (above), committed.
2. **Worked cases:** 5 events with their controls (dates, broadcast, spot, strike, both straddle prices, gross), shown to the user.
3. The full measurement runs once (`scripts/measure_results_straddle.py`), and the results go to `docs/E1_RESULTS_VOL_RESULTS_2026-11-27.md`, committed before they are reported.

## If alive

A phase 2 pre-registration of a defined-risk version (an iron fly with wings frozen in advance), sized by the desk's risk framework, judged with the deflated Sharpe ratio counting every trial on record. Trading stays paused until the user lifts it.

## Data check (counts only)

Run 2026-11-27, no P&L computed.

- **Results events in the window:** 58,581.
  - 53,333 are outside F&O: no stock future with an expiry after R.
  - **5,136 usable**, across **320 stocks**.
  - Dropped: 62 where the straddle didn't trade at R, 42 with no traded ATM straddle at P, 8 with a missing file.
- **Usable by year:** 2019 477, 2020 477, 2021 562, 2022 658, 2023 683, 2024 674, 2025 849, 2026 756.
- **Paired with a clean control:** 4,904. Controls lost: 114 not traded at R, 50 no traded straddle at P, 46 missing file, 16 not in F&O, 4 no clean session, 2 no future at R.
- **Days from P to option expiry:** quartiles 11 / 18 / 25.
