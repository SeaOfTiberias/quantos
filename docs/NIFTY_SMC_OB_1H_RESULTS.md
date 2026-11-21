# NIFTY 1H SMC order block: results

Pre-registration: `docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md` (826574a, signed off 2026-11-22). Data frozen at 0f3192a (hashes in `docs/RESEARCH_DATA.md`). Engine: `core/backtest/smc_ob_1h.py`. Script: `scripts/research/smc_ob_1h.py`.

## Step 1: data (2026-11-22)

Fyers NIFTY 50 and India VIX, 60- and 5-minute bars, 2017-11-22 09:15 to 2026-11-20 15:25 IST. That is 15,557 one-hour and 166,529 five-minute NIFTY bars. Copies on the VM and the PC are verified against `SHA256SUMS`.

## Step 2: reproduction gate (2026-11-22): PASSED, grid (b)

`python scripts/research/smc_ob_1h.py reproduce`, spot rules only. The check uses entry dates and windows and never looks at P&L. It covers the TradingView entries from 2017-12-01 onwards (71 of them).

| Grid | Our trades | TradingView entries matched | Our entries not in TradingView |
|---|---|---|---|
| (a) Fyers 09:15 grid | 79 | 32 / 71 = 45% | 47 |
| **(b) hour-aligned grid** | 75 | **70 / 71 = 99%** | 5 |

By the pre-registered rule, **grid (b) is used** (09:15–10:00, 10:00–11:00, …, 15:00–15:30; signal bars 10:00 and 14:00; entries at 11:00 and 15:00). The TradingView export was built on this grid.

**The one miss, #68 (Fri 2023-09-15 15:00).**
- The engine took a signal one session earlier (Thu 09-14 15:00) that TradingView didn't.
- It was in that trade on the Friday, so it skipped #68, and it then entered Mon 09-18 11:00 instead.
- It is a single divergence near a threshold that cascades for two trades.

**Our 5 extra entries:** 2019-07-04 15:00, 2022-11-28 11:00, 2023-07-20 11:00, and 2023-09-14 15:00 and 2023-09-18 11:00 from the #68 cascade.

`python scripts/research/smc_ob_1h.py cases`, spot only:

| TV | Entry | TradingView exit | This engine's exit | Agreement |
|---|---|---|---|---|
| #44 | Fri 2020-12-04 15:00, 13,245.05 (engine 13,245.00) | Tue 12-08 11:00, 13,359.80 | Tue 12-08 11:10, 13,359.79, raised stop; stop moved to breakeven 12-07, trail 12-08 | Same exit level and hour |
| #54 | Wed 2021-07-14 11:00, 15,826.00 | Fri 07-16 11:00, 15,928.15, time exit (14 bars) | Close of Fri 07-16 10:00 bar, 15,928.00, time (bar 14) | Same: TradingView fills the close at the next bar's open |
| #78 | Fri 2024-07-26 11:00, 24,613.35 | Mon 07-29 09:00, 24,943.30 | Mon 07-29 09:15, 24,944.01, target | Within 0.7 points, over a weekend |
| #85 | Wed 2025-05-07 15:00, 24,395.70 | Thu 05-08 14:00, 24,251.65 | Thu 05-08 14:55, 24,249.65, stop | Within 2 points |
| #92 | Wed 2026-04-22 11:00, 24,440.20 | Thu 04-23 09:00, 24,202.35 | Thu 04-23 09:15, 24,202.35, gap through stop | Exact |
| #68 | Fri 2023-09-15 15:00 | — | No entry (in the 09-14 trade) | The miss above |

**Bar counts.** TradingView's "Duration (bars)" counts bars after the entry bar. The engine counts the entry bar as bar 1, which is the pre-registered reading. Both put the time stop at the same moment.


## Step 3a: discovery (2026-11-22): FAIL

User's go-ahead 2026-11-22. `python scripts/research/smc_ob_1h_step3.py discovery` (grid b). Written and committed before any confirmation number was computed.

**Discovery, 2019-02-11 to 2022-12-31: n = 37**

| Measure | Value |
|---|---|
| Gate A: spot net points per trade (after 0.04% round trip) | +10.5 (gross +16.2; t 0.68) |
| Options: mean net return on premium (Stratified) | +0.92% (median -6.82%) |
| One-sided t | 0.19 |
| Winners (net > 0) | 14 of 37 |
| Mean entry premium / mean decay paid (points) | 214.6 / -12.6 |
| Mean cost per round trip (points) | 1.43 |
| Placebo (2000 sets, pool 1187 bars): mean of set means | +2.31% (5th–95th pct -6.67% .. +11.78%) |
| Placebo p (share of sets ≥ real) | 0.590 |
| Placebo, spot: mean +12.0 pts, p | 0.530 |
| Clean / Stressed mean net | +1.38% / +1.07% |

**Verdict: FAIL. H1 does not go on to confirmation.**

| Bar (pre-registration §7) | Needed | Got | Result |
|---|---|---|---|
| Gate A | spot net > 0 | +10.5 points (t 0.68) | passes, barely |
| Options mean net | > 0 | +0.92% | passes, barely |
| One-sided t | ≥ 2.0 | 0.19 | **fails** |
| Placebo p | ≤ 0.05 | 0.590 | **fails** |

**What it means.** Random long entries on daily-uptrend days, in the same 11:00 and 15:00 windows and the same year, with the same risk, exits and contract, averaged **+2.31%**. That is better than the strategy's +0.92%, and the spot placebo did better too (+12.0 points against +10.5).
- The order-block, structure and POC conditions add nothing over "buy a call on a daily-uptrend day at 11:00 or 15:00".
- What the TradingView curve shows is the daily uptrend filter's drift, not the SMC entry.

**Code fix made during this step, before any result was seen.** The first run hung. `core/orb_scalping/expiry.py`'s `next_nifty_weekly_expiry` loops forever on a holiday-adjusted expiry: expiry + 1 day is the holiday Thursday itself, which adjusts back to the same Wednesday. The script now finds "the nearest expiry with at least 6 days" by walking the search date forward. The shared module is unchanged. Its bug matters only to callers that roll from a holiday-adjusted expiry. ORB's DTE-floor roll is one such caller; it is to be checked separately.
