# 50/200 DMA cross and price/50 DMA cross, with parameter permutation (pre-registration, 2026-11-27)

Written **before any code for it exists and before any run**. Research only: trading is paused, nothing live changes, whatever the result. Method for judging a grid: Dave Walton, "Know Your System! Turning Data Mining Bias to Benefit Through System Parameter Permutation" (NAAIM Wagner Award, 2014). The strategy is judged on its **median** grid version, not its best one, and a walk-forward test checks that a version picked by rule holds up out of sample.

## Question

On NSE stocks, long only, does either of two classic moving-average rules earn more than simply holding the market over the same days, after realistic costs, robustly across nearby settings?

- **A. Golden cross:** buy when the fast DMA crosses above the slow DMA; sell when it crosses back below (death cross).
- **B. Price over the DMA:** buy when the close crosses above the DMA; sell when the close crosses back below it.

A and B are scored separately. Two signals are tested in this round, and that is reported with any result.

## Data and universe (the 2016-23 out-of-sample set, unchanged)

The same data as `scripts/backtest_darvas_atr_stop_oos.py`:
- NSE daily equity bhavcopies, EQ series, 2016-01-01 to 2023-12-31, including names that were later delisted or merged (no survivorship from the data source).
- Split/bonus adjustment from `data_cache/nse_corporate_actions_2016_2023.json` plus that script's residual fixes, by importing its loaders unchanged.
- **Universe:** on each 1 Jan and 1 Jul, the 500 symbols with the highest median daily traded value over the prior 126 sessions. A signal counts only if its symbol is in the universe on the signal date. An open position is held to its exit even if the symbol leaves the universe.

## Rules

- DMA = simple moving average of the adjusted close, D sessions long.
- **A:** signal when SMA(fast) closes above SMA(slow) today and was at or below it yesterday. Exit signal on the opposite cross.
- **B:** signal when the close is above SMA(D) today and was at or below it yesterday. Exit signal when the close is below SMA(D) after having been above it.
- **Fills:** entry at the **next session's open** after the signal close; exit at the next session's open after the exit signal. No target, no time limit.

## Exits (a grid dimension, not a separate test)

Moving-average exits are slow: a death cross often comes long after the top, so winners give back much of their gain. Each version uses one of four exits:

- **Signal:** the opposite cross only, as above.
- **Signal + ATR trail, k ∈ {2.5, 3, 4}** (a chandelier stop): the trade also exits when the close falls below **the highest close since entry − k × ATR(14)**, whichever comes first. ATR is Wilder's 14-day ATR on the adjusted bars, recomputed each day. The stop only rises, never falls. On the entry day "the highest close since entry" is the entry session's close, so the trail also acts as the initial stop. Fill: the next session's open, like every other exit (a gap below the stop fills at that open).

Why ATR: it scales the stop to each stock's own volatility, unlike a fixed percent, and it is the stop family the Darvas rule passed out of sample with. Trailing from the highest close rather than a fixed initial stop lets a winner run, which is where a trend rule earns its money.
- One position per symbol at a time; a new entry signal while in a position is ignored.
- **Window:** entry signals from 2016-11-01 (so a 220-day SMA exists) to 2023-09-30. A trade still open at the data end, 2023-12-29, is marked at that close.
- **Size and costs:** ₹1,00,000 per trade, `net_return` with `STRESSED_COST_MODEL` (STT, exchange, SEBI, stamp, GST, 25 bps slippage), as in the Darvas OOS run.

## The parameter grid (fixed now)

- **A:** fast ∈ {40, 45, 50, 55, 60} × slow ∈ {180, 190, 200, 210, 220} × exit ∈ {signal, ATR 2.5, ATR 3, ATR 4}: **100 versions**.
- **B:** D ∈ {40, 45, 50, 55, 60} × exit ∈ {signal, ATR 2.5, ATR 3, ATR 4}: **20 versions**.

50/200 and 50 with the signal exit are the headline versions, but they are **not** the ones scored.

## Measure

- **Excess return per trade:** a trade's net return minus the **equal-weight universe return** over the same entry-open to exit-open dates (the Darvas OOS `V2` benchmark). Long-only rules on a rising market make money from beta alone; excess return removes that.
- **A version's score:** its mean excess return per trade.
- **The median version:** the versions are ranked by score from lowest to highest, and the median version is the 50th of 100 (A) or the 10th of 20 (B), the lower of the two middle versions, which is the conservative choice. Its trades are the ones tested.

## Pass (all must hold, separately for A and for B)

1. **Median version, discovery 2016-23:** mean excess return per trade > 0, and its week-clustered bootstrap 90% CI (10,000 draws, seed 20261127, weeks of entry) has a lower end > 0.
2. **Breadth:** at least 70% of the grid's versions have a mean excess return > 0 (70 of 100 for A, 14 of 20 for B).
3. **Both halves:** the median version's mean excess return is > 0 for entries in 2016-19 and for entries in 2020-23.
4. **Walk-forward:** for each calendar year 2018 to 2023, the version with the best score on all entries before that year is chosen, and only its trades entered in that year are kept. The stitched walk-forward trades have mean excess return > 0.

Anything else is a FAIL, reported as failed and not re-tuned this round.

## Reported, not scored

- The full grid as a table (trades, win rate, mean net, mean excess, median hold), and the best version's score beside the median's.
- The headline versions (50/200 and 50, signal exit) on their own.
- **Per exit:** the median version within each exit (signal, ATR 2.5, 3, 4), and the share of trades closed by the trail vs the signal. This shows whether the trail helps, but it does not rescue the rule: a FAIL with one good exit family is a FAIL, and that family would need its own pre-registration in a later round.
- The median version's profit factor, worst running-sum drawdown, and per-year mean excess.
- The walk-forward's chosen version each year (it shows whether the "best" setting stays put).
- **Placebo:** for the median version, 200 runs that keep each trade's symbol and holding length but move the entry to a random universe-eligible session in the same calendar year (seed 20261127). The median version's mean net return is placed in that distribution (p-value). This shows whether the timing adds anything beyond holding those stocks for that long.
- 2024-26 on the L1 store (today's universe, so survivorship-biased): the median version's mean excess, reported only.

## Before the full run

Five worked trades for each of A and B, shown to the user: the first five headline-version (50/200 and 50) entries in date order, with the signal day, both SMAs, the entry open, the exit signal and the exit open, net and excess return, and the same five trades under the ATR 3 exit (the trail level on the exit day). They check the mechanics only. Then the full grid runs once.

## If either passes

It becomes a candidate for a paper variant, scored on its own. Real money still needs the user's go-ahead, and trading stays paused until the user lifts it.
