# Candle-Confirm Momentum Gut-Check — Methodology (candidate 19)

Fixed BEFORE `scripts/gutcheck_candle_confirm_momentum.py` was run. Do not
change any rule below after seeing a result.

## Hypothesis under test

User's framing: NIFTY and BankNifty "usually follow the direction indicated
by the first or second 1-minute candle for at least the next 10 minutes."
Proposed strategy: buy ATM CE/PE based on the first two 1-minute candles,
hold to stop-loss or trailing stop-loss.

This gut-check tests only the raw directional-persistence claim on the
**index itself** — no options, no premium reconstruction, no stop-loss
levels, no costs, no position sizing. Same sequencing as every prior
candidate in this project (13-18): cheap descriptive check first, full
backtest only if this clears a bar.

## Signal definition (locked via user Q&A, 2026-08-04)

- `candle1` = the session's first 1-minute candle (09:15-09:16 IST).
- `candle2` = the second 1-minute candle (09:16-09:17 IST).
- Direction: `candle1.close > candle1.open` → **CALL bias**;
  `candle1.close < candle1.open` → **PUT bias**;
  `candle1.close == candle1.open` (doji) → no signal, day skipped.
- Confirmation ("candle 2 confirms" — user's chosen rule, option A of 2):
  the trade is only taken if `candle2` does not oppose `candle1`.
  - CALL bias: skipped if `candle2.close < candle2.open` (red).
  - PUT bias: skipped if `candle2.close > candle2.open` (green).
  - `candle2` doji (flat) does not oppose — signal still fires.
- No signal on shortened sessions with fewer than 18 one-minute candles
  (need candle index 17 for the +15-minute robustness readout below).

## Entry / measurement window

- Entry executes at **candle index 2's open** (09:17:00 IST) — the next
  candle's open after the signal candle (`candle2`) closes. Same
  no-same-bar-execution convention as `core/orb_scalping/signal.py` and
  `core/breakout1010/signal.py`.
- Primary forward horizon: **10 minutes** (close of candle index 12,
  i.e. 10 full one-minute bars after entry) — matches the hypothesis's
  own wording ("at least the next 10 minutes").
- Secondary horizons reported for robustness only, not for the verdict:
  5 minutes (candle index 7) and 15 minutes (candle index 17).

## Data

- Fyers 1-minute candles, NIFTY 50 and NIFTY BANK, fetched live
  (chunked to the confirmed 100-day intraday limit — same chunk/retry
  shape as `scripts/backtest_dow_theory_trend.py`'s
  `fetch_chunked_intraday`, resolution parameterized to `"1m"`).
- 1-minute depth confirmed live 2026-08-04 back to at least 2020 (spot
  checks at 30/60/.../2200 days back all returned data) — far deeper
  than needed. Window start dates below reuse the SAME confirmed-safe
  dates already established for 5-minute data in this project (candidate
  14/15), for consistency with the rest of the backtest suite rather
  than chasing the full available depth:
  - NIFTY: 2022-06-01 onward.
  - BankNifty: 2021-06-01 onward.
- NIFTY and BankNifty reported **independently, never pooled** — same
  rule as every prior candidate.

## Metrics reported (descriptive only — no invented significance test)

Per index, per signal direction (CALL bias / PUT bias), separately:

- `n` — number of signal days (after doji/opposed-candle2 filtering).
- Win rate — % of signal days where the +10min forward return is in the
  signaled direction.
- Mean forward return %, mean |forward return| %.
- **Baseline**: the same mean / mean-|.| forward-10-min return computed
  unconditionally over ALL trading days in the window (any candle1/2
  pattern, no filtering) — read the signal-conditioned numbers against
  this, not against zero. A 09:15-09:27 IST window is the most volatile
  part of the session; a naive win-rate or mean-return number with no
  baseline would overstate the edge.
- Selectivity — % of trading days that produced no signal at all
  (doji candle1, or candle2 opposing candle1), reported per index.

## What would make this untrustworthy

- If the "baseline" unconditional forward-10-min move is nearly as large
  as the signal-conditioned move, the signal is not adding information —
  it's just capturing ordinary opening-range volatility that happens in
  either direction regardless of the first two candles.
- Thin `n` after the doji/opposed-candle2 filter (this rule is fairly
  strict — both candles must agree) could leave too few signal days for
  the win rate to be meaningful, especially split by direction.
- This is spot-index return, not option P&L — even a real spot edge can
  be erased by ATM option spread/theta/slippage (candidate 18's own
  ORB signal showed a real spot edge that only barely survived realistic
  option costs). A pass here is necessary, not sufficient.
