# Candidate 18 (ORB Options Scalping) — Real Capital-Tracked Equity Curve

Methodology: docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. This report answers a different question than docs/ORB_SCALPING_RESULTS.md's pooled per-trade stats -- see this script's own module docstring (scripts/simulate_orb_scalping_equity_curve.py) for why those can't answer "what does real capital become." Uses the Stratified cost variant (locked-final, per ORB_SCALPING_RESULTS.md) for both indices, merged into ONE account sharing ONE cash pool, exactly 1 lot/trade (unchanged sizing), skipping any trade the account can't afford.

NIFTY window: 2022-06-01 to 2026-09-24 (1052 signals). BankNifty window: 2021-06-01 to 2026-09-24 (1283 signals).

## Results by starting capital

| Starting capital | Final equity | Total return % | CAGR % | Sharpe (daily) | Max DD % | Max DD ₹ | Trades taken | Trades skipped (insufficient cash) |
|---|---|---|---|---|---|---|---|---|
| ₹50,000 | ₹1,964.64 | -96.1% | -45.6% | -0.63 | 97.7% | ₹83,136.67 | 284 | 2051 |
| ₹55,000 | ₹512,806.30 | 832.4% | 52.2% | 0.87 | 93.8% | ₹84,537.23 | 2253 | 82 |
| ₹60,000 | ₹584,134.09 | 873.6% | 53.4% | 0.99 | 71.4% | ₹67,879.11 | 2333 | 2 |
| ₹100,000 | ₹623,388.68 | 523.4% | 41.1% | 1.07 | 50.2% | ₹67,879.11 | 2335 | 0 |
| ₹200,000 | ₹723,388.68 | 261.7% | 27.4% | 1.15 | 28.9% | ₹67,879.11 | 2335 | 0 |
| ₹500,000 | ₹1,023,388.68 | 104.7% | 14.4% | 1.17 | 12.7% | ₹67,879.11 | 2335 | 0 |

Sharpe here is the DAILY equity-curve calculation (sqrt(252) annualization over every trading day in the window, zero-return days included) -- NOT `core/backtest/parser.py`'s pooled per-trade annualization (see docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md's Track 1 finding that these are two genuinely separate calculations, same convention `core/rotation/equity_curve.py` and docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md's "equity-curve daily returns" line already use).

Max drawdown is bounded to [0, 100]% by construction (a real compounding account, not a sum of independent trade percentages) -- contrast docs/ORB_SCALPING_RESULTS.md's own trades, whose pooled stats don't report a drawdown at all for exactly this reason.

## Interpretation: ₹50,000 is not viable, and the failure mode is a cliff, not a slope

The headline: at ₹50,000 starting capital, this strategy is nearly wiped
out (final equity ₹1,965, max drawdown 97.7%) — but ₹55,000, just 10% more
capital, ends at ₹512,806 (+832%). The strategy's own edge is not in
question here (see docs/ORB_SCALPING_RESULTS.md's PASS verdict); what this
run shows is that **a fixed-1-lot options-scalping strategy has a hard
minimum viable capital, and ₹50,000 sits just below it, not comfortably
above it.**

Why a cliff and not a slope: single-lot premium cost for this strategy
runs ₹7,000–25,000/trade (BankNifty's 30-lot at ~₹250–800/share premium
is the more expensive leg). Once an early drawdown pushes cash below that
threshold, the account is **locked out of the very trades that would let
it recover** — it can't compound its way back because it can't afford to
open new positions, so a temporary drawdown becomes permanent. ₹50,000
crosses that lockout threshold during the first ~13 months of the window
(BankNifty-only, since NIFTY's own confirmed depth starts a year later,
2022-06-01) and never recovers: by 2022-06-01 cash is already down to
single-digit thousands, and 2051 of 2335 possible trades over the full
window are skipped as a direct result. ₹55,000+ has just enough buffer to
survive that same early drawdown and keep compounding.

## Raising capital to ₹500,000 solves survival, NOT return-scaling — read this before treating it as "the fix"

Every capital tier from ₹60,000 upward takes the **exact same 2,335
trades** and earns the **exact same absolute profit (~₹523,389)**, because
position sizing here is fixed at exactly 1 lot/trade, unchanged from the
original backtest's own convention — this script never scales lot count
with available capital (see this doc's own methodology line and the
adapter's module docstring). That's why final equity at every tier from
₹100,000 up is just "starting capital + ₹523,389", and why CAGR/total-
return% get WORSE as starting capital rises (₹100k: 41.1% CAGR; ₹200k:
27.4%; ₹500k: 14.4%) — a bigger account isn't earning more, it's just
diluting the same fixed absolute profit over a larger base, with the
surplus capital sitting completely idle.

So: **₹500,000 does buy safety** — it clears the ₹50k-55k lockout cliff
with a huge margin and behaves identically to ₹60,000+ in every respect
that matters for survival (2,335/2,335 trades taken, same max-DD in rupee
terms, ₹67,879). But it does **not** buy more profit than a much smaller
"safe" account (₹60,000–100,000) would, under this adapter's sizing
policy. If the goal is deploying ₹500,000 productively (not just avoiding
the wipeout), that requires a genuinely different, not-yet-built sizing
policy — e.g. scaling lot count with available capital, or running
multiple concurrent lots per signal — which is a real design decision
(discussed as an open question for the Darvas ATR-stop candidate in
docs/SHARPE_SWEEP_AND_EQUITY_CURVE_PLAN.md's Track 2 design notes) and
would need its own dedicated look, not an assumption smuggled in here.

**Practical reading**: ₹500,000 is a safe, cliff-clearing choice if the
plan is genuinely to trade this strategy 1 lot at a time and treat the
rest as a buffer/reserve. It is not, as currently modeled, a way to make
this strategy earn 5x what a ₹100,000 account earns — the strategy simply
doesn't ask for more than 1 lot's worth of capital at a time.

**Caveat on exact figures**: this backtest re-fetched live intraday data
during market hours (2026-09-24, run started ~13:01 IST) — a handful of
candles/trades at the very end of the window can differ by a few rupees
between runs made minutes apart on an open trading day. The cliff's
location (~₹50k–55k) and the fixed-sizing dilution effect are the
findings; the exact final-equity rupee figures are not meant to be
reproduced bit-for-bit on a later re-run.

## Skipped trades at ₹50,000 starting capital (first 20 of 2051)

| Date | Underlying | Premium needed | Cash available |
|---|---|---|---|
| 2022-06-01 | NIFTY | ₹12,016.55 | ₹6,216.97 |
| 2022-06-02 | NIFTY | ₹12,302.55 | ₹2,972.01 |
| 2022-06-03 | NIFTY | ₹10,032.10 | ₹9,790.54 |
| 2022-06-07 | BANKNIFTY | ₹24,520.50 | ₹21,715.98 |
| 2022-06-08 | BANKNIFTY | ₹18,216.60 | ₹14,955.06 |
| 2022-06-09 | NIFTY | ₹11,586.25 | ₹6,779.31 |
| 2022-06-10 | BANKNIFTY | ₹17,445.00 | ₹12,728.10 |
| 2022-06-14 | BANKNIFTY | ₹20,627.70 | ₹14,608.85 |
| 2022-06-15 | BANKNIFTY | ₹17,136.30 | ₹7,263.48 |
| 2022-06-16 | BANKNIFTY | ₹15,272.70 | ₹5,849.92 |
| 2022-06-17 | BANKNIFTY | ₹18,603.60 | ₹6,958.76 |
| 2022-06-20 | BANKNIFTY | ₹14,828.70 | ₹8,349.71 |
| 2022-06-21 | BANKNIFTY | ₹14,346.60 | ₹6,967.22 |
| 2022-06-22 | BANKNIFTY | ₹11,713.80 | ₹4,607.17 |
| 2022-06-23 | BANKNIFTY | ₹11,801.70 | ₹4,640.53 |
| 2022-06-24 | BANKNIFTY | ₹11,204.40 | ₹3,570.16 |
| 2022-06-27 | NIFTY | ₹7,198.75 | ₹3,984.73 |
| 2022-06-29 | NIFTY | ₹13,712.40 | ₹10,284.71 |
| 2022-06-30 | NIFTY | ₹12,412.40 | ₹9,203.50 |
| 2022-07-01 | NIFTY | ₹11,133.20 | ₹8,105.19 |
