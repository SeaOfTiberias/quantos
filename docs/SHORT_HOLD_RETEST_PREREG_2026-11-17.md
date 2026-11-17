# Failed daily signals, re-tested as 15 / 30 / 60-minute trades: pre-registration (2026-11-17)

Written and committed before any run. The user asked on 2026-11-17 for the failed strategies to be tested with 15, 30 or 60-minute holds. Their point: for F&O, a hold measured in days is an eternity, and every test so far used daily candles.

## Which strategies, and why only these

**Included:** every failed signal that fires at a known moment and whose events can be rebuilt from our data. Each set is listed with how its entry moment is fixed.

| Set | Signal | Entry moment |
|---|---|---|
| E1 | Daily close above ET's R3 = P + 2(H − L) of the previous session (2026-11-17, failed) | Next session |
| E2 | Daily close below S3 (2026-11-17 short failed; the long side is the S3 flush, under test) | Next session |
| E3 | First 5-minute close above the day's R3, 09:30–14:30 | The next 5-minute bar |
| E4 | First 5-minute close below the day's S3, 09:30–14:30 | The next 5-minute bar |
| E5 | Pivot Compression Breakout, day 1, the user's Pine v2.0 (2026-11-17, failed) | Next session |
| E6 | The same rule mirrored for shorts (2026-11-17) | Next session |
| E7 | The 2026-11-07 CCI(34)/SMA52 + 5-SMA over monthly CPR rule, long (`core/backtest/cci_cpr.py`, failed) | Next session |
| E8 | The same rule, short | Next session |
| E9 | 55-day closing-high breakout with a follow-through close: the continuation starter (2026-11-16, failed) | The session after the follow-through |
| E10 | The same rule for puts (55-day closing-low break) | The session after the follow-through |
| E11 | 55-day breakout with no follow-through, the GLAND case (2026-11-16 fade, failed) | The session after the no-follow-through day |
| E12 | F&O screener signals, CE (`~/.quantos/bt_fno/outcomes.jsonl`, Sep 2025 – Oct 2026) | Next session |
| E13 | F&O screener signals, PE | Next session |

**Excluded:**
- **Strategies that were already intraday:** ORB (18, 18b), the 10:10 breakout, the trend-day filter, expiry-day, the goodnight scalper. They were tested at short holds and failed.
- **Multi-week strategies:** momentum rotation, pairs, PEAD, VRP, the regime and term-structure signals, event proximity, the ML factor. A 30-minute version of any of these is a different strategy.
- **Darvas Bucket B:** our trade dates end in 2023, so there is no 2024–26 period to confirm on. It is reported for 2017–23 only and cannot pass.

## Universe, data, trade

- **Data:** 5-minute bars for the 211 F&O stocks in `~/.quantos/l1_snap_20261113/m5`, 2017 to 2026-11-13. The R3/S3 levels for E1–E4 come from the previous session's 5-minute bars.
- **Entry:**
  - For the next-session sets, the open of the **09:20** bar (the second bar, after the opening print).
  - For E3/E4, the open of the bar after the signal bar.
- **Holds:** 3, 6 and 12 bars (15, 30 and 60 minutes). The exit is the close of the last bar. Events whose hold would run past the 15:25 bar are dropped.
- **Measure:** the trade's return minus the mean return of every F&O stock over the same bars, so a market move doesn't count as an edge. Then minus **0.10%**, today's round trip for stock futures (STT 0.05% on the sell side since 2026-04-01, plus about two ticks of slippage).

## How a pass is decided

**Discovery, 2017–2023:**
- For every set and hold, the sign (long or short) is chosen by the discovery mean. That lets the "invert it" question answer itself.
- A cell goes forward if the net excess in that sign is above 0 with t ≥ 2.

E12 and E13 have no discovery period, because the screener only exists from Sep 2025. Their sign is fixed by design: CE long, PE short. Both go straight to confirmation.

**Confirmation, 2024 – 2026-11-13, untouched until the discovery table is written:**
- A cell passes if, in the same sign, the net excess is above 0.
- The one-sided p-value must clear Holm across every cell that reached confirmation.
- It needs n ≥ 100.

**Anything else fails.** A pass means a pre-registered paper test of that one cell, with real option or futures quotes. It does not mean deployment.

## Reported, not scored

- The same table with entry at 09:15.
- The time-of-day split for E3/E4 (before and after 11:00).
- The share of trades whose gross move beats 0.10%.
