# S7-2 — Expectancy Arithmetic: Does Darvas's Plausible Edge Clear Its Own Costs?

**Status:** ✅ **DONE 2026-07-16 — inconclusive by design, and that's the finding.** Net
expectancy sign depends on where the real system falls within plausible parameter
ranges. Not obviously dead on arrival, but too close to zero for intuition to
settle — which is exactly why S7-2 hands off to S7-3 (the backtest) instead of
resolving anything by itself.
**Backlog item:** S7-2, `docs/SPRINT4_BACKLOG.md`. Zero code — this is arithmetic
against the already-built S5-1 cost model (`core/risk/costs.py`).
**Origin:** Fable's 2026-07-16 review of the trading rationale — "nothing anywhere
states what the strategy must ACHIEVE to be worth running."

## Why this is the cheapest falsifier available

Every other Sprint 7 story (veto instrumentation, sizing, exit rules) is
worthless if the strategy can't beat its own transaction costs. This is a
one-page check, not a backtest, and it comes first for that reason: if the
answer were unambiguous, it would delete the rest of the sprint.

## Cost side (measured, not guessed)

`core/risk/costs.py` is calibrated to reproduce Fyers' contract note to the
paisa. Running it against realistic Darvas trade sizes (NSE intraday MIS,
2–3% moves, entry prices ₹500–₹1,500) gives round-trip cost as a fraction of
one-leg notional:

| Scenario | Slippage/leg | Round-trip cost |
|---|---|---|
| Liquid mid-cap, normal fill | 15 bps | **0.36–0.41%** |
| Same trade, illiquid breakout fill | 40 bps | **0.92%** |

Slippage dominates the stack — brokerage, STT, exchange, SEBI, stamp, and GST
together are ~₹50–100 per round trip regardless of size; a breakout-entry
fill on a thin name is what actually moves the number. This matches Fable's
plausible sketch of 0.3–0.8% round-trip cost, now grounded in the real model
rather than assumed.

## Edge side (plausible ranges, not measured — that's S7-3's job)

Expressed in R multiples (1R = the initial stop distance, i.e. risk per
trade). Plausible parameter ranges for a breakout system, not this system's
actual measured numbers, which don't exist yet:

- Win rate: 30–45%
- Average winner: 1.5–2.5R
- Average loser: ~1R (by construction — the stop defines the loss)

Gross expectancy `E = p·avgWin − (1−p)·avgLoss` across that grid lands
**0.05R to 0.2R per trade**, gross of costs.

## Converting cost into R terms — the step that actually matters

A cost of "0.4% of notional" is meaningless against expectancy in R until
it's divided by what 1R is *as a percentage of notional* — i.e. the stop
distance. `core/darvas/box.py` bounds box width (the stop distance) between
2% and 8% of price (`BOX_MAX_WIDTH_PCT = 0.08`; tighter boxes score higher
confidence), so 1R plausibly spans **3–5%** of entry price for a typical
qualifying box.

    cost_in_R = round_trip_cost_pct / stop_distance_pct

| | Tight box (1R = 3%) | Wide box (1R = 5%) |
|---|---|---|
| Liquid fill (0.36–0.41% cost) | **0.12–0.14R** | **0.07–0.08R** |
| Illiquid fill (0.92% cost) | **0.31R** | **0.18R** |

## Verdict

Overlaying the two sides:

- **Best case** (wide box, liquid fill): cost ≈ 0.07R against gross
  expectancy up to 0.2R → **net ≈ +0.13R.** Comfortably positive.
- **Worst case** (tight box, illiquid fill): cost ≈ 0.31R against gross
  expectancy as low as 0.05R → **net ≈ −0.26R.** Comfortably negative.
- The two ranges overlap through most of the middle. **The arithmetic alone
  cannot sign the expectancy** — it depends on where the real system's win
  rate, R-multiple, box width, and actual breakout-fill slippage fall, none
  of which are measured yet.

This is not a failure of the exercise — it's the correct outcome for a
zero-code check. The edge is **not** obviously dead on arrival (ruling out
"stop here, save a sprint"), but it is **not** comfortably clear of costs
either (ruling out "skip straight to the veto instrumentation"). That
leaves exactly one next step: **S7-3**, the sample backtest, which measures
the real win rate, R-multiple, and slippage distribution instead of
sketching plausible ranges for them.
