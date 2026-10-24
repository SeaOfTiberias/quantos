---
title: Darvas Bucket B Cue Tests (Universe, Entry Filters, Exits)
compiled: 2026-10-24
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: darvas-bucket-b-cues
candidate: "Darvas line 3 add-ons, T1–T8"
family: breakout
instrument: equity-cash
status: closed
verdict: FAIL
first_tested: 2026-10-23
verdict_date: 2026-10-24
profit_factor:
sharpe:
trades: 1950
bar: "Per test: excess over the trade's own universe > 0 in P1 and P2, and the week-bootstrap bound at α = 0.05/8 > 0 (plus trade-count and dropped-group conditions)"
headline: "All 8 pre-registered tests failed: no small-cap universe edge, and none of four entry filters or three exits beat the baseline Bucket B rule."
next_gate: "None this round; a test that failed is not re-tuned. Any new cue needs its own pre-registration."
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-24-darvas-bucket-b-universe-entry-cues-and-exits-pre-registrati
---

# Darvas Bucket B Cue Tests (Universe, Entry Filters, Exits)

> [!abstract] Compiled page
> Written from `[[2026-10-24-darvas-bucket-b-universe-entry-cues-and-exits-pre-registrati]]` on 2026-10-24. Context and retrieval only — rules in this layer never execute.

## Definition

Eight pre-registered tests of add-ons to the frozen [[darvas-atr-stop-bucket-b]] rule: one on the universe (T1), four entry filters (T2–T5) and three exits (T6–T8). The ideas came from five hindsight charts: three closed paper losses that all exited at the stop (ZYDUSLIFE −7.7%, PERSISTENT −6.8%, GLAND −9.8%), the open PTCIL trade at −5% after +5.7%, and a small-cap 52-week-high breakout that worked outside the universe `[[2026-10-24-darvas-bucket-b-universe-entry-cues-and-exits-pre-registrati]]`.

## Mechanics

- **Fixed for every test**: the frozen Bucket B rules (box width 35–50%, entry at the next open after a FRESH BREAKOUT, initial stop at ceiling − 2 × ATR(14), stop and target trail only on a new, higher box). Data: NSE EQ bhavcopy 2016-01-01 to 2026-06-25, including later-delisted names.
- **Periods**: P1 = breakouts 2016-07-01 to 2023-09-21 (the earlier OOS window); P2 = 2023-09-22 to 2026-03-31, which is in-sample for the baseline but fresh for every cue.
- **Fills, all arms**: a bar that opens below the stop fills at the open; a locked bar (high = low) defers the exit to the next tradeable open. Costs: Stressed on ₹1L, with an extra 0.25% slippage per side for U2.
- **Measure**: per-trade excess over the equal-weight return of the trade's own universe over the same dates. Bootstrap by entry week, 10,000 draws; α = 0.05/8, one-sided.
- **Universes**: U1 = ranks 1–500 by 126-session median traded value (the control); U2 = ranks 501–1000 with at least ₹2 cr/day.
- **Code checks before results counted**: the plain-Python box detector matched `analyse_symbol` on 619 sampled bars with 0 mismatches, and re-running the old OOS setup reproduced 991 trades at +2.16% mean net.

## Results

1,950 Bucket B trades (U1 1,259, U2 691) `[[2026-10-24-darvas-bucket-b-universe-entry-cues-and-exits-pre-registrati]]`.

| Test | Idea | Key numbers | Verdict |
|---|---|---|---|
| T1 universe | Edge in ranks 501–1000 | U2 excess −0.40% (P1), −2.27% (P2); pooled bound −2.59% | FAIL |
| T2 clear air | 52-week-high breakouts only | Kept − dropped +0.55% (P1), −1.97% (P2) | FAIL |
| T3 MACD confirms | No MACD divergence | Kept − dropped −1.92% (P1), −0.30% (P2) | FAIL |
| T4 volume | ≥ 1.5 × 50-day volume | Kept 1,167 of 1,259; diff −4.86% in P2 | FAIL |
| T5 not extended | Control, expected to fail | Diff −0.20% (P1), −1.90% (P2) | FAIL |
| T6 early failure | Exit on first close back in the box | Paired −0.41% (P1), −0.80% (P2); top-5% winners +29.4% → +13.6% | FAIL |
| T7 breakeven | Stop to entry after +1 ATR | Paired −0.99% (P1), −1.01% (P2) | FAIL |
| T8 weak day 1 | Control, expected to fail | Paired −0.11% (P1), −0.36% (P2) | FAIL |

Both early exits (T6, T7) cut the trades that carry the result: the top 5% of baseline trades fell by about half under each.

### Business view (description only)

U1: 129 signals a year, 39% won, average win +15.4% against average loss −9.2%, mean net +0.31%, mean excess −1.03%. Median traded value of names traded ₹19.7 cr/day, so a ₹4.5L slot is 0.23% of it. U2: 71 a year, mean net −0.10%, excess −1.34%, median ₹6.4 cr/day.

### What the run revealed about the baseline

A post-run diagnostic (description only) found the whole fall in U1 P1 mean net, from +2.16% under the old fills to +0.38% under gap-aware fills, comes from 332 stop exits. 281 of those were not overnight gaps: a newly confirmed higher box trailed the stop **above** the current price, and the frozen backtest sold at a stop price that never traded (for example NATIONALUM 2021-11-16, a fill at 118.2 against an open of 100.0). The other 51 were real gap-downs `[[2026-10-24-darvas-bucket-b-universe-entry-cues-and-exits-pre-registrati]]`. That changes the reading of [[darvas-atr-stop-bucket-b]]'s out-of-sample pass.

## Not tested

Results inside the holding period (PERSISTENT probably gapped on results) were deferred, because the results calendar on hand covers only October 2024 to March 2025 `[[2026-10-24-darvas-bucket-b-universe-entry-cues-and-exits-pre-registrati]]`.

## Relation to other concepts

- Every arm uses [[darvas-atr-stop-bucket-b]]'s frozen rules as the baseline, so these fails are about the add-ons; the baseline's own standing is on that page.
- T6 and T7 are exit-side refinements of the trail described in [[darvas-trailing-stop]]; both cost more in clipped winners than they saved in losses.
