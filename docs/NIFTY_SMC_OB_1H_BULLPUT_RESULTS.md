# NIFTY 1H SMC order block, bull put credit spread: results

**Verdict: FAIL (2026-11-23).** The bull put spread on the frozen SMC-OB signal does no better than the same spread opened at a random daily-uptrend entry at the same hour.
- Discovery: mean R +0.51%, t 0.27, placebo p 0.439.
- Confirmation (reported only): mean R +0.36%, t 0.14, p 0.211.
- No variant in §8 gets near the bar.
- No re-tuning in this round. Together with the call test, this closes the SMC-OB signal: two option expressions on the same spot entries, and neither beats random uptrend entries.

- Pre-registration: `docs/NIFTY_SMC_OB_1H_BULLPUT_PREREG_2026-11-22.md` (0861b92, signed off 2026-11-23; amendment 1 made during step 1a).
- Spread arithmetic: `core/backtest/bull_put.py`, tested in `tests/unit/test_bull_put.py` (21 tests).
- Script: `scripts/research/smc_ob_1h_bullput.py`.

## Step 1a: put skew, frozen

**Data:** NSE bhavcopy closes, 2019-02-11 to 2026-10-05.
- 1,757 sessions used; 128 skipped (no weekly with 6–10 days left, or the ATM pair couldn't be inverted).
- 18,015 put observations.
- Frozen table: `docs/research/nifty_put_skew_2026-11-23.json` (sha256 50ce38af…797f0b).

**How to read the table:**
- s = a put's implied vol as a multiple of the ATM implied vol.
- z = how far the strike sits below spot, in standard deviations to expiry.
- The scored short leg (ATM − 50) sits at about z −0.2 to −0.5; the long leg (250 points lower) at about z −1.3 to −2.5.

| z | s, pooled (used) | n | s, 2019–22 | n | s, 2023–26 | n |
|---|---|---|---|---|---|---|
| −0.25 to 0 | 1.058 | 3,402 | 1.073 | 1,716 | 1.038 | 1,686 |
| −0.50 to −0.25 | 1.080 | 3,333 | 1.095 | 1,679 | 1.059 | 1,654 |
| −0.75 to −0.50 | 1.105 | 3,185 | 1.119 | 1,607 | 1.085 | 1,578 |
| −1.00 to −0.75 | 1.134 | 2,865 | 1.149 | 1,464 | 1.115 | 1,401 |
| −1.25 to −1.00 | 1.167 | 2,115 | 1.184 | 1,123 | 1.147 | 992 |
| −1.50 to −1.25 | 1.209 | 1,376 | 1.224 | 761 | 1.193 | 615 |
| −1.75 to −1.50 | 1.260 | 799 | 1.267 | 479 | 1.250 | 320 |
| −2.00 to −1.75 | 1.316 | 442 | 1.321 | 296 | 1.300 | 146 |
| −2.25 to −2.00 | 1.377 | 235 | 1.390 | 172 | 1.350 | 63 |
| −2.50 to −2.25 | 1.453 | 143 | 1.453 | 114 | 1.446 | 29 |
| −2.75 to −2.50 | 1.522 | 79 | 1.522 | 73 | 1.515 | 6 |
| −3.00 to −2.75 | 1.644 | 41 | 1.638 | 40 | 1.774 | 1 |

The two halves agree to within about 0.035, except in the last row, where 2023–26 has a single observation.

## Step 1b: NIFTY lot sizes

Coded in `bull_put.nifty_lot`. A contract keeps its listed lot until it expires, and monthlies changed on a different expiry from weeklies.

| Change | Applies from |
|---|---|
| 75 (since 2015) to 50 | monthly 2021-07-29; weeklies from 2021-08-05 |
| 50 to 25 | effective 2024-04-26; first weekly 2024-05-02 |
| 25 to 75 | first weekly 2025-01-02; the 2025-01-30 monthly stays at 25; first monthly at 75 is 2025-02-27 |
| 75 to 65 | first weekly 2026-01-06 (last weekly at 75: 2025-12-23; last monthly: 2025-12-30) |

**Sources:**
- [Zerodha, Apr 2021](https://zerodha.com/marketintel/bulletin/291849/revision-in-lot-size-of-nifty-and-stock-fo-contracts)
- [NSE FAOP47854](https://archives.nseindia.com/content/circulars/FAOP47854.pdf)
- [Zerodha, Apr 2024](https://zerodha.com/marketintel/bulletin/375282/revision-in-lot-size-of-index-derivative-contracts-2)
- [Kotak, Nov 2024](https://www.kotakneo.com/bulletins/understanding-the-nse-circular-on-contract-size-revision-for-index-derivatives/)
- [Zerodha, Oct 2025](https://zerodha.com/marketintel/bulletin/429705/revision-in-lot-size-of-index-derivative-contracts-from-december-30-2025)

Lot size scales only the rupee figures; it never enters R.

## Step 1c: spread pricing check (entry days, no P&L)

**Method:**
- For each of the 69 scored trades: the model's credit for its own two contracts, priced at 15:30 on the entry day with NSE's close and the 15:25 VIX.
- Compared with the credit implied by the bhavcopy closes of those two contracts.
- Both legs were found for all 69 trades, and our expiry rule picked a listed expiry every time.

| Pricing | n | Median signed error, model − market (pts) | Median absolute error (pts) | Median absolute error, % of credit | 90th percentile |
|---|---|---|---|---|---|
| **With skew (scored)** | 69 | +3.0 | 4.4 | **6.9%** | 19.7% |
| Flat IV | 69 | +6.6 | 6.9 | 11.1% | 25.1% |

**Reading:**
- The median market credit was 63.4 points.
- The skew cuts the error by about a third.
- The model still overstates the credit by about 3 points per spread. That flatters every spread, real and placebo alike, so it doesn't bias the comparison between them. It does make the absolute R about 1.5 points too high (3 points on about 186 points of maximum risk).

## Step 1d: five worked spreads on placebo-pool entries (no real trade)

**How they were drawn:**
- 5 bars drawn with seed 20261123 from the placebo pool: the 11:00 and 15:00 entries on daily-uptrend days.
- None is also a real signal.
- Risk is fixed at 1.2 × ATR for these examples only.
- Costs: 3.0 points.

| Entry | Spot, short / long | Credit (max risk) | Spot exit | Debit | Net | R | ₹ (lot) |
|---|---|---|---|---|---|---|---|
| Fri 2020-07-10 15:00 | 10769 · 10700 / 10450 PE, exp 07-16 | 58.66 (191.34) | Mon 09:35, target | 33.40 | +22.26 | +11.6% | +1,669 (75) |
| Mon 2021-02-22 15:00 | 14733 · 14700 / 14450, exp 03-04 | 87.47 (162.53) | same day 15:25, stop | 106.12 | −21.65 | −13.3% | −1,624 (75) |
| Wed 2021-05-19 15:00 | 15058 · 15000 / 14750, exp 05-27 | 69.04 (180.96) | Thu 09:30, stop | 85.43 | −19.39 | −10.7% | −1,454 (75) |
| Thu 2025-10-16 15:00 | 25622 · 25550 / 25300, exp 10-28 | 64.10 (185.90) | Fri 09:20, stop | 80.86 | −19.76 | −10.6% | −1,482 (75) |
| Tue 2026-08-04 11:00 | 24578 · 24550 / 24300, exp 08-11 | 71.59 (178.41) | same day 13:10, stop | 95.31 | −26.72 | −15.0% | −1,737 (65) |

**What the cases show about the mechanics:**
- The spot stop is close to the entry (0.8–1.8 ATR), so the spread exits early on a stop, after a loss of about 20 points or −11% to −15% R.
- On a 2R target it gains about 20–25 points.
- That is roughly a symmetric bet. The time decay earned over a one- or two-bar hold is small next to the delta move: at entry the spread's delta is about +0.25.
- The full leg prices and IVs are printed by `python scripts/research/smc_ob_1h_bullput.py cases`.

## Step 2a: discovery (2026-11-23, written before confirmation was computed)

The spot trades match the call test's export: 69 of 69, with identical entries and exits.

**Discovery, 2019-02-11 to 2022-12-31: n = 37**

| Measure | Value |
|---|---|
| **Mean net return on maximum risk, R (3.0-pt costs)** | **+0.51%** (median −0.27%) |
| One-sided t | 0.27 |
| Winners (net > 0) | 18 of 37 |
| Mean credit / maximum risk / net (points) | 64.1 / 185.9 / +0.93 |
| Placebo (2,000 sets, pool 1,187 bars): mean of set means | +0.13% (5th–95th pct −3.85% to +4.05%) |
| **Placebo p (share of sets ≥ real)** | **0.439** |
| R with Stratified / Stressed costs, both legs | +1.07% / +1.73% |
| Net ₹ total at historical lots | +2,939 |

**Discovery verdict: FAIL.** The bars needed t ≥ 2.0 and placebo p ≤ 0.05; it got t 0.27 and p 0.439. H2 does not go on. Confirmation is computed and reported for the record only.

## Step 2b: confirmation (reported only; discovery had already failed)

**Confirmation, 2023-01-01 to 2026-11-20: n = 32**

| Measure | Value |
|---|---|
| **Mean net return on maximum risk, R (3.0-pt costs)** | **+0.36%** (median +1.46%) |
| One-sided t | 0.14 |
| Winners (net > 0) | 18 of 32 |
| Mean credit / maximum risk / net (points) | 68.3 / 181.7 / +0.77 |
| Placebo (2,000 sets, pool 1,074 bars): mean of set means | −1.92% (5th–95th pct −6.64% to +2.88%) |
| **Placebo p** | **0.211** |
| R with Stratified / Stressed costs, both legs | +0.29% / +1.49% |
| Net ₹ total at historical lots | −2,458 |

**Confirmation would also have failed its own bar** (p 0.211 against ≤ 0.10).

The rupee total is negative while mean R is positive. Rupees weight each trade by its lot, and the lots ran 25 to 75 over this span.

## Step 2c: diagnostics

**Variants** (mean R, one-sided t, placebo p with the same variant):

| Variant | Discovery | Confirmation |
|---|---|---|
| Scored: 250 wing, skew, frozen, 3.0 pts | +0.51% (t 0.27, p 0.439) | +0.36% (t 0.14, p 0.211) |
| Profit-take at 70% of credit | +0.60% (t 0.31, p 0.421, fired 2) | +0.36% (t 0.14, p 0.207, fired 0) |
| 300-point wing | +0.75% (t 0.44, p 0.434) | +0.68% (t 0.28, p 0.208) |
| Stratified costs, both legs | +1.07% (t 0.56, p 0.435) | +0.29% (t 0.11, p 0.220) |
| Stressed costs, both legs | +1.73% (t 0.91, p 0.436) | +1.49% (t 0.56, p 0.210) |
| Flat IV (no skew) | +1.30% (t 0.64, p 0.476) | +1.54% (t 0.55, p 0.212) |
| Calendar time convention | +1.51% (t 0.72, p 0.470) | +1.92% (t 0.68, p 0.176) |
| 252-day time convention | +0.70% (t 0.37, p 0.467) | +0.68% (t 0.26, p 0.224) |

**Holds by overnight gap, both periods** (mean R):

| Group | n | Spot pts | R (frozen) | R (calendar) | R (252-day) |
|---|---|---|---|---|---|
| intraday | 14 | -54.3 | -8.48% | -8.80% | -8.24% |
| weeknight only | 39 | +22.2 | +0.34% | +0.63% | +0.69% |
| weekend/holiday gap | 16 | +71.2 | +8.51% | +13.49% | +8.51% |
|   of which Friday entries | 12 | +81.0 | +8.68% | +13.83% | +8.79% |

**By entry window** (mean R):

| | Discovery n | Discovery R | Confirmation n | Confirmation R |
|---|---|---|---|---|
| 11:00 | 19 | -0.47% | 17 | -0.91% |
| 15:00 | 18 | +1.55% | 15 | +1.81% |

**By spot exit reason** (mean R):

| | Discovery n | Discovery R | Confirmation n | Confirmation R |
|---|---|---|---|---|
| stop | 13 | -11.65% | 12 | -13.54% |
| stop_gap | 0 | — | 1 | -31.87% |
| stop_gap_raised | 1 | -0.27% | 1 | -5.43% |
| stop_raised | 11 | +0.64% | 5 | +3.81% |
| target | 5 | +14.08% | 4 | +15.97% |
| target_gap | 2 | +17.41% | 1 | +19.20% |
| time | 5 | +11.69% | 8 | +13.65% |

**By year** (mean R):

| | Discovery n | Discovery R | Confirmation n | Confirmation R |
|---|---|---|---|---|
| 2019 | 8 | -4.11% | 0 | — |
| 2020 | 10 | +4.11% | 0 | — |
| 2021 | 12 | -0.18% | 0 | — |
| 2022 | 7 | +1.86% | 0 | — |
| 2023 | 0 | — | 8 | +0.65% |
| 2024 | 0 | — | 14 | +4.52% |
| 2025 | 0 | — | 6 | +2.12% |
| 2026 | 0 | — | 4 | -17.41% |

**Rupees at historical lot sizes** (3.0-pt costs): discovery +2,939 over 37 trades; confirmation -2,458 over 32 trades.

**Reading** (none of this is scored):
- **Every variant fails against its own placebo** (p 0.18–0.48). Neither a wider wing, the profit-take, a different cost model, flat IV nor a different time convention changes the picture.
- **The 70% profit-take almost never fires** (2 of 69). A one- or two-bar spot exit closes the spread long before 70% of the credit decays.
- **The spread is a spot-direction bet.**
  - Stops lose 11–14% R. Targets and time stops make 12–19%.
  - Weekend and Friday holds look good (+8.5% R frozen), because the spot rose +71 points on average in those 16 trades. That is the same post-hoc subset the call test flagged, it is convention-dependent (+13.5% under calendar time), and it is not a result.
- **2026 so far:** 4 trades, −17.4% R.

Per-trade export: `backtest_results/SMC-OB-1H_BULLPUT_QUANTOS_NSE_NIFTY_2026-11-23.csv` (69 trades: both legs' strikes, IVs and prices, credit, debit, maximum risk, R, rupees at historical lots).
