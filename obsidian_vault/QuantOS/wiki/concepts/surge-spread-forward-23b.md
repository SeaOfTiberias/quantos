---
title: Wide Surge Bull Call Spreads, Forward Paper Test (Candidate 23b)
compiled: 2026-10-15
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/open
strategy_id: surge-spread-forward-23b
candidate: "23b"
family: momentum
instrument: stock-options
status: live-paper
verdict: OPEN
first_tested: 2026-10-15
verdict_date:
profit_factor:
sharpe:
trades:
bar: "After ≥ 60 closed forward trades at real bid/ask: PF > 1, Sharpe > 0.5, and mean return on risk > 0 with date-clustered t ≥ 1.5"
headline: "Forward paper test of one fixed wide bull call spread (L2W4) on +5% surges below the 52-week high, filled at live bid/ask at 15:15 IST; separates a real 2025–26 change from best-of-16 luck."
capital: "none (paper; read-only logger, no order code)"
next_gate: "60 closed paper trades (about 2½–3 months at ~25 surges a month); no P&L reported before then"
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-15-candidate-23b-wide-bull-call-spreads-on-surges-forward-paper, 2026-10-15-candidate-23b-part-c-surge-follow-through-persistence-result
---

# Wide Surge Bull Call Spreads, Forward Paper Test (Candidate 23b)

> [!abstract] Compiled page
> Written from `[[2026-10-15-candidate-23b-wide-bull-call-spreads-on-surges-forward-paper]]` and `[[2026-10-15-candidate-23b-part-c-surge-follow-through-persistence-result]]` on 2026-10-15. Context and retrieval only — rules in this layer never execute.

## Definition

The follow-up to [[surge-spread-candidate-23]]. Candidate 23's bull call spreads failed on 2020–24 data. In the 2025–26 holdout, wide structures made money at the measured spread cost, but that was found by looking at all 16 structures on the holdout, so the holdout cannot confirm it. 23b tests one structure, fixed in advance, on **new data only**. It also replaces the assumed bid-ask cost with **real quotes** `[[2026-10-15-candidate-23b-wide-bull-call-spreads-on-surges-forward-paper]]`.

## Mechanics (Part A, the verdict)

- **Structure**: L2W4 only. The long call is 2 listed strikes above ATM and the short call 4 strikes above the long. It was the strongest wide structure in the cleaned 2025–26 holdout.
- **Daily run at 15:15 IST** (read-only):
  - **Trigger**: an F&O stock up ≥ 5% on the Fyers quote and not at a fresh 52-week closing high, with a 10-session cooldown per symbol.
  - **Expiry**: the nearest one with ≥ 5 weekdays left. The derived NSE calendar cannot see future holidays.
  - **Fills**: buy the long leg at the ask, sell the short at the bid. Both legs need a two-sided quote, and the real debit must sit between 0 and the width.
- **Exit**: after 8 sessions, or on the last session before expiry, at the quotes (long at the bid, short at the ask). Sessions are counted only on days with a NIFTY daily bar.
- **Verdict**: once ≥ 60 trades have closed, PF > 1, Sharpe > 0.5 and mean return on risk > 0 with t ≥ 1.5, using real fills plus statutory costs. **No P&L is reported before then.**

`[[2026-10-15-candidate-23b-wide-bull-call-spreads-on-surges-forward-paper]]`

## Market conditions

- **Part B (descriptive)**: each run logs the NIFTY change, India VIX, F&O breadth and the number of surges, and each trade carries that day's state. At the verdict, results are split by state for information only.
- **Part C (persistence check, run before Part A)**: does the last 3 months' surge follow-through predict the next month's? **FAIL** on 2020-05 to 2024-12 (56 months): Spearman 0.149, one-sided p 0.137. Months after positive follow-through averaged +0.25% against +0.31% after non-positive. **So no market-state gate is used.** About 56 points gives low power, so this is no evidence of persistence rather than proof of none `[[2026-10-15-candidate-23b-part-c-surge-follow-through-persistence-result]]`.

## Relation to other concepts

- Descends from [[surge-spread-candidate-23]], whose 2025–26 holdout motivated it.
- Its no-peeking gate and forward-only verdict follow the same discipline as the paper walk-forward of [[momentum-turnover-candidate-11]].
- Part C's failure fits this project's record that conditioning on market state does not predict reliably (see the vol-conditioning line in [[strategy-search]]).
