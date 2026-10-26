---
title: CCI(34)/EMA52 and SMA 5/40 as F&O Screener Filters
compiled: 2026-10-26
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: fno-screener-cci-sma-filters
candidate: "screener filter 2026-10-26"
family: trend
instrument: stock-futures
status: closed
verdict: MIXED
first_tested: 2026-10-26
verdict_date: 2026-10-26
profit_factor:
sharpe:
trades: 2612
bar: "kept n >= 100, both halves > 0, day-clustered t >= 2.7, beats unfiltered in both halves (9 tests)"
headline: "Both daily indicators agree with 93-99% of screener picks already, so as filters they remove almost nothing; 1 of 9 tests clears the bar on a 0.02%-per-trade change, so neither is worth adding."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-26-f-o-screener-cci-34-ema52-and-sma-5-40-as-filters-pre-regist, 2026-10-26-f-o-screener-cci-34-ema52-and-sma-5-40-filters-results
---

# CCI(34)/EMA52 and SMA 5/40 as F&O Screener Filters

> [!abstract] Compiled page
> Written from `[[2026-10-26-f-o-screener-cci-34-ema52-and-sma-5-40-as-filters-pre-regist]]` and `[[2026-10-26-f-o-screener-cci-34-ema52-and-sma-5-40-filters-results]]` on 2026-10-26. Context and retrieval only — rules in this layer never execute.

## Definition

Two daily indicators the user proposed as filters on [[fno-screener]] picks: CCI(34) above or below its own 52-period EMA, and the 5-day SMA above or below the 40-day SMA. They were tested alone and together. A call pick is kept only on a bullish reading and a put pick only on a bearish one, read on the signal day.

## Mechanics

The screener backtest's signals (FRESH and OUT ≤ 5 sessions, 2025-09-02 to 2026-10-23, 213 stocks), one trade per breakout episode. Three entry sets: calls at the next open, puts at the next open, and the put H1 retest (the screener's only measured edge). One exit, futures on the underlying: daily-close stop 0.75 ATR, emergency 1 ATR, 1R target, 10 sessions, 0.1% cost. Nine tests with a high bar (t ≥ 2.7) for that reason.

## Verdict

**MIXED, in effect a FAIL** `[[2026-10-26-f-o-screener-cci-34-ema52-and-sma-5-40-filters-results]]`. Eight of the nine tests fail. The one pass, SMA 5/40 on puts at the next open, removes 34 of 2,646 trades and moves the mean from +0.23% to +0.25% per trade (second half +0.03% to +0.04%). That clears the pre-registered bar, but the change is too small to matter.

| Entry set | Unfiltered mean | CCI rejects | SMA rejects | Both reject | Best kept mean |
|---|---|---|---|---|---|
| Calls, next open | −0.11% (n 2,310) | 168 (7%) | 28 (1%) | 196 (8%) | −0.11% |
| Puts, next open | +0.23% (n 2,646) | 142 (5%) | 34 (1%) | 174 (7%) | +0.25% (SMA) |
| Puts, H1 retest | +0.34% (n 1,672) | 116 (7%) | 26 (2%) | 141 (8%) | +0.34% |

Why: a screener breakout is already a trend move. The 5/40 SMA and the CCI signal line nearly always point the same way on the signal day, so there is little left for them to filter. On the H1 retest the trades CCI rejected did better (+0.42%) than the ones it kept (+0.33%).

## Relation to other concepts

Leaves [[fno-screener]] and the put H1 retest unchanged. The indicators were not tested as standalone entry signals.
