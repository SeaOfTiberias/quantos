---
title: ORB Options Scalping (Candidate 18)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: orb-options-scalping-candidate-18
candidate: "18"
family: intraday-options
instrument: index-options
status: retired
verdict: FAIL
first_tested: 2026-09-01
verdict_date: 2026-09-30
profit_factor: 0.85
sharpe: -1.14
trades: 1056
bar: "PF > 1 and Sharpe > 0.5 per index (Stratified costs), under the holdout-validated option-pricing time convention; numbers shown are NIFTY (BankNifty PF 0.82, Sharpe −1.30)"
headline: "Passed its original backtest on both indices, then failed on both once option premiums were priced with a convention calibrated to real quotes; closed and timers stopped 2026-09-30."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-opening-range-breakout-options-scalping-methodology-pre-comm, 2026-09-17-orb-options-scalping-backtest-results-candidate-18, 2026-09-17-orb-options-scalping-condition-mining-methodology-pre-commit, 2026-09-17-orb-condition-mining-results, 2026-09-17-orb-options-scalping-event-triggered-stop-out-spread-probe-s, 2026-10-13-opening-range-breakout-options-scalping-methodology-pre-comm, 2026-10-13-orb-options-scalping-backtest-results-candidate-18, 2026-10-13-orb-condition-mining-results, 2026-10-13-orb-options-scalping-arm-threshold-give-back-analysis-candid, 2026-10-13-orb-options-scalping-arm-threshold-methodology-pre-committed, 2026-10-13-orb-options-scalping-arm-threshold-grid-results-candidate-18, 2026-10-13-orb-options-scalping-net-profit-by-arm-bucket-candidate-18, 2026-10-13-candidate-18-orb-options-scalping-real-capital-tracked-equit, 2026-10-13-candidate-18-orb-options-scalping-capital-allocation-positio, 2026-10-13-candidate-18-fix-2-results-banknifty-expiry-day-entry-lag, 2026-10-13-orb-option-pricing-time-convention-calibration, 2026-10-13-candidate-18-under-the-calibrated-time-convention, 2026-10-13-orb-exit-policy-study-calibrated-pricing-futures, 2026-10-13-candidate-18-independent-verification-in-tradingview-2026-09, 2026-10-13-strategy-status-snapshot-2026-10-13
---

# ORB Options Scalping (Candidate 18)

> [!abstract] Compiled page
> First compiled 2026-09-17; rewritten 2026-10-13 from the sources listed in `compiled_from`. The 2026-10-13 sources cover the arm-threshold studies, capital work, re-pricing and closure. Context and retrieval only — rules in this layer never execute.

## Definition

A classic Opening Range Breakout, traded as NIFTY and BankNifty index options. It was the first candidate in the project to pass its own pre-registered cost bar on both indices, and the most-developed candidate before it failed. Premiums were never real traded prices: Fyers serves no intraday history for expired contracts, so every premium is a Black-Scholes reconstruction from the index level and India VIX `[[2026-09-17-opening-range-breakout-options-scalping-methodology-pre-comm]]`. How those reconstructed premiums decay over time is what ultimately decided the verdict.

## Mechanics

- **Range**: the first three 5-minute candles (09:15–09:30 IST).
- **Entry**: from the 4th candle, on the close: above the range → CALL, below → PUT. First signal only; filled at the next candle's open.
- **Exit**: stop on the opposite side of the range. Once price moves one range-width in favour, the stop trails the prior 3 candles' low/high and only ratchets. There is also a 25%-of-premium stop and a 15:20 IST flatten.
- **Contracts**: BankNifty nearest monthly; NIFTY nearest weekly with a DTE < 2 roll; ATM strike, fixed at entry.
- **Costs**: Clean, Stressed (+15 bps a leg), then several more realistic variants, ending at Stratified (locked-final), which gated the verdict.

`[[2026-09-17-opening-range-breakout-options-scalping-methodology-pre-comm]]`

## Verdict history

| Date | Step | Result |
|---|---|---|
| 2026-09-01 | Pre-registered backtest, Stratified | **PASS**. NIFTY: 1036 trades, PF 1.23, Sharpe 0.88. BankNifty: 1268 trades, PF 1.16, Sharpe 0.95 `[[2026-09-17-orb-options-scalping-backtest-results-candidate-18]]` |
| 2026-09-24 | Sharpe annualisation fix | Stratified Sharpe rose to 1.21 (NIFTY) and 1.27 (BankNifty); PF unchanged `[[2026-10-13-orb-options-scalping-backtest-results-candidate-18]]` |
| 2026-09-21 | Arm-threshold give-back (measurement only) | 29.1% of NIFTY and 35.4% of BankNifty trades never armed the trail and rode to the flatten, keeping 6% / 0% of their peak profit. Trades that armed kept about 73% `[[2026-10-13-orb-options-scalping-arm-threshold-give-back-analysis-candid]]` |
| 2026-09-21 | Profit by arm bucket | The armed third carries the entire profit (+345% of net on NIFTY, +410% on BankNifty). The non-armed two-thirds lose on their own (PF 0.16 / 0.18) `[[2026-10-13-orb-options-scalping-net-profit-by-arm-bucket-candidate-18]]` |
| 2026-09-21 | Arm-threshold grid {0.25, 0.5, 0.75, 1.0} × range width | No smaller multiplier passed on both indices; every one was worse than 1.0× `[[2026-10-13-orb-options-scalping-arm-threshold-grid-results-candidate-18]]` |
| 2026-09-24 | Capital-tracked equity curve and Kelly sizing | ₹50k wiped to about ₹2k (cliff); quarter to half Kelly with ≥ ₹1L was defensible. See [[capital-readiness-validation]] |
| 2026-09-30 | Fix 2 (BankNifty expiry day, entry lag) | Corrected 0-DTE pricing cut NIFTY to PF 1.12 / Sharpe 0.68 and BankNifty to 1.09 / 0.91, still passing. The pre-registered rule picked **skip** BankNifty expiry days (roll PF 1.06 vs skip 1.07, inside the 0.05 tie band) `[[2026-10-13-candidate-18-fix-2-results-banknifty-expiry-day-entry-lag]]` |
| 2026-09-30 | Time-convention calibration | Fitted on 472 real intraday quotes (2026-07-29 to 09-30). It beat the calendar convention on the holdout (MSE 0.0218 vs 0.0865). Frozen: session 1.85, weeknight 0.0, weekend 0.4 calendar-day equivalents `[[2026-10-13-orb-option-pricing-time-convention-calibration]]` |
| 2026-09-30 | **Re-run under the calibrated convention** | **FAIL**. NIFTY: 1056 trades, PF 0.85, Sharpe −1.14. BankNifty: 1223 trades, PF 0.82, Sharpe −1.30. The calendar convention would have passed both `[[2026-10-13-candidate-18-under-the-calibrated-time-convention]]` |
| 2026-09-30 | TradingView cross-check (NIFTY futures points) | TradingView independently reproduced the loss: gross edge of a few points a trade against about 9 points of round-trip cost, −₹4.45L net `[[2026-10-13-candidate-18-independent-verification-in-tradingview-2026-09]]` |
| 2026-09-30 | Exit-policy study (calibrated pricing, plus futures) | All five exit variants FAIL on both indices, as options and as futures `[[2026-10-13-orb-exit-policy-study-calibrated-pricing-futures]]` |

## Current status

**Closed. Live paper timers stopped 2026-09-30** `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`. Its descendant [[orb-entry-filter-candidate-18b]] stopped with it.

## Condition mining (feeds 18b)

A pre-registered 3-step test (n ≥ 30 per side, mining improvement, holdout confirmation) found two informative conditions, replicated on 2026-09-03 and 2026-09-21: `monday_or_friday` on NIFTY (holdout PF 1.22, Sharpe 1.62 in the re-run) and `big_gap` on BankNifty (holdout PF 1.53, Sharpe 2.18) `[[2026-10-13-orb-condition-mining-results]]`. Both were later tested in index points and labelled a pricing artifact (see [[orb-entry-filter-candidate-18b]]).

## Relation to other concepts

- [[breakout-1010-banknifty-candidate-15]] used the same synthetic Black-Scholes premiums. Its small edge carries the same pricing risk that this candidate's calibration exposed.
- The five-for-five failed vol-conditioning line ([[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]], [[event-proximity-vol]]) is the trap the condition-mining split was built to avoid.
- [[trend-day-filter-candidate-21]] and [[ema8-second-trade]] reused this candidate's futures cost model and index-points testing to check whether other intraday entries had a gross edge.
