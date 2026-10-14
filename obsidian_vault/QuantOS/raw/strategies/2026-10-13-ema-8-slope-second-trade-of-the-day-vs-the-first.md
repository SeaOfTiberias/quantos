---
title: 'EMA 8 slope — second trade of the day vs the first'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\EMA8_SECOND_TRADE_RESULTS.md'
checksum: 5fdbb8259852fb8635a2181e6d8a09f71b3f9fe73193a568630a704b0325ff07
body_checksum: c9c2400975e34a3f7310abc37996fde9bdec01e57d08d3504096ebda37fafb15
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# EMA 8 slope — second trade of the day vs the first

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\EMA8_SECOND_TRADE_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Pre-registered in `scripts/test_ema8_second_trade.py` (committed before this run). Index points in the trade's direction; 1.5 x ATR(14) trail; max 2 trades/day; 20-EMA filter on (as the user's TV run).

## Step 0 — parity with TradingView (NIFTY)

TV trades 2139, Python trades 2140, matched by entry time + direction: **84.9%** (gate 80%).

| Trade of day | N | Mean pts | t (pts) |
|---|---|---|---|
| 1 | 1071 | -1.05 | -0.90 |
| 2 | 1069 | +2.84 | 2.37 |
Replica trade-1/2 means within 1.0 pt of TV's {1: -1.52, 2: 3.06}: **yes**


## BANKNIFTY — the test

| Trade of day | N | Mean pts | t (pts) |
|---|---|---|---|
| 1 | 1321 | -6.87 | -2.48 |
| 2 | 1313 | -0.32 | -0.11 |

- H: trade 2 minus trade 1 = +6.55 pts, one-sided p = 0.050 -> holds
- Economic bar: trade 2 alone as futures, mean net Rs-487/trade (t -5.67) -> does NOT clear

**CLOSED: the second-trade effect does not carry to BANKNIFTY**
