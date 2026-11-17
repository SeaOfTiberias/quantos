# Darvas second chance: a map re-entry after a stop-out: pre-registration (2026-11-17)

Written and committed before any run. The user approved it on 2026-11-17 ("lets do both").

**Where it came from.** The history replays of 2026-11-17 (`PICK_AND_ENTRY_PLAN.md` section 5) ran the map plan on Darvas Bucket B picks, 2016–2023. On the picks the plan entered, its sweep entries turned the Darvas trade's loss into a gain: +1.13% vs −4.14% as traded (2016–19), and +0.82% vs −3.07% (2020–23). But it entered only about 12% of picks, so it cannot replace the Darvas trade. The idea here is to keep the Darvas trade as it is, and when it is stopped out at a loss, give the stock a second chance through the map.

**Independence.** That lead came from the same stocks and years as 2016–23 here, though with different pick dates (the breakout there, the stop-out here). So 2016–23 is not a clean test. **2024–26 is the only untouched period**, and it must pass on its own.

## Picks

- **Source:** Darvas ATR-stop trades in Bucket B (box width over 35% and up to 50%). For 2016–2023 they come from `~/.quantos/darvas_atr_stop_oos_results.json`; for 2024–2026 from `~/.quantos/darvas_atr_stop_results.json`.
- **A pick is a losing stop-out:** exit reason `stop` with the exit price below the entry price. Exits at a target, at the time limit, or at a trailing stop in profit are not picks.
- **The pick date is the stop-out session.** The map card is built from bars through that day's close.
- **Survivorship.** The 2024–26 trades come from the current Nifty 500 list, so that period carries survivorship bias, the same as the original backtest.
- Picks whose symbol is not in the L1 store (`l1_snap_20261113`) are dropped and counted.

## Plan (frozen, no changes)

The map plan at commit d06b88d plus the review fixes, run with `scripts/call_plans.py --replay-from`. Each re-entry pick goes in as a CE call with its own source tag, so it gets no follow-through starter. Everything else is as in `PICK_AND_ENTRY_PLAN.md` section 3:
- a structural level 0.2–4 ATR below, a sweep of 0.25 ATR, a reclaim within 3 sessions, entry at the next open;
- a stop 0.1 ATR under the sweep low, the map target or 2R, a 1R minimum;
- one re-try, a 20-session wait and a 15-session hold;
- the NIFTY guard and the weekly cap.

The replay runs in three chunks by pick date (2016–19, 2020–23, 2024–26), each in its own scratch root. Each chunk runs until its last plan has closed.

## Measure

- **Main entries**, meaning sweep and re-sweep tracks that closed (target, stop or time).
- **Net R** = (exit − entry − 0.25% of entry) / (entry − stop). The 0.25% is the round trip for cash delivery, as in the earlier daily tests.

## Pass

1. **Discovery, picks dated 2016–2023:**
   - mean net R ≥ **+0.20**, with t ≥ 2 and n ≥ 60 entries;
   - mean net R > 0 in both 2016–19 and 2020–23.
2. **Confirmation, picks dated 2024-01-01 to 2026-11-13:**
   - mean net R > 0, with n ≥ 20 entries.
   - At about 20–40 entries this can only catch a reversal; it cannot prove the size of the edge.

All must hold. Anything else is a FAIL, reported as failed and not re-tuned this round.

## Reported, not scored

- **A plain re-entry:** buy at the next open after the stop-out, hold 15 sessions, sell at the close, net of 0.25%. This shows what the map adds over simply buying back.
- Results by exit type (target, stop, time) and by level kind.
- The NIFTY guard's cancellations.
- The share of picks entered.
- What the re-entries add per Darvas trade: the re-entry's net % summed over all losing stop-outs, divided by every Bucket B trade in that period.

Before the full run, five worked cases are printed and checked by hand.

## If it passes

The re-entry is added to the Darvas paper executor's plan, on paper, scored separately from the Darvas entries. Real money still needs the forward record and the user's release. Trading stays paused.
