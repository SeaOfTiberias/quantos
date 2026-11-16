# Pivot Compression Breakout as an F&O pick source: pre-registration (2026-11-17)

Written and committed before any history run. The user proposed this filter on 2026-11-17 as a long pick source that "acts a little earlier than the Darvas one", for the F&O picks.

## The rule, exactly as the user's Pine v2.0

The source is the TradingView script "Pivot Compression Breakout (5 EMA + 40 SMA + CCI 34)". The Python port is `pcb.py`, copied into `scripts/research/` with the results. All defaults are kept.

A daily bar is **setup** when all five conditions hold.

| Condition | Definition |
|---|---|
| Tight | \|this month's pivot − last month's pivot\| / this month's pivot ≤ 3%. A month's pivot is (H+L+C)/3 of the previous completed month. |
| EMA over pivot | The 5-EMA is above this month's pivot, and its 5-bar low is at or below the pivot. |
| EMA over 40 | The 5-EMA is above the 40-SMA, and it crossed above within the last 5 bars. |
| CCI | CCI(34, hlc3) is above its 52-SMA, and it crossed above within the last 5 bars. |
| Volume | Volume is above 1.2 × its 50-SMA, on a green bar. |

The **signal** is day 1: setup today and not yesterday. The rule is long only.

Worked check before the run: on TATACONSUM the port gives the November pivot as 990.27 and October's as 980.27. That matches the chart. The signal falls on 2026-11-03, matching the "BO" triangle. ITC also fires on 2026-11-03.

**Overlap with a failed test.** Two of the five conditions are the core of the 2026-11-07 rule (`CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md`, failed):
- the CCI(34) cross of its 52-SMA;
- the fast average over the monthly pivot.

The new parts are the 40-SMA cross, the volume bar and the tight-pivot condition. This test is run on the whole rule as written; it is not a re-tune of the failed one.

## Universe and period

- **Stocks:** every stock with F&O futures in the 2026-11-13 Fyers F&O master that is also in the L1 store.
  - This is a survivorship bias: today's F&O list. The benchmark is the same universe, which partly offsets it.
- **Period:** signals from 2021-01-01 to the last date with 15 sessions after it (data ends 2026-11-13).
- **Data:** split- and bonus-adjusted daily bars.

## Measures

### A. Plain trade (pass/fail)

The trade is the same one as the 2026-11-16 continuation test, so the two can be compared:
- **Entry:** the next session's open.
- **Stop:** the signal bar's low − 0.1 × ATR(14).
- **Target:** the map card's target (`call_plan.target` on the card through the signal day) if it is at least 1R away; otherwise 2R.
- **Exit:** after 15 sessions, at the close. A bar that touches both the stop and the target counts as a stop.

### B. Ten-session excess return (pass/fail)

The return from the next open to the close 10 sessions later, minus the equal-weight return of the universe over the same span. Costs are 0.25% per trade.

**Pass:** the rule is a pick source worth wiring only if all of these hold:
- A: mean R ≥ +0.20, with n ≥ 150, and mean R ≥ 0 in both halves (2021–23 and 2024–26);
- B: mean excess return after costs > 0 in both halves.

Anything else is a FAIL, reported as failed and not re-tuned this round.

### C. The "earlier than Darvas" claim (reported, not scored)

For each signal: does a 55-day closing-high breakout follow within 20 sessions? This is the breakout proxy used for Darvas in the 2026-11-16 continuation test. The report gives:
- the share of signals that get one;
- the median number of sessions until it;
- the median gain from the signal close to that breakout close (the "headroom").

### D. Context rows (reported, not for selection)

The same measures with one condition removed at a time: no volume, no 40-SMA, no tight pivot. They show which part carries the result. The rule that is scored stays the one above.

### E. If it passes

It still runs through the call-plan replay (the pick is the signal, and the map gives the entry) before it becomes a pick source. A pass here is not a deploy.

## Result (run 2026-11-17, `scripts/research/pivot_compression_test.py`): FAIL

| Version | n | Mean R | 2021–23 | 2024–26 | 10-session excess after costs (2021–23 / 2024–26) |
|---|---|---|---|---|---|
| **Rule as written** | 1066 | +0.14 | +0.26 | **0.00** | +0.27% / **−0.04%** |
| No volume condition (context) | 1794 | +0.12 | +0.23 | +0.02 | +0.41% / +0.08% |
| No 40-SMA condition (context) | 1401 | +0.12 | +0.24 | −0.01 | +0.25% / −0.31% |
| No tight-pivot condition (context) | 1834 | +0.11 | +0.24 | −0.03 | +0.42% / −0.18% |

The rule misses the +0.20R bar overall. It makes nothing in 2024–26 and is below the universe in that half. No single condition carries it: every drop-one version also fails 2024–26.

**Earlier than Darvas: yes.** 35% of signals are already a 55-day closing high. Of the other 692, 72% make one within 20 sessions: a median of 4 sessions later, at a median of 3.4% above the signal close. That beats the close above R3, which gets there 47% of the time. The rule spots breakouts early, but trading from the signal has not paid since 2024.

Not re-tuned. Same shape as the continuation starter (2026-11-16) and the R3 close: positive in 2021–23, flat in 2024–26.
