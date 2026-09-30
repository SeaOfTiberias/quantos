# ORB exit-policy study (calibrated pricing + futures)

Method, variants and the pre-registered bar (PF > 1, Sharpe > 0.5, t > 3): `scripts/backtest_orb_exits.py` docstring, committed before this run. V0 parity with signal.simulate_day verified on every day of real candles. 1 lot; BANKNIFTY expiry day skipped.

## NIFTY — options (calibrated pricing)

| Policy | N | Win | PF | Sharpe | Net Rs | t | Bar |
|---|---|---|---|---|---|---|---|
| V0 current | 1056 | 43% | 0.85 | -1.14 | -181,838 | -1.96 | FAIL |
| V1 arm at 0.5 RW | 1056 | 51% | 0.78 | -1.53 | -227,387 | -2.83 | FAIL |
| V2 breakeven at 0.5 RW | 1056 | 35% | 0.81 | -1.32 | -212,043 | -2.45 | FAIL |
| V3 time stop 60 min (if not armed) | 1056 | 43% | 0.76 | -1.70 | -181,433 | -3.11 | FAIL |
| V4 trail 1 RW from entry | 1056 | 38% | 0.84 | -1.25 | -187,736 | -2.12 | FAIL |

## NIFTY — futures (same signal, no time decay)

Futures bar: PF > 1 and t > 3 (Sharpe not computed on this ledger).

| Policy | N | Win | PF | Sharpe | Net Rs | t | Bar |
|---|---|---|---|---|---|---|---|
| V0 current | 1056 | 49% | 0.83 | — | -463,510 | -2.47 | FAIL |
| V1 arm at 0.5 RW | 1056 | 56% | 0.72 | — | -635,421 | -3.91 | FAIL |
| V2 breakeven at 0.5 RW | 1056 | 40% | 0.78 | — | -526,883 | -3.03 | FAIL |
| V3 time stop 60 min (if not armed) | 1056 | 44% | 0.60 | — | -676,152 | -5.91 | FAIL |
| V4 trail 1 RW from entry | 1056 | 42% | 0.82 | — | -420,340 | -2.51 | FAIL |

Exit reasons (NIFTY):
- V0 current: stop 368, trailing_stop 349, session_flatten 339
- V1 arm at 0.5 RW: trailing_stop 561, stop 312, session_flatten 183
- V2 breakeven at 0.5 RW: stop 312, trailing_stop 296, session_flatten 244, breakeven_stop 204
- V3 time stop 60 min (if not armed): time_stop 811, stop 125, trailing_stop 111, session_flatten 9
- V4 trail 1 RW from entry: trailing_stop 845, session_flatten 211

## BANKNIFTY — options (calibrated pricing)

| Policy | N | Win | PF | Sharpe | Net Rs | t | Bar |
|---|---|---|---|---|---|---|---|
| V0 current | 1223 | 42% | 0.82 | -1.30 | -371,312 | -2.76 | FAIL |
| V1 arm at 0.5 RW | 1223 | 51% | 0.74 | -1.72 | -449,307 | -4.26 | FAIL |
| V2 breakeven at 0.5 RW | 1223 | 37% | 0.79 | -1.37 | -373,832 | -2.96 | FAIL |
| V3 time stop 60 min (if not armed) | 1223 | 43% | 0.77 | -1.09 | -267,675 | -3.41 | FAIL |
| V4 trail 1 RW from entry | 1223 | 38% | 0.84 | -1.13 | -302,915 | -2.42 | FAIL |

## BANKNIFTY — futures (same signal, no time decay)

Futures bar: PF > 1 and t > 3 (Sharpe not computed on this ledger).

| Policy | N | Win | PF | Sharpe | Net Rs | t | Bar |
|---|---|---|---|---|---|---|---|
| V0 current | 1223 | 49% | 0.87 | — | -532,347 | -2.01 | FAIL |
| V1 arm at 0.5 RW | 1223 | 57% | 0.77 | — | -791,662 | -3.62 | FAIL |
| V2 breakeven at 0.5 RW | 1223 | 40% | 0.84 | — | -576,980 | -2.33 | FAIL |
| V3 time stop 60 min (if not armed) | 1223 | 45% | 0.71 | — | -692,197 | -4.48 | FAIL |
| V4 trail 1 RW from entry | 1223 | 42% | 0.89 | — | -385,039 | -1.61 | FAIL |

Exit reasons (BANKNIFTY):
- V0 current: session_flatten 468, stop 391, trailing_stop 364
- V1 arm at 0.5 RW: trailing_stop 627, stop 333, session_flatten 263
- V2 breakeven at 0.5 RW: session_flatten 346, stop 333, trailing_stop 315, breakeven_stop 229
- V3 time stop 60 min (if not armed): time_stop 982, stop 126, trailing_stop 97, session_flatten 18
- V4 trail 1 RW from entry: trailing_stop 908, session_flatten 315

