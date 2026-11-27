# Desk edge E3, phase 1: overnight vs intraday in NIFTY / BANKNIFTY futures (pre-registration, 2026-11-27)

**Status: signed off by the user 2026-11-27**, before any return was computed. Written after the code and a data-count check (files and nights only, no returns), before any return was computed. Research only: trading is paused, nothing live changes. Plan: `docs/QUANT_DESK_PLAN_2026-11-27.md` §4 E3.

## Question

Is there a premium for holding NIFTY or BANKNIFTY futures **overnight** (close to next open) that survives **today's** costs? This is measurement only. No trading rule is tested here; a phase 2 rule gets its own pre-registration only if phase 1 finds the premium alive.

Why it might exist: holding through the overnight gap carries risk that a day trader avoids, and such a premium is documented in several markets. Why it might not: India's overnight gap mostly prices news from the US session and GIFT Nifty, and the 2026 futures STT (0.05% on the sell side) is large next to a typical overnight move.

## Data

- **Index futures from the NSE F&O bhavcopy** (`core/fno/bhavcopy_futures.py`, the cached raw zips; both NSE file generations, the format told by the header). Window **2019-02-11 to 2026-11-27**. 31 missing files were fetched on 2026-11-27 before this was written; 2021-03-30 is missing from NSE's archive.
- Data check, no returns: before the fetch, 1,888 NIFTY and 1,886 BANKNIFTY nights.
- **Prices:** `open` = the day's first trade. `close` = NSE's futures closing price, the **volume-weighted average of the last 30 minutes** (achievable by trading through 15:00-15:30, not the last tick).

## Definitions

- **Contract:** on session *d*, the nearest expiry **strictly after** *d* (on expiry day, the next month), so a position opened at *d*'s close can be closed at the next open on the same contract.
- **Night:** session *d* to the next NSE session *n* (`core.reference.calendar`). It counts only if:
  - both files are present (a gap is never bridged);
  - neither *d* nor *n* is a Saturday or Sunday (special sessions: Muhurat, Budget days, DR drills);
  - the contract trades on both days.
- **Overnight return** = open(*n*) / close(*d*) − 1. **Intraday return** = close(*d*) / open(*d*) − 1, same contract.
- **Cost (verdict):** one round trip of a long position at **2026 rates on every night**, the rates we would pay now (`core/pairs/costs.py`: STT 0.05% sell side, exchange, SEBI, stamp, GST, brokerage ₹20/order; where the lot size isn't in the file, a ₹10 lakh notional for the brokerage cap). Plus **slippage of 1 bp at the close and 2 bps at the open**, 3 bps per round trip.

## Verdict (each index separately)

Phase 1 is **ALIVE** for an index only if **all** hold for the overnight net return (gross minus verdict cost, in bps per night):

1. the mean over the whole window is **> 0** with a one-sided t-statistic **≥ 2.24** (1.25%: a 2.5% level split over the two indices);
2. the mean is **> 0 in both halves**: 2019-02-11 to 2022-12-31, and 2023-01-01 to 2026-11-27.

Otherwise it is **DEAD**, reported as failed, and not re-tuned: no other contract, cost, slippage, window or session filter is tried afterwards. If both indices are dead, E3 closes and the desk moves to E1.

## Reported, not scored

- Overnight net at each night's own historical rates (STT 0.0125% / 0.02% / 0.05%).
- By year; weekend/holiday nights vs one-night gaps.
- The intraday mirror (buy at open, sell at close) at verdict costs.
- From 2024, overnight from the **last trade** instead of the 30-minute VWAP close (newer files only).

## Before the run

Worked cases are shown to the user: 5 nights per index (dates, contract, prices, both returns, cost). Then the full measurement runs once (`scripts/measure_overnight_futures.py`), and the results go to `docs/E3_OVERNIGHT_RESULTS_2026-11-27.md`, committed before they are reported.

## If alive

A phase 2 pre-registration: a 1-lot buy-close/sell-open rule with margin cost charged, judged on the desk standards (deflated Sharpe counting every trial on record). Trading stays paused until the user lifts it.
