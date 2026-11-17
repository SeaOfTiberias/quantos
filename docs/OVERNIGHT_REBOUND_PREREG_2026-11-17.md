# Index overnight rebound after a NIFTY sell-off day: pre-registration (2026-11-17)

Written and committed before any run. The user approved it on 2026-11-17 ("go").

**Where it came from.** The S3 flush test of the same day (`S3_FLUSH_LONG_PREREG_2026-11-17.md`, reported, not scored) found that F&O stocks closing below S3 on days NIFTY fell more than 1% made +0.44R (2021–23) and +0.43R (2024–26) when bought at the signal close, and lost when bought at the next open. The bounce was overnight and market-wide. That lead came from 2021–26, so **2012–2020 is the independent test**. 2021–26 is checked again, but it is not independent.

## Data

- `~/.quantos/index_bars/NIFTY.csv` and `BANKNIFTY.csv`: daily cash-index bars, 2012-02-21 to 2026-11-13. The opens are real; less than 0.5% of days in any year have an open equal to the previous close.
- A night is used only if the next row is the next trading session: by `core.reference.calendar` where it covers the date (2015-01-01 to 2026-08-18), otherwise a gap of at most 4 calendar days.

## Signal and trade

- **Signal:** NIFTY's close is at least **1.0%** below its previous close. The same NIFTY signal is used for both instruments.
- **Trade:** long at the signal day's close, out at the next session's open. The overnight return is next open / signal close − 1.
- **Instruments:** NIFTY and BANKNIFTY, each scored on its own.
- **Costs:** **0.07%** round trip, today's cost for index futures. That is STT 0.05% on the sell side (since 2026-04-01), plus about 0.02% for exchange fees and slippage.
- **Baseline:** the same overnight return on every other night (non-signal nights) in the same period.

**Limits, stated up front.** The cash-index close and open stand in for futures fills. A real trade fills at about 15:25 and around 09:15–09:20, and the futures basis moves overnight. These are daily bars, so a 15:25 fill cannot be checked here.

## Pass (each instrument separately)

**Discovery, 2012-02-21 to 2020-12-31:**
1. The mean net overnight return (gross − 0.07%) is above 0, with one-sample t ≥ 2.
2. The gross mean beats non-signal nights, with Welch t ≥ 1.65 (one-sided 5%).
3. The mean net return is still above 0 with 2020 left out, so that the COVID crash alone cannot carry it.

**Confirmation, 2021-01-01 to 2026-11-13** (for instruments that pass discovery):
4. n ≥ 50 signal nights.
5. The mean net return is above 0, with a one-sided p-value that clears Holm across the instruments that reached confirmation (α 0.05).
6. The gross mean is above the mean of non-signal nights.

All six must hold. Anything else is a FAIL, reported as failed and not re-tuned this round.

## Reported, not scored

- Exit at the next session's close instead of the open.
- Thresholds of 1.5% and 2.0%.
- BANKNIFTY on its own −1% signal.
- The worst overnight loss on a signal night, the 5th percentile, and the share of losing nights.
- Results at 0.10% cost.
- Results by year.
- Five worked signal nights, printed and checkable by hand from the CSVs.

## If it passes

It becomes a pre-registered **paper** test with real 15:25 and next-morning futures quotes. That shows whether the cash-index gap survives futures fills and the basis. Nothing goes to real money without the forward record and the user's release. Trading stays paused.

## Result (run 2026-11-17, `scripts/research/overnight_rebound_test.py`, plan at e22940b): FAIL, both instruments at discovery

| Instrument, period | Signal nights | Gross | Net of 0.07% | t | Other nights |
|---|---|---|---|---|---|
| NIFTY, 2012–20 | 238 | +0.116% | +0.046% | 0.79 | +0.123% |
| NIFTY, 2012–20 without 2020 | 197 | +0.062% | −0.008% | −0.20 | +0.119% |
| NIFTY, 2021–26 | 147 | +0.015% | −0.055% | −0.74 | +0.092% |
| BANKNIFTY, 2012–20 | 238 | +0.097% | +0.027% | 0.37 | +0.133% |
| BANKNIFTY, 2012–20 without 2020 | 197 | +0.018% | −0.052% | −1.03 | +0.130% |
| BANKNIFTY, 2021–26 | 147 | −0.033% | −0.103% | −1.23 | +0.071% |

After a NIFTY fall of 1% or more, the index's next overnight move is **smaller** than an ordinary night's, not larger. The small positive mean in 2012–20 comes from 2020. In 2024–26 the signal nights lost money in every year for NIFTY. Holding to the next close instead of the open changes nothing (t 0.48 and −0.04 for NIFTY).

**Reported, not scored.** At a −2.0% threshold, 2021–26 shows +0.40% net on 25 nights (t 2.1). In 2012–20 the same cut gave +0.11% on 62 nights (t 0.6), so the independent period does not support it. It is a 25-night result, found after the fact, and is not re-tested this round.

**Why the stock-level lead didn't carry over.** The S3 flush lead measured the most beaten-down stocks on market sell-off days, in R units with tight stops. A small move in % reads as a large R. The index as a whole doesn't rebound overnight. Whatever the lead was, it isn't a market-wide overnight edge you can trade with index futures.
