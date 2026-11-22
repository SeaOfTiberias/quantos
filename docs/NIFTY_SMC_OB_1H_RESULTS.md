# NIFTY 1H SMC order block: results

**ARCHIVED 2026-11-22 (user):** the naked long-call variant is closed. A follow-up that changes only the option expression (bull put credit spread) is pre-registered separately in `docs/NIFTY_SMC_OB_1H_BULLPUT_PREREG_2026-11-22.md`.

**Verdict: FAIL** (2026-11-22). It fails in discovery, and it would also have failed confirmation on its own bar.
- The SMC entry does no better than buying an ITM-2 call at the same hour on a random daily-uptrend day.
- The options version nets about +0.7–0.9% per trade, with t 0.1–0.2.
- No re-tuning in this round (pre-registration §7).

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

## Step 3b: confirmation (2026-11-22): reported only (H1 had already failed)

**Confirmation, 2023-01-01 to 2026-11-20: n = 32**

| Measure | Value |
|---|---|
| Gate A: spot net points per trade (after 0.04% round trip) | +10.9 (gross +20.1; t 0.47) |
| Options: mean net return on premium (Stratified) | +0.69% (median -9.79%) |
| One-sided t | 0.11 |
| Winners (net > 0) | 11 of 32 |
| Mean entry premium / mean decay paid (points) | 246.7 / -20.6 |
| Mean cost per round trip (points) | 1.59 |
| Placebo (2000 sets, pool 1074 bars): mean of set means | -1.01% (5th–95th pct -11.58% .. +10.91%) |
| Placebo p (share of sets ≥ real) | 0.389 |
| Placebo, spot: mean -1.6 pts, p | 0.317 |
| Clean / Stressed mean net | +1.11% / +0.81% |

This would also **FAIL** on its own bar (placebo p 0.389 > 0.10; t 0.11).

### Diagnostics (§8; reported, not scored)

**Holds by overnight gap, both periods together** (mean net return on premium, Stratified):

| Group | n | Spot pts | Net (frozen) | Decay paid, pts (frozen) | Net (calendar) | Net (252-day) |
|---|---|---|---|---|---|---|
| intraday | 14 | -54.3 | -16.75% | -5.3 | -14.20% | -15.18% |
| weeknight only | 39 | +22.2 | +2.39% | -14.2 | +2.29% | +1.03% |
| weekend/holiday gap | 16 | +71.2 | +12.35% | -31.3 | +0.89% | +10.25% |
|   of which Friday entries | 12 | +81.0 | +18.30% | -29.4 | +6.52% | +15.66% |
|   Friday entries, intraday | 1 | -52.0 | -22.38% | -1.0 | -20.27% | -19.99% |

**By entry window:**

| | Discovery n | Discovery net | Confirmation n | Confirmation net |
|---|---|---|---|---|
| 11:00 | 19 | -0.40% | 17 | +3.38% |
| 15:00 | 18 | +2.31% | 15 | -2.36% |

**By exit reason:**

| | Discovery n | Discovery net | Confirmation n | Confirmation net |
|---|---|---|---|---|
| stop | 13 | -24.84% | 12 | -25.29% |
| stop_gap | 0 | — | 1 | -48.49% |
| stop_gap_raised | 1 | -6.18% | 1 | -16.33% |
| stop_raised | 11 | -3.13% | 5 | +3.26% |
| target | 5 | +44.83% | 4 | +65.44% |
| target_gap | 2 | +54.71% | 1 | +50.73% |
| time | 5 | +12.81% | 8 | +7.71% |

**By year:**

| | Discovery n | Discovery net | Confirmation n | Confirmation net |
|---|---|---|---|---|
| 2019 | 8 | -9.09% | 0 | — |
| 2020 | 10 | +8.01% | 0 | — |
| 2021 | 12 | +0.16% | 0 | — |
| 2022 | 7 | +3.53% | 0 | — |
| 2023 | 0 | — | 8 | +2.63% |
| 2024 | 0 | — | 14 | +5.06% |
| 2025 | 0 | — | 6 | +8.61% |
| 2026 | 0 | — | 4 | -30.33% |

**Strike (frozen convention, Stratified):**

| Strike | Discovery net | Confirmation net |
|---|---|---|
| ITM-2 (scored) | +0.92% | +0.69% |
| ITM-1 | +0.51% | +0.34% |
| ATM | -0.04% | -0.09% |

**Pre-weekly stretch 2018-01-01 to 2019-02-08 (spot only, not scored):** n 5, mean gross +29.8 pts, net +25.5 pts.

**Spot against the TradingView export, matched trades (70):** this engine +1476 pts, TradingView +1763 pts.

**Pricing check against NSE end-of-day option closes** (model at 15:30 spot and VIX vs the contract's bhavcopy close, entry day):

| Span | n | Median abs error | 90th pct |
|---|---|---|---|
| pre-registered span 2023-07..2026-07, 15:00 entries | 10 | 9.1% | 16.5% |
| every entry 2019-02..2026-10 | 24 | 7.0% | 14.7% |

**Real recorded quotes (option-chain recorder, since 2026-09-30):** 0 trades in that span: nothing to compare.


### Reading the diagnostics

- **Weekend holds.** Holds over a weekend or holiday gap are the only group that looks good: n 16, +12.35% under the frozen convention; Friday entries n 12, +18.30%.
  - Much of that depends on the pricing convention. Under calendar time it is +0.89% (Friday +6.52%), because the frozen fit charges only 0.4 days of decay for a weekend. That weekend weight is the least-identified number in it.
  - The spot move is real (+71 points, against +22 for weeknight holds).
  - It is a post-hoc subset of 16 trades with no placebo of its own, so **it is not a result.** Testing "Friday-entry calls carry weekend drift" would be a new hypothesis needing its own pre-registration, its own placebo (random daily-uptrend Friday entries), and real weekend quotes to pin down the decay. The plan's research-churn warning applies.
- **Intraday exits** (n 14, −16.75%) are mostly stops the same day.
- **Strikes.** ITM-2 is better than ITM-1, which is better than ATM: the deeper strike carries less decay for each point of delta. None is meaningfully positive.
- **Years.** 2026 so far: 4 trades, −30.33%.
- **Spot against TradingView** (70 matched trades): this engine +1,476 points against TradingView's +1,763. TradingView is about 4 points better per trade. Its broker emulator assumes an intrabar path within the 1H bar, where this engine reads the real 5-minute path. Even the TradingView figure is about 25 points gross per trade, which the placebo matches.
- **Pricing.** The model is within 7–9% of NSE end-of-day closes (median; 90th percentile about 15–17%), but on only 24 matched contracts. Many of the trades' contracts had no usable bhavcopy row on the entry date, so it is a rough check. A 9% premium error is smaller than the difference between the strategy and its placebo would need to be to matter here: both use the same pricer.
