# Close above R3 (ET Markets "Positive Breakout Third Resistance") as an F&O pick source: pre-registration (2026-11-17)

Written and committed before any history run. On 2026-11-17 the user showed the ET Markets screen "Current Price above Resistance 3", with TATACONSUM, ITC and MAXHEALTH on Nifty 50 and 11 names on Nifty 500. They asked to try it for the F&O picks, as a filter that "acts a little earlier than the Darvas one".

(The Pine "Pivot Compression Breakout" pre-registered earlier today, 0882245, is a different rule. It is still run and reported as registered.)

## The rule

ET's levels come from the previous session's high, low and close. They were checked on the 2026-11-13 bars of TATACONSUM and ITC; P, R1, R2 and R3 all match ET to the paisa:

| Level | Formula |
|---|---|
| P | (H + L + C) / 3 |
| R1 | 2P − L |
| R2 | P + (H − L) |
| R3 | P + 2(H − L) |
| S3 (mirror) | P − 2(H − L) |

ET's R3 is not the textbook H + 2(P − L).

The two signals are:
- **Long:** the daily close is above R3, and the previous close was not above its own R3.
- **Short (mirror, ET's "Negative Breakout Third Support"):** the daily close is below S3, and the previous close was not below its own S3.

## Universe and period

The same as the Pivot Compression test:
- every stock with F&O futures in the 2026-11-13 Fyers F&O master that is in the L1 store (218 stocks; a survivorship bias, partly offset by the same-universe benchmark);
- signals from 2021-01-01 to the last date with 15 sessions after it;
- split- and bonus-adjusted daily bars.

## Measures, scored per side

### A. Plain trade

- **Entry:** the next session's open.
- **Stop:** the signal bar's low − 0.1 × ATR(14) for longs (high + 0.1 × ATR for shorts).
- **Target:** 2R. It is fixed because there are thousands of events; the map-card target is too slow to compute for all of them.
- **Exit:** after 15 sessions, at the close. A bar that touches both the stop and the target counts as a stop.

### B. Ten-session excess return

The return from the next open to the close 10 sessions later, in the trade's direction, minus the equal-weight universe over the same span. Costs are 0.25%.

**Pass (per side):** all of these must hold:
- A: mean R ≥ +0.20, with n ≥ 150, and ≥ 0 in both halves (2021–23 and 2024–26);
- B: mean excess > 0 in both halves.

Anything else fails. It is reported as failed and not re-tuned this round.

### C. Earlier than Darvas (reported)

Longs only:
- the share of signals that are already a 55-day closing high;
- of the rest, the share that make one within 20 sessions, the median number of sessions, and the median gain from the signal close to that close.

### D. Context (reported, not for selection)

- Results split by whether NIFTY was above its 50-day mean.
- The same trade entered at the signal day's close instead of the next open, because the screen is read during the session.

### E. If a side passes

It still goes through the call-plan replay (the signal is the pick, and the map gives the entry) before it becomes a pick source.

## Result (run 2026-11-17, `scripts/research/r3_breakout_test.py`): FAIL, both sides

| Side | n | Mean R | 2021–23 | 2024–26 | 10-session excess after costs (2021–23 / 2024–26) |
|---|---|---|---|---|---|
| Long (close > R3) | 5719 | +0.11 | +0.18 | +0.02 | +0.14% / −0.07% |
| Short (close < S3) | 4056 | −0.09 | −0.15 | −0.05 | −0.10% / −0.37% |

The long side misses the +0.20R bar overall and fails the second half on both measures. The short side loses throughout.

### Context (reported, not scored)

- **Longs with NIFTY above its 50-day mean:** +0.14R, +0.18% excess. With NIFTY below it: +0.01R, −0.36%.
- **Entered at the signal close instead of the next open:**

  | Period | Mean R |
  |---|---|
  | Overall | +0.20 |
  | 2021–23 | +0.28 |
  | 2024–26 | +0.10 |

  This entry fades in the second half too.
- **Earlier than Darvas:** 44% of long signals are already a 55-day closing high. Of the other 3,176, 47% make one within 20 sessions: a median of 6 sessions later, at a median of 4.9% above the signal close. So the screen is earlier when a breakout follows, but half the time none follows.

Not re-tuned. Close-entry and the NIFTY-up subset are recorded as leads only. Neither clears the bar in 2024–26.

## Addendum (2026-11-17, user: "invert it for sells"): next-day study, descriptive (`scripts/research/pivot_shorts_nextday.py`)

The signals are a close below S2 (P − (H − L)), a close below S3, and the user's Pivot Compression rule mirrored for shorts. The universe is F&O stocks, 2021–26. For a short, a fall is the gain.

| Signal | Period | Next day close-to-close | 5 days | 10 days |
|---|---|---|---|---|
| Every stock-day (baseline) | 2021–23 | +0.13% | +0.66% | +1.30% |
| Every stock-day (baseline) | 2024–26 | +0.06% | +0.29% | +0.60% |
| Below S2 | 2021–23 | +0.04% | +0.51% | +1.32% |
| Below S2 | 2024–26 | +0.07% | +0.45% | +0.92% |
| Below S3 | 2021–23 | +0.26% | +0.42% | +1.47% |
| Below S3 | 2024–26 | +0.26% | +0.68% | +1.23% |
| Pivot Compression mirrored | 2021–23 | +0.27% | +0.89% | +1.49% |
| Pivot Compression mirrored | 2024–26 | +0.25% | +0.98% | +1.17% |

None of the three works as a short, in either half and whether or not the stock is in a downtrend (below a falling 200-SMA). The stocks bounce: after a close below S3 they beat the baseline over 10 days in both halves (+0.17% and +0.63%).

**Lead for a new pre-registration, not a result:** buy the S3 flush, a long after a close below S3. That's preferably where the close is back into a map demand zone or a swept level. It is the only pivot-screen pattern in this round that holds in 2024–26.
