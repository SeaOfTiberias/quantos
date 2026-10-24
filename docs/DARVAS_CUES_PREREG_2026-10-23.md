# Darvas Bucket B: universe, entry cues and exits. Pre-registration (2026-10-23)

Written before any of these tests ran. Nothing below has been computed on the data yet.

## Why

The live paper run (dry-run, ₹5L) has closed 3 Bucket B trades, all at the stop:

| Trade | Result | Best point |
|---|---|---|
| ZYDUSLIFE 09-28 | −7.7% | +0.9% |
| PERSISTENT 10-14 | −6.8% | +1.5% |
| GLAND 10-08 | −9.8% | +0.3% |

A fourth, PTCIL, is open, at −5% on 2026-10-23 after reaching +5.7%. At a 47% win rate, three straight losses happen about 15% of the time, so this is **not** evidence against the rule.

Reading the four charts suggested some cues, listed below. A small-cap 52-week-high breakout outside the universe, which worked over the same weeks, suggested two more: the universe question and the "clear air" cue. **These ideas come from five hindsight charts.** This test decides whether any of them hold across the full trade history.

## Fixed for every test

- **Rules.** Bucket B (box width 35–50%) exactly as frozen in `scripts/backtest_darvas_atr_stop.py`:
  - FRESH BREAKOUT on the signal bar *i*, entry at the open of *i+1*;
  - initial stop = box ceiling − 2 × ATR(14);
  - the stop and the `mm_target` trail only when a new, higher box forms.
- **Data.** NSE's daily EQ bhavcopy (`data_cache/pead_nse/eq_bhavcopy_raw`, 2016-01-01 to 2026-06-25, which includes later-delisted names). Split and bonus adjustment uses the same method as `scripts/backtest_darvas_atr_stop_oos.py`.
- **Periods.**
  - **P1:** breakouts 2016-07-01 to 2023-09-21, the OOS window.
  - **P2:** breakouts 2023-09-22 to 2026-03-31, exits up to 2026-06-25, open trades marked to market.
  - P2 is where the Bucket B rule itself was found, so it is in-sample for the baseline but fresh for every cue below.
  - P2 needs the corporate-actions list extended past 2023, using the same NSE source and method. That is a data step done before the run. If it can't be done, P2 is dropped, and this is said in the results.
- **Fills, all arms including the baseline:**
  - If a bar opens below the stop, the exit fills at the **open**, not the stop. The frozen backtest filled at the stop, which flatters gap-downs.
  - A bar with high = low (locked at a price band) can't be traded, and the exit moves to the next tradeable open.
  - Targets fill at the target.
- **Costs.** `STRESSED_COST_MODEL` on a ₹1L position. U2 (below) gets an extra **0.25% slippage per side** for wider small-cap spreads.
- **Measure.** Per-trade **excess**: net return minus the equal-weight return of that trade's own universe over the same entry-to-exit dates. Raw returns are reported but never judged, so a small-cap bull run can't pass as an edge.
- **Bootstrap.** Resampled by entry week, 10,000 draws, seed 20261024.
- **Multiple testing.** 8 tests below, so α = 0.05 / 8 ≈ 0.006 (one-sided). "Bound > 0" means the 0.6th percentile of the bootstrap is above zero.

## Universes

| ID | Definition |
|---|---|
| U1 | Ranks 1–500 by median daily traded value over the prior 126 sessions, re-ranked on 1 Jan and 1 Jul. This is the existing OOS universe and the control. |
| U2 | Ranks 501–1000 on the same ranking, with a median traded value of at least ₹2 cr/day. |
| U3 | U1 ∪ U2 (descriptive; follows from U1 and U2). |

Live trading currently scans the Nifty 500 *index* list, not U1. The overlap between the two is reported as description only.

## Hypotheses

### T1, the universe

**Does Bucket B have an edge in U2?** It passes only if all of these hold:
1. Mean excess > 0 in P1 **and** in P2.
2. The pooled bootstrap bound of mean excess > 0.
3. At least 300 trades pooled.

If T1 passes, U3 becomes the candidate paper universe. If it fails, the scan stays on large and mid caps.

### Entry filters (T2–T5)

All are measured at the signal bar *i*, so they are known before entry. Each is tested on U1 Bucket B trades. Each splits trades into **kept** and **dropped**.

| ID | Keep when | Idea |
|---|---|---|
| T2 clear air | close*ᵢ* ≥ the highest high of sessions *i−252 … i−1* (a 52-week-high breakout) | An older high overhead caps the move (ZYDUS, PERSISTENT, PTCIL). |
| T3 MACD confirms | MACD(12,26) line at *i* ≥ its maximum over *i−60 … i−1* | A lower MACD high is a divergence (PERSISTENT, GLAND, PTCIL). |
| T4 volume | volume*ᵢ* ≥ 1.5 × the mean volume of *i−50 … i−1* | Breakouts need participation. |
| T5 not extended (control) | (close*ᵢ* − close*ᵢ₋₂*) / ATR(14)*ᵢ* < 2.5 | All four losers came off a 2-day vertical burst. **Expected to fail**: most breakouts look like this. |

**A filter passes if all of these hold:**
1. Mean excess of kept − dropped > 0 in P1 **and** P2.
2. The pooled bootstrap bound of (kept − dropped) > 0.
3. The dropped group's pooled mean excess ≤ 0. Dropping trades that beat the universe would lower total profit even if the average per trade rises.
4. At least 250 trades kept, pooled.

### Exits (T6–T8)

Applied to the same U1 Bucket B trades. Each is compared trade by trade with the baseline exit (paired difference).

| ID | Rule | Idea |
|---|---|---|
| T6 early failure | Until the stop first trails: the first daily close below the box ceiling → exit at the next open. | The breakout failed. It would have cut the three closed losses from −24.3% to −11.1% combined. |
| T7 breakeven | Once a high ≥ entry + 1 × ATR(14)*ᵢ*, raise the stop to the entry price (if higher). | Don't give back an open gain (PTCIL, +5.7%). |
| T8 weak day 1 (control) | The entry-day close is below its open and in the lower third of its range → exit at the next open. | All four entry days closed weak. **Expected to fail**: it's common after a big signal candle. |

**An exit passes if all of these hold:**
1. Mean paired difference (variant − baseline net) > 0 in P1 **and** P2.
2. The pooled bootstrap bound > 0.

Both exits can cut winners that retest the box before running. The top 5% of baseline trades are therefore reported under each variant (description only).

## Excluded

**Results within the hold.** PERSISTENT probably gapped on results, but the results-date data on hand (`point_in_time_pat.csv`) covers only October 2024 to March 2025. That is too little. The cue is deferred until a full results calendar exists.

## Amendment before the run (2026-10-23, nothing computed yet)

1. **Business view, description only, not part of any verdict.** For U1 and U2 Bucket B under the baseline exit:
   - trades per year;
   - win rate and average win / average loss;
   - mean net and mean excess;
   - the implied excess per year on ₹5L at 9% per trade (trades per year × mean excess × ₹45k);
   - the median daily traded value of the names traded, and a ₹45k slot (₹5L) and a ₹4.5L slot (₹50L) as a % of it. That is capacity: how far the strategy scales before our own orders move the price.

   A strategy that is real but trades 10 times a year, or can't take ₹50L, is a different business from one that can.
2. **Code check before any result counts.** The box detector is ported from pandas to plain Python for speed (`analyse_symbol` takes about 47 ms a call, so a full run would take about 17 hours).
   - The port must match `analyse_symbol` on sampled real bars.
   - Re-running the OOS window (U1, data cut at 2023-12-31, the old stop fills) must reproduce `docs/DARVAS_ATR_STOP_OOS_RESULTS.md`: 991 Bucket B trades, mean net +2.16%.
   - If either check fails, nothing below is reported until it's fixed.
3. **Known overlap, noted before the run.** The FRESH BREAKOUT rule already requires volume ≥ 1.5 × its 20-day average. T4 (≥ 1.5 × the 50-day average, today excluded) is therefore expected to keep most trades. T4 is left as registered.

## After the run

- Results are appended to this file. The script is `scripts/backtest_darvas_cues.py`, committed with them.
- A test that fails is reported as failed and **not re-tuned in this round**: no other thresholds and no other lookbacks.
- Anything that passes goes to the **paper** executor first, and only on the user's go-ahead. Capital, sizing and `dry_run` are unchanged by this test.
- Not combined. Passing filters and exits are tested together only in a later, separately pre-registered round.

---

## Results

Run 2026-10-24: `python scripts/backtest_darvas_cues.py`. 1950 Bucket B trades (U1 1259, U2 691). Gap-aware fills, Stressed costs (+0.25%/side for U2). Excess is over each trade's own universe. Bound = the 0.62% bootstrap quantile (one-sided α = 0.05/8).

### T1, the universe (baseline exit)

| Universe | Period | Trades | Won | Mean net | Mean excess | Bound (excess) |
|---|---|---|---|---|---|---|
| U1 | P1 | 991 | 39% | +0.38% | -1.09% |  |
| U1 | P2 | 268 | 36% | +0.07% | -0.81% |  |
| U1 | both | 1259 | 39% | +0.31% | -1.03% | -1.98% |
| U2 | P1 | 343 | 41% | +1.34% | -0.40% |  |
| U2 | P2 | 348 | 33% | -1.51% | -2.27% |  |
| U2 | both | 691 | 37% | -0.10% | -1.34% | -2.59% |

**T1 FAIL** (U2: excess > 0 in P1 and P2, bound > 0, ≥ 300 trades).

### Entry filters T2–T5 (U1, baseline exit)

| Test | Kept | Dropped | Kept excess | Dropped excess | Diff P1 | Diff P2 | Bound (diff) | Verdict |
|---|---|---|---|---|---|---|---|---|
| T2 clear air | 522 | 737 | -1.02% | -1.04% | +0.55% | -1.97% | -1.86% | fail |
| T3 MACD confirms | 277 | 982 | -2.28% | -0.68% | -1.92% | -0.30% | -3.88% | fail |
| T4 volume ≥ 1.5× 50d | 1167 | 92 | -1.03% | -1.01% | +1.41% | -4.86% | -3.65% | fail |
| T5 not extended (control) | 983 | 276 | -1.15% | -0.61% | -0.20% | -1.90% | -2.64% | fail |

### Exits T6–T8 (U1, paired against the baseline exit)

| Test | Trades | Mean net | Mean excess | Paired diff P1 | Paired diff P2 | Bound | Top-5% winners: base → variant | Verdict |
|---|---|---|---|---|---|---|---|---|
| T6 early failure | 1259 | -0.18% | -0.99% | -0.41% | -0.80% | -1.22% | +29.4% → +13.6% | fail |
| T7 breakeven | 1259 | -0.68% | -1.38% | -0.99% | -1.01% | -1.73% | +29.4% → +14.4% | fail |
| T8 weak day 1 (control) | 1259 | +0.15% | -0.78% | -0.11% | -0.36% | -0.79% | +29.4% → +19.7% | fail |

U1 baseline mean net +0.31%, excess -1.03%.

### Business view (description only)

| Universe | Trades/yr | Won | Avg win / avg loss | Mean net | Mean excess | Excess ₹/yr on ₹5L (9% slots) | Median traded value | ₹45k slot | ₹4.5L slot |
|---|---|---|---|---|---|---|---|---|---|
| U1 | 129 | 39% | +15.4% / -9.2% | +0.31% | -1.03% | ₹-59,837 | ₹19.7 cr | 0.023% | 0.23% |
| U2 | 71 | 37% | +16.2% / -9.6% | -0.10% | -1.34% | ₹-42,748 | ₹6.4 cr | 0.071% | 0.71% |

Trades/yr is every signal; the live book takes fewer (cash limit at 9% per slot).


### Why the baseline fell from +2.16% to +0.38% (diagnostic, description only)

Run 2026-10-24 after the registered tests; not part of any verdict. It re-ran the 991 U1 P1 trades with the old stop fills and matched them one for one with the gap-aware run (991 of 991 matched, same entries).

- Mean net: **+2.16% (old stop fills) → +0.38% (gap-aware)**. Win rate 47% → 39%.
- 332 trades changed, all of them stop exits in both runs. The fill change explains the whole drop; the costs, data and universe do not.
- **281 of the 332 were not overnight gaps.** The exit bar opened at or above 99% of the prior close. What happened: a new, higher box confirmed at the close, the trailed stop (ceiling − 2 × ATR) landed *above* the current price, and the frozen backtest sold at that stop, a price that did not trade. Examples: NATIONALUM 2021-11-16, old fill 118.2 against an open of 100.0 after a week of 97–103; NCC 2018-02-06, old fill 129.4 against an open of 104.5; HDFCAMC 2020-01-07, old fill 1830.9 against a bar range of 1538–1548 (adjusted prices).
- The other 51 were real gap-downs (OMKARCHEM 2017-06-27, PINCON 2017-11, locked limit-down bars).
- A live executor holding a stop above the market sells at the next open, which is what the gap-aware fill does. **The +2.16% / +0.70% excess in `docs/DARVAS_ATR_STOP_OOS_RESULTS.md` was inflated by impossible fills.** Under realistic fills, U1 Bucket B in P1 makes +0.38% net and −1.09% excess a trade.
- The script `scripts/backtest_darvas_cues.py` reproduces this: `--validate-oos` gives the old stop-fill number, and the main run gives the gap-aware one.
