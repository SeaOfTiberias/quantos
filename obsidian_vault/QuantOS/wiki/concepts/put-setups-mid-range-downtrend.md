---
title: Put Setups (Mirrored Darvas vs Mid-Range Downtrends)
compiled: 2026-10-25
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: put-setups-mid-range-downtrend
candidate: "Put setups A / B-A / C (2026-10-25)"
family: breakout
instrument: stock-futures
status: closed
verdict: FAIL
first_tested: 2026-10-25
verdict_date: 2026-10-25
profit_factor:
sharpe:
trades: 667
bar: "ex5 > 0 with date-bootstrap 1.67% > 0, ex5 > 0 in each half, next-open 5-session short minus 0.10% > 0, n >= 100 on >= 40 days (C also > 0 in an out-of-window year)"
headline: "Counted once per episode, none of three put setups predicts a 5-session fall: the live mirrored-Darvas put rule (+0.06% excess, second half -0.32%), adding laggard names, and a failed-rally-in-a-downtrend setup all fail."
next_gate: "None this round. A failed test is not re-tuned. Screener put-list change needs the user's go-ahead."
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-25-put-setups-mirrored-darvas-vs-mid-range-downtrends-pre-regis
---

# Put Setups (Mirrored Darvas vs Mid-Range Downtrends)

> [!abstract] Compiled page
> Written from `[[2026-10-25-put-setups-mirrored-darvas-vs-mid-range-downtrends-pre-regis]]` on 2026-10-25. Context and retrieval only — rules in this layer never execute.

## Why it was tested

The [[fno-screener]]'s put side is its call-side Darvas logic run on price-inverted bars: a box breakdown near the 52-week low, in a downtrend, at most 5 sessions old. On 2026-10-23 ADANIENT, falling from the middle of its range (41% above its 52-week low, 12 sessions past a breakdown), was in none of its lists. The test asked whether the put side misses stocks falling from mid-range `[[2026-10-25-put-setups-mirrored-darvas-vs-mid-range-downtrends-pre-regis]]`.

## Variants

- **A, baseline**: the live put rule (inverted-bar Darvas, FRESH or OUT ≤ 5 sessions, downtrend, LAGGARD excluded).
- **B − A**: the entries A misses only because of the near-low (LAGGARD) gate.
- **C, failed rally**: below a falling 50-day SMA, a rally in the last 5 sessions touched min(EMA21, SMA50), a lower high than sessions t−30…t−6, and a close below the prior day's low.

One entry per stock per 10 sessions; short, 5-session hold, no stop; excess = move minus the same-day F&O universe average. 213 stocks, 2025-09-02 to 2026-10-16 `[[2026-10-25-put-setups-mirrored-darvas-vs-mid-range-downtrends-pre-regis]]`.

## Results

| Variant | n (days) | ex5 | bootstrap 1.67% | halves | tradable − 0.10% | Verdict |
|---|---|---|---|---|---|---|
| A baseline | 667 (209) | +0.06% | −0.26 | +0.36 / −0.32 | −0.01% | FAIL |
| B − A | 94 (57) | +0.01% | −0.98 | −0.12 / +0.21 | +0.27% | FAIL (also too small) |
| C failed rally | 1,442 (247) | +0.01% | −0.19 | −0.01 / +0.03 | −0.19% | FAIL |
| C, out-of-window year | 1,150 (178) | +0.12% | −0.15 | +0.25 / −0.19 | +0.22% | (check passed; C failed overall) |

`[[2026-10-25-put-setups-mirrored-darvas-vs-mid-range-downtrends-pre-regis]]`

## What it means

- The live put list has **no measured edge as a plain 5-session short**. An earlier screener backtest reported +0.24% for 2–5-session-old breakouts; it counted a stock again on every day it stayed broken down, which this test does not.
- It does not test the screener's separate **retest plan** for puts (limit at the box floor, daily-close stop, 1R target), which keeps its own earlier measurement.
- Not gating, recorded only: with Nifty below its EMA20, A averaged −0.11%.

## Relation to other concepts

Tests the put side of [[fno-screener]]. Same pre-registration discipline as [[surge-bull-put-credit]].
