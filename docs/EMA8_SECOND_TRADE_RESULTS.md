# EMA 8 slope — second trade of the day vs the first

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
