---
title: Darvas ATR-Scaled Stop, Bucket B
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/passed
strategy_id: darvas-atr-stop-bucket-b
candidate: "Darvas line 3 (ATR stop)"
family: breakout
instrument: equity-cash
status: live-paper
verdict: PASS
first_tested: 2026-09-23
verdict_date: 2026-10-05
profit_factor: 1.46
sharpe: 1.79
trades: 991
bar: "Out-of-sample 2016–2023: PF > 1 and Sharpe > 0.5, beats the equal-weight universe, week-bootstrap 90% CI lower bound > 0"
headline: "Only validated live strategy: in-sample pass, failed a falsification pass, then passed a frozen-rules 2016–2023 out-of-sample test; paper trading since 2026-10-08."
capital: "₹5,00,000 paper; 9% of equity per position"
next_gate: "User's explicit go-ahead to flip dry_run to real capital (plan: ₹5L real after a few days of paper)"
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-darvas-atr-scaled-stop-backtest-pre-committed-2026-09-23-bef, 2026-10-13-darvas-atr-scaled-stop-backtest-results, 2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p, 2026-10-13-darvas-atr-stop-falsification-pass, 2026-10-13-darvas-atr-stop-out-of-sample-2016-2023, 2026-10-13-strategy-status-snapshot-2026-10-13, 2026-10-13-quantos-full-project-state-for-external-review
---

# Darvas ATR-Scaled Stop, Bucket B

> [!abstract] Compiled page
> Written from `[[2026-10-13-darvas-atr-scaled-stop-backtest-pre-committed-2026-09-23-bef]]`, `[[2026-10-13-darvas-atr-scaled-stop-backtest-results]]`, `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]`, `[[2026-10-13-darvas-atr-stop-falsification-pass]]`, `[[2026-10-13-darvas-atr-stop-out-of-sample-2016-2023]]` and `[[2026-10-13-strategy-status-snapshot-2026-10-13]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

A Darvas weekly-box breakout on Nifty 500 stocks, restricted to boxes 35–50% wide (Bucket B). It uses the trailing stop/target of [[darvas-trailing-stop]], but the stop sits **2.0 × ATR(14)** below the box ceiling instead of a fixed 2%. It is the third link in the Darvas chain, and as of 2026-10-13 the only strategy in the project running live, on paper `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

## Mechanics

- **Why ATR**: in the trailing-stop backtest, 87–90% of trades exited by stop and only 10–12% by target, and that small tail of target hits carried the whole positive result. A fixed 2% buffer shakes out a stock whose normal daily range is 4–5% just as fast as a calm one `[[2026-10-13-darvas-atr-scaled-stop-backtest-pre-committed-2026-09-23-bef]]`.
- **Stop**: `box_ceiling − 2.0 × ATR(14)`, using the scanner's own `_atr()` helper (Wilder, 14 days). It is recomputed whenever a higher box confirms and is only ever raised. 2.0× is the Chandelier-exit convention, picked as an external anchor; no sweep across multipliers was run.
- **Target**: unchanged, the measured move (ceiling + box height), trailed to each new box.
- **Everything else** is copied from [[darvas-trailing-stop]]: the point-in-time Nifty 500 universe, 2023-09-22 to 2026-09-22, the 2026-02-15 split, delivery costs plus Stressed, and no time stop.
- **Live sizing**: about 9% of current equity per position, the grid-searched "portfolio Kelly" fraction `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]`.

## Verdict history

| Date | Test | Result |
|---|---|---|
| 2026-09-24 | In-sample pre-registered backtest | **PASS**: Bucket B mining 210 trades, PF 1.15, Sharpe 0.68; holdout 67 trades, PF 1.16, Sharpe 0.62 (Stressed). The control bucket fails holdout, as required `[[2026-10-13-darvas-atr-scaled-stop-backtest-results]]` |
| 2026-09-24 | Bug-fix re-run (target-trail gating) | Zero of 2,280 trades changed. Fable's caution stands: mining and holdout Sharpe both sit just above 0.5, so read this as fit for a discretionary panel, not proven for capital `[[2026-10-13-darvas-atr-scaled-stop-backtest-results]]` |
| 2026-09-25 | Capital-tracked equity curve | No wipeout cliff (worst drawdown about 50%). At about 9% per trade, full-window Sharpe 0.24–0.35, max drawdown 10–16%. On the holdout alone that fraction was roughly flat (−2.8% to +0.7%) `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]` |
| 2026-10-01 | Falsification pass | **KILLED** on 2 of 3 kill conditions: without the top 5% of trades the total goes from +192.8% to −233.1%, and the week-bootstrap 90% CI of the mean is −0.76% to +2.10% `[[2026-10-13-darvas-atr-stop-falsification-pass]]` |
| 2026-10-05 | Out-of-sample 2016–2023, frozen rules | **PASS**: 991 trades, PF 1.46, Sharpe 1.79, mean +2.16% a trade, +0.70% over the equal-weight universe, bootstrap CI +1.23% to +3.08% `[[2026-10-13-darvas-atr-stop-out-of-sample-2016-2023]]` |

The out-of-sample run used NSE bhavcopy data including later-delisted names and a liquidity-ranked top-500 universe (1,048 symbols, 7,130 trades) `[[2026-10-13-darvas-atr-stop-out-of-sample-2016-2023]]`.

### Post-run scrutiny of the out-of-sample result (not part of its verdict)

- The first printed Sharpe was 92.8, caused by trades listed by symbol rather than date. After the fix, the in-sample Bucket B Sharpe moves to 0.55 (mining, only just passing) and 0.63 (holdout). Overlapping trades are still not independent, so the Sharpe remains overstated.
- Most of the raw return is the market (the equal-weight universe returned 14.7% a year). Bucket B's excess is +0.70% a trade, with a 90% CI of **+0.03% to +1.36%**: above zero, but only just. The excess was positive in 6 of 8 entry years.
- Raw losing years were 2018 (−4.12% a trade), 2019 (−0.88%) and 2022 (−0.12%). Expect drawdowns when mid- and small-caps fall.

`[[2026-10-13-darvas-atr-stop-out-of-sample-2016-2023]]`

## Current status

Paper trading on the VM with `dry_run: true`, ₹5,00,000 paper capital, 9% of equity per position. First paper fills came on 2026-10-08. Scans run at 18:00 IST, pre-open entries at 09:02, and stops/exits/trailing at 09:16, on the 2026-09-30 Nifty 500 rebalance (494 symbols). The user's plan is to paper trade for a few days and then go to ₹5L real; flipping `dry_run` needs a fresh, explicit go-ahead. No real capital has been deployed `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

## Relation to other concepts

- The third single-variable step after [[darvas-box-width]] (static exit, failed) and [[darvas-trailing-stop]] (trailing exit, breakeven). Only the stop distance changed between this test and the previous one.
- Its passing in-sample result was the second candidate to clear the project's PF/Sharpe screen, after [[orb-options-scalping-candidate-18]]. The project-state review used it as the example of a pass that still lacked [[capital-readiness-validation]] `[[2026-10-13-quantos-full-project-state-for-external-review]]`.
- The Darvas signal itself traces back to [[darvas-sepa-s7-3]], which failed with its original fixed-percentage stop.
