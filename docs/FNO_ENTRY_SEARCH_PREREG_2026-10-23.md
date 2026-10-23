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

---

## Results (run 2026-10-23, after the commit above)

`python scripts/backtest_fno_entries.py`: 5,431 FRESH/OUT ≤5 signals over 283 days, halves split at 2026-03-27. Fixed exit as above, futures, 0.1% round trip.

| Side | Test | n | Mean / trade | Won | t (by day) | H1 | H2 | Verdict |
|---|---|---|---|---|---|---|---|---|
| Calls | baseline (next open) | 2494 | −0.10% | 58% | −1.0 | −0.09 | −0.10 | — |
| Calls | H1 retest | 1502 | −0.04% | 61% | −0.4 | −0.02 | −0.06 | fail |
| Calls | H2 relative strength | 1623 | −0.09% | 59% | −0.9 | −0.06 | −0.11 | fail |
| Calls | H3 fade failed put breakdowns | 326 | −0.50% | 51% | −2.4 | −0.72 | −0.20 | fail |
| Calls | H4 no chase | 2406 | −0.10% | 58% | −1.3 | −0.08 | −0.12 | fail |
| Puts | baseline (next open) | 2875 | +0.23% | 67% | +2.3 | +0.42 | +0.00 | — |
| **Puts** | **H1 retest** | **1795** | **+0.33%** | **69%** | **+3.5** | **+0.41** | **+0.24** | **PASS** |
| Puts | H2 relative strength | 1427 | +0.13% | 65% | +1.5 | +0.33 | −0.11 | fail |
| Puts | H3 fade failed call breakouts | 278 | +0.01% | 62% | +0.4 | −0.24 | +0.30 | fail |
| Puts | H4 no chase | 2761 | +0.24% | 67% | +2.5 | +0.43 | +0.01 | fail |

**Robustness check (not part of the pre-registration).** Consecutive signals from one breakdown share a box level, so one limit fill can be counted several times. Counted once per fill, puts H1 still passes: n = 1,499, +0.31% per trade, 69% won, t = 3.2, halves +0.37 / +0.24. Calls H1 is −0.05%.

**What changed in the screener.** The put plan line is now the H1 entry:
- a sell limit 0.25 ATR under the broken floor, valid 3 sessions
- stop on a daily close 0.75 ATR above the fill
- resting 1R target
- out by session 10

Calls keep the same line but are labelled "no measured edge" (user, 2026-10-23: keep sending them and tune them out later).

**Limits.**
- Survivorship: today's F&O list is applied to the whole year.
- Futures only. The option wrappers lost on these signals (scripts/analyze_fno_backtest.py).
- One year of data. The live trade-idea log is the forward test.
