---
title: NIFTY EMA9/21 Options Strategy (S8-4)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-s8-4-nifty-ema9-21-options-strategy-backtest, 2026-09-17-s8-2-fyers-automation-trade-history-retrospective
---

# NIFTY EMA9/21 Options Strategy (S8-4)

> [!abstract] Compiled page
> Written from `[[2026-09-17-s8-4-nifty-ema9-21-options-strategy-backtest]]` and `[[2026-09-17-s8-2-fyers-automation-trade-history-retrospective]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A backtest of the exit-rule design behind the live discretionary NIFTY options strategy this project's execution automation was originally built around (EMA9/EMA21 crossover entries, a fixed ±₹2000 P&L cap or 3:10pm time-stop as the baseline exit). Grounded in a real retrospective of 26 actual same-day round trips (`[[2026-09-17-s8-2-fyers-automation-trade-history-retrospective]]`) before the backtest ran, rather than a hand-picked assumption: that retrospective found 6 of 26 real trades were held well past the point their own entry signal had already reversed, and 4 of 26 gave back over 20% of their peak favorable move before exit.

## Mechanics

Option P&L is approximated as `delta(0.45) × underlying point move × lot size (65)`, held at a constant delta for each trade's life — not a real options pricing model (no historical NIFTY option chain/IV data exists in this project's data source). The 0.45 delta and lot size 65 are grounded in the real S8-2 trade retrospective, not hand-picked. Three exit variants tested against the same entry signal: the live baseline (±₹2000 cap or 3:10pm), an ATR-based trailing stop, and a faster invalidation exit (close on signal reversal).

## Verdict

**FAIL**, and none of the three variants clears the bar `[[2026-09-17-s8-4-nifty-ema9-21-options-strategy-backtest]]`:

| Variant | Trades | Win rate | Profit factor | Sharpe | Net % |
|---|---|---|---|---|---|
| Baseline (live strategy) | 693 | 49% | 1.00 | 0.03 | +37.0% |
| Trailing stop (ATR) | 774 | 51% | 0.92 | -0.29 | -523.8% |
| Faster invalidation | 818 | 35% | 1.05 | 0.19 | +313.6% |

The baseline — the strategy actually running live at the time — sits almost exactly at breakeven on profit factor with a Sharpe near zero. Neither proposed fix (trail tighter, exit faster on signal failure) clears the bar either; the trailing-stop variant is meaningfully worse.

## Relation to other concepts

Read the relative comparison between the three variants as the signal, not the absolute rupee figures — the delta-approximated P&L is disclosed as directionally informative, not an exact pricing model, unlike [[orb-options-scalping-candidate-18]] and [[goodnight-scalper-candidate-20]]'s full Black-Scholes reconstructions.
