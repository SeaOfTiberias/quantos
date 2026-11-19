# Darvas Bucket B: a structural stop instead of the ATR stop (pre-registration, 2026-11-19)

Execution plan E3, part 2 (`docs/EXECUTION_PLAN_2026-11-19.md`). Written and committed **before any code for it exists and before any run**. Research only: nothing live changes, whatever the result.

## Question

Darvas exits sometimes come at the sweep that should have been the entry: GLAND and ZYDUS in October 2026 were stopped and then rallied (lesson 9, `docs/TRADE_REASONING.md`). Does placing the **initial** stop just beyond the nearest structural liquidity on the v3 map, instead of at box ceiling − 2 ATR(14), improve the same trades?

## Trades (fixed; no new entries)

- **Discovery:** the Bucket B trades (box width over 35% and up to 50%) of the 2016-23 out-of-sample run, from `~/.quantos/darvas_atr_stop_oos_results.json`: 991 trades, the set `docs/DARVAS_GO_NO_GO_2026-11.md` reproduced.
- **Confirmation:** the Bucket B trades of the original run with entries from 2024-01-01, from `~/.quantos/darvas_atr_stop_results.json`. That run's universe is today's Nifty 500, so this period carries survivorship bias, as the original did.
- Same entry (date and open price) in both arms. A trade whose symbol is not in the L1 store snapshot `~/.quantos/l1_snap_20261113` is dropped and counted.

## The two arms

Both arms are re-simulated on the **same bars**: the L1 store's adjusted bhavcopy bars, with the backtest's own `analyse_symbol` and `_simulate_exit_atr` from `scripts/backtest_darvas_atr_stop.py`, unchanged.

- **ATR (control):** initial stop = box ceiling − 2 × ATR(14) at the breakout bar, as frozen.
- **Structural:** initial stop = `sweep_level(card, bars, "CE")["level"]` − 0.1 × ATR(D).
  - `sweep_level` is `core/market_map/call_plan.py` as at this commit: lesson 9's structural liquidity 0.2–4 ATR(D) below the price, extended through levels within 0.5 ATR of the pool's far edge.
  - The card is the v3 context card (`core/market_map/card.py` over `structure.l1_read`) from bars through the **breakout** session's close, at that close.
  - When `sweep_level` finds no level, the structural arm keeps the ATR stop. Those trades are counted as "no level" and enter the comparison as identical (difference 0).
- **Everything after the initial stop is identical:** the stop and target trail on each new box ceiling exactly as frozen (the stop rises to ceiling − 2 ATR only when that is above the current stop), the target is `mm_target`, and exits fill at the stop or target price, as in the backtest.

**Reproduction gate, checked before any arm is compared:** the re-simulated ATR arm must match the cached trade (same exit date within one session and exit price within 1%) on **at least 90%** of trades in each period. Below that, the bars differ too much from the original run's. The test stops, and that is reported instead of a result.

## Measure

- **Net return per trade:** `net_return` from `scripts/backtest_darvas_atr_stop_oos.py` (₹1,00,000 per trade, Stressed costs incl. 25 bps slippage), as in the OOS run.
- **Primary statistic:** the **paired difference**, structural minus ATR, per trade (equal capital per trade, the backtest's own sizing).

## Pass (all must hold)

1. **Discovery (2016-23):** the mean paired difference is > 0, and its week-clustered bootstrap 90% CI (10,000 draws, seed 20261119, weeks of entry) has a lower bound > 0.
2. **Both halves of discovery:** the mean paired difference is > 0 in 2016-19 and in 2020-23 (by entry date).
3. **Confirmation (2024-26):** the mean paired difference is > 0.

Anything else is a FAIL, reported as failed and not re-tuned this round.

## Reported, not scored

- Shares: trades with a different initial stop, structural stop wider vs tighter, "no level".
- Each arm's mean net return, win rate, and mean initial risk (entry − stop, % of entry).
- Each arm's mean net R, where R = initial risk. A wider stop changes R, so R is shown but not compared.
- **The GLAND pattern:** in each arm, the share of stopped trades whose high, within 15 sessions after the stop, comes back above the entry price.
- Each arm's running-sum drawdown, in exit order.
- Level kinds that set the structural stop.

## Before the full run

Five worked cases, drawn by hand from discovery trades and shown to the user: the breakout, both stops with the level kind, and each arm's exit. They check mechanics only. The first five discovery trades in entry order are used, so the cases aren't picked.

## If it passes

A structural-stop variant may run as a separate paper variant beside the Darvas executor, unchanged and scored on its own (as the sprint notes of 2026-11-06 require for any map-filtered Darvas variant). Real money still needs `docs/DARVAS_GO_NO_GO_2026-11.md`'s review and the user's go-ahead. Trading stays paused.
