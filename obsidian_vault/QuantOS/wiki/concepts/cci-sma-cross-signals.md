---
title: CCI(34)/EMA52 and SMA 5/40 Crosses as Standalone Signals
compiled: 2026-10-26
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: cci-sma-cross-signals
candidate: "cross signals 2026-10-26"
family: trend
instrument: stock-futures
status: closed
verdict: FAIL
first_tested: 2026-10-26
verdict_date: 2026-10-26
profit_factor:
sharpe:
trades: 1973
bar: "vs-NIFTY mean per trade: n >= 150, > 0 in both halves, day-clustered t >= 2.7 (12 tests)"
headline: "Trading daily CCI-over-its-EMA52 or 5/40 SMA crosses on 213 F&O stocks loses money before or after adjusting for NIFTY; 0 of 12 tests pass, and the shorts lose clearly."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-26-cci-34-ema52-and-sma-5-40-crosses-as-standalone-signals-pre, 2026-10-26-cci-34-ema52-and-sma-5-40-crosses-as-standalone-signals-resu
---

# CCI(34)/EMA52 and SMA 5/40 Crosses as Standalone Signals

> [!abstract] Compiled page
> Written from `[[2026-10-26-cci-34-ema52-and-sma-5-40-crosses-as-standalone-signals-pre]]` and `[[2026-10-26-cci-34-ema52-and-sma-5-40-crosses-as-standalone-signals-resu]]` on 2026-10-26. Context and retrieval only — rules in this layer never execute.

## Definition

The user's two daily indicators used as entries in their own right, after they added nothing as screener filters ([[fno-screener-cci-sma-filters]]). The signals are a fresh cross of SMA5 over or under SMA40, of CCI(34) over or under its 52-EMA, and the day both first agree. Long on a bullish cross, short on a bearish one.

## Mechanics

213 F&O stocks, daily bars, entries 2024-11-28 to 2026-10-23, at the next open. Two exits: the opposite cross (60-session cap), or the screener's fixed daily rules (0.75 ATR daily-close stop, 1 ATR emergency, 1R target, 10 sessions). 0.1% cost. Each trade is judged net of NIFTY's move over the same days, so market drift isn't counted as skill.

## Verdict

**FAIL, 0 of 12** `[[2026-10-26-cci-34-ema52-and-sma-5-40-crosses-as-standalone-signals-resu]]`.

| Signal / exit / side | n | Raw mean | vs NIFTY | t |
|---|---|---|---|---|
| SMA / opposite / long | 1,973 | −0.03% | +0.63% | +1.3 |
| SMA / opposite / short | 1,878 | −1.31% | −0.82% | −5.2 |
| SMA / fixed / long | 1,897 | −0.34% | −0.21% | −2.6 |
| CCI / opposite / long | 5,298 | −0.13% | +0.13% | −0.3 |
| CCI / opposite / short | 5,274 | −0.57% | −0.45% | −3.4 |
| Both / opposite / long | 3,694 | −0.32% | +0.15% | +0.6 |
| Both / opposite / short | 3,505 | −0.55% | −0.45% | −4.0 |

The full table, including the fixed-exit shorts (all about −0.05% vs NIFTY), is in the results source. The closest call, SMA long with the opposite-cross exit, beats NIFTY by 0.63% per trade but still loses money outright (−0.03%), and its t of 1.3 is far from the bar. Shorts on a bearish cross lose clearly (t −3.4 to −5.2): over this period, stocks that crossed down tended to recover.

## Relation to other concepts

Same indicators as [[fno-screener-cci-sma-filters]]. Like [[nifty-ema-options-s8-4]], a moving-average cross on its own carries no edge in this data.
