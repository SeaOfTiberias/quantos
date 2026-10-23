# F&O screener entry search: pre-registration (2026-10-23)

Written before any of these tests ran. The year backtest (scripts/backtest_fno_screener.py, scripts/backtest_fno_exits.py) found:

- **Calls:** no edge. Breakouts lose after costs under every exit rule.
- **Puts:** a small edge, mostly in the first half of the year.

Variables already examined, so **excluded** here: setup state and age, OI build-up label, Nifty vs EMA20, momentum tier, box width, volume ratio, liquid contract, Darvas bucket.

## Fixed for every test

- **Signals:** FRESH or OUT ≤ 5 sessions, from ~/.quantos/bt_fno/outcomes.jsonl (Sep 2025 – Oct 2026), each side separately.
- **Exit:** the rule chosen earlier, not re-tuned here.
  - stop on a daily close 0.75 ATR(14) beyond the entry, plus an emergency stop 1 ATR further on touch
  - resting target at 1R
  - out at the close of session 10
- **Instrument and cost:** futures on the underlying, 0.1% round trip.
- **Halves:** split at the median signal date.

## Hypotheses

| ID | Entry rule | Idea |
|---|---|---|
| H1 retest | A limit at box level + 0.25 ATR (in the trade's direction), valid for 3 sessions after the signal. Enter only if touched; the entry is the limit price, or the open if a bar gaps through it. | Buy the retest, not the open. Today's TCS and PFC plans. |
| H2 relative strength | Enter at the next open only if the stock's 20-session return minus Nifty's is > +5 pp for calls, or < −5 pp for puts. | Trade the leaders and laggards against the market, not stocks moving with it. |
| H3 failed breakout | If the close falls back inside the box (beyond the level) within 2 sessions of a FRESH/OUT1 signal, trade the OPPOSITE side at the next open. | Failed breakouts trap the late buyers. |
| H4 no chase | Enter at the next open, except when that open gaps more than 0.5 ATR beyond the signal-day close in the signal's direction. | Gapping opens are exhaustion. |

## Pass criteria (each hypothesis, each side: 8 tests)

1. Mean return per trade > 0 in **both** halves.
2. Day-clustered t ≥ **2.7** (about p < 0.05 / 8).
3. At least **150** trades.

A pass also needs to beat that side's baseline (enter every signal at the next open, same exit), since the point is a *better* entry.

A hypothesis that fails is reported as failed and not re-tuned in this round.
