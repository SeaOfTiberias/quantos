# Strategy Status Snapshot — 2026-10-13

Operational status of every strategy and trading aid that is live, paused
or switched off as of 2026-10-13. Research verdicts live in each
strategy's own methodology/results docs. This file records only what is
RUNNING and what was DECIDED about it, which no results doc captures.

Compiled 2026-10-13 by Claude Code from the operator's project records:
Claude's persistent project memory (which logs each decision the user
approved, with the date) plus the docs named below. Where a line rests on
a memory record rather than a committed doc, it says "(record)". Correct
this file by writing a NEW dated snapshot, not by editing this one.

## Running

| Strategy / aid | State | Since | Capital | Gate to the next step |
|---|---|---|---|---|
| Darvas ATR-stop, Bucket B (35–50% box width) | Paper trading on the VM, `dry_run: true` | first paper fills 2026-10-08 (record) | ₹5,00,000 paper; 9% of equity per position (`equity_fraction 0.09`) | User plan (2026-10-05): paper a few days, then ₹5L real. Flipping `dry_run` needs a fresh explicit go-ahead (record). Basis: out-of-sample PASS, docs/DARVAS_ATR_STOP_OOS_RESULTS.md |
| Candidate 11, momentum turnover | Quarterly paper walk-forward (`quantos-paper-momentum.timer`) | rebalanced 2026-09-30; next 2026-12-31 (record) | ₹10,00,000 paper | Needs 4 quarters of out-of-sample results before a verdict (record; docs/MOMENTUM_TURNOVER_WALKFORWARD_METHODOLOGY.md) |
| Trade watcher (discretionary aid) | Alerts-only exit manager for the user's manual option trades; Telegram only, no order code | 2026-10-07 (record) | n/a (manages the user's own positions) | Stage 2 (real stop orders at the broker) only with the user's explicit go-ahead after stage 1 proves itself (record) |
| F&O screener (discretionary aid) | Evening call/put candidate list to Telegram, 18:15 IST weekdays; no orders | first live run 2026-10-12 (record) | n/a | Review hit rate once 20–30 candidates exist (record) |

Darvas schedule (record): scan 18:00 IST, pre-open entries 09:02, stops /
exits / trailing 09:16. Universe: the 2026-09-30 Nifty 500 rebalance
(494 symbols).

## Switched off

| Strategy | Decision | Date | Note |
|---|---|---|---|
| Candidate 18, ORB options scalping | Closed; live timers stopped | 2026-09-30 (record) | Failed under the calibrated option-pricing time convention, docs/ORB_TIME_CONVENTION_RESULTS.md |
| Candidate 18b, ORB entry filter | Stopped with candidate 18 | 2026-09-30 (record) | Its prospective gate (due 2026-11-17) cannot accrue trades with the timers stopped. The index-points test labelled both filters a pricing artifact, docs/ORB_18B_FILTER_INDEX_POINTS.md |
| S8-3 weekly rotation dry run | `rotation.enabled: false` | 2026-10-12 (record) | Its dry run never tracked holdings, so its log is meaningless; the quarterly walk-forward above supersedes it |
| S8-3 real-capital rotation pilot | `rotation_pilot.enabled: false` | 2026-10-12 (record) | Timer already disabled since July, no positions |

## Closed this month without going live

| Candidate | Verdict | Date | Doc |
|---|---|---|---|
| Candidate 21, trend-day filter | FAIL | 2026-10-01 | docs/TREND_DAY_FILTER_RESULTS.md |
| EMA-8 second trade of the day | CLOSED (does not carry to BankNifty) | 2026-10-01 | docs/EMA8_SECOND_TRADE_RESULTS.md |
| IV-gated short premium (VRP follow-up) | FAIL | 2026-10-06 | docs/VRP_IV_GATED_RESULTS.md |
| StatArb residual ("straying duckling"), BankNifty | FAIL | 2026-10-13 | docs/STATARB_BANKNIFTY_RESULTS.md |
| StatArb residual, Nifty 50 | FAIL; residual / pairs mean-reversion family retired | 2026-10-13 | docs/STATARB_NIFTY50_RESULTS.md |

## Real capital

No strategy has traded real capital as of 2026-10-13.
