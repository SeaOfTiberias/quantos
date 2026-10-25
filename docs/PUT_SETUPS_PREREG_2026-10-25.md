# Put setups: mirrored Darvas vs mid-range downtrends. Pre-registration (2026-10-25)

Written and committed before any of these tests ran. No outcome below has been computed.

## Why

The F&O screener's put side is the call side's Darvas logic run on price-inverted bars: a box breakdown, within the top two-thirds of the universe by proximity to the 52-week low, in a downtrend (EMA9 < EMA21), at most 5 sessions after the breakdown. On 2026-10-23 ADANIENT (−2.9%, −8.6% in a month) was in none of the screener's lists. It broke below its 2,830 box floor 12 sessions earlier and is 41% above its 52-week low, so the near-low ranking drops it (LAGGARD). The question is whether the put side misses a real setup: **stocks falling from the middle of their range, not near their lows.**

Disclosed: ADANIENT, one stock on one day, motivated variant C. Nothing else about outcomes has been looked at.

## Data and conventions (unchanged from `scripts/backtest_fno_screener.py`)

- **Bars**: `~/.quantos/bt_fno/bars.pkl`, Fyers daily bars for today's 213 F&O stocks and NIFTY, 2024-07-25 to 2026-10-23. Survivorship (today's list applied throughout) and unadjusted corporate actions (forward moves over 25% dropped) are known limits.
- **Signal window**: the sessions where A and B can run (≥ 275 bars of history), **2025-09-02 to 2026-10-16**, the last session with 5 forward sessions.
- **Forward move**, signed for a put (a fall is positive), at 1, 3 and 5 sessions:
  - `cc` = close of signal day t to close of t+h;
  - `oc` = open of t+1 to close of t+h, the tradable entry;
  - `ex` = `cc` minus the same-day equal-weight average `cc` of the whole universe (sign-adjusted), which strips the market's move.
- **One entry per episode.** A symbol's first qualifying session counts. The same symbol and variant can't count again for 10 sessions, so a stock that qualifies on five straight days counts once. Each variant's n is therefore close to independent trades.
- **Halves**: entries split at the median signal date of the window.

## The three variants (PE side only)

**A, baseline (the live put rule)**
- `core/discovery/momentum_shortlist.build_shortlist` on inverted bars, `core/fno_screener/screener.setup_rank(entry, 5)` ∈ {0, 1}.
- That means a FRESH breakdown, or one at most 5 sessions old; downtrend required; LAGGARD tier excluded.
- NEAR (watch) is not an entry.

**B, A without the near-low gate**
- Same as A, but the LAGGARD tier is allowed. The downtrend gate and the 5-session limit stay.
- The question is the **increment**: B's entries that A doesn't have (B − A, LAGGARD names only). It is judged on its own.

**C, failed rally in a downtrend** (new; real bars, no inversion). On session t, all of:
1. The 50-day SMA is falling: SMA50(t) < SMA50(t−10).
2. Close(t) < SMA50(t).
3. **The rally tested resistance**: in t−5 … t−1 there is a session whose high ≥ min(EMA21, SMA50) of that session.
4. **Lower high**: the highest high of t−5 … t−1 < the highest high of t−30 … t−6.
5. **Trigger**: Close(t) < Low(t−1).

C makes no reference to the 52-week low or to Darvas boxes. Its overlap with A is reported.

## Pass bar

Three variants are judged (A, B − A, C), so the bootstrap bound is the **1.67th percentile** (one-sided 0.05 / 3). The bootstrap resamples by signal date, 10,000 draws, seed 20261025.

A variant passes only if all of these hold:
1. **Mean `ex5` > 0**, and its bootstrap 1.67th percentile > 0.
2. Mean `ex5` > 0 **in each half**.
3. **Tradable**: mean `oc5` (raw, short futures from the next open, held 5 sessions) minus **0.10% round-trip cost** > 0.
4. **Size**: at least 100 entries on at least 40 distinct signal days.
5. **C only, an extra out-of-window year**: C needs just 60 bars, so it also runs on **2024-10-23 to 2025-09-01**. Mean `ex5` must be > 0 there as well. A and B can't run on that period.

Fixed 5-session hold, no stop: the same convention as the screener backtest that set today's rules. Not a full exit test.

**Reported, not gating:**
- each variant split by Nifty above or below its EMA20;
- `ex1` and `ex3`;
- win rate;
- the bear put debit spread outcome at bhavcopy closes (long ATM, short at 1 EM5) for any variant that passes, from `scripts/analyze_fno_backtest.py spreads`'s method.

## What each result leads to

- **A fails**: the live put list loses its measured basis. Reported as such; the screener's put side is flagged in the vault, and changes only on the user's go-ahead.
- **B − A passes**: the LAGGARD exclusion is dropped for puts, after the user's go-ahead.
- **C passes**: C is added to the screener as a separate put list ("failed rally"). It goes through the trade-idea log and paper first, then to the user.
- **Anything that fails is reported as a fail.** Thresholds and definitions are not re-tuned in this round.

Code: `scripts/backtest_put_setups.py`. Results are appended to this file.

## Results (2026-10-25)

Run by `scripts/backtest_put_setups.py`; raw numbers in `~/.quantos/bt_fno/put_setups.json`. Halves split at 2026-03-24. `ex` = % move in the put's favour minus the same-day universe average.

| Variant | n | days | ex1 | ex3 | ex5 | ex5 boot 1.67% | ex5 H1 | ex5 H2 | oc5 − 0.10% | win5 | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A baseline | 667 | 209 | -0.029 | 0.126 | 0.056 | -0.258 | 0.359 | -0.32 | -0.005 | 51.4% | **FAIL** |
| B-A LAGGARD increment | 94 | 57 | -0.249 | -0.194 | 0.01 | -0.982 | -0.115 | 0.212 | 0.266 | 51.1% | **FAIL** |
| C failed rally | 1442 | 247 | -0.02 | 0.068 | 0.012 | -0.188 | -0.005 | 0.03 | -0.186 | 52.1% | **FAIL** |

C out-of-window (2024-10-23..2025-09-01): n 1150 on 178 days, ex5 0.115, halves 0.252 / -0.193, oc5 − 0.10% 0.217. C entries with an A entry for the same stock in the 5 sessions before: 15.6%.

Checks failed per variant:

- **A baseline**: 1 ex5>0 and boot lo>0, 2 both halves >0, 3 oc5 - 0.10% > 0. Nifty above EMA20: ex5 0.442 (n 206); below: -0.112 (n 461).
- **B-A LAGGARD increment**: 1 ex5>0 and boot lo>0, 2 both halves >0, 4 n>=100 on >=40 days. Nifty above EMA20: ex5 1.223 (n 19); below: -0.297 (n 75).
- **C failed rally**: 1 ex5>0 and boot lo>0, 2 both halves >0, 3 oc5 - 0.10% > 0. Nifty above EMA20: ex5 0.196 (n 639); below: -0.132 (n 803).
