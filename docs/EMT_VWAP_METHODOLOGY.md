# EMT (exhaustion mean theory) on NIFTY 5-minute — methodology

Fixed 2026-10-26, BEFORE the backtest was run. The user's idea: when NIFTY stretches
away from its mean on the 5-minute chart, the first bar that turns back toward the mean
is the entry (sell after a stretch up, buy after a stretch down). Choices below were
made by the user from a short list (session 2026-10-26).

## Phase 1 — index points (this document)

**Data.** Fyers 5-minute bars, ~1 year back from the run date: NIFTY 50 index (prices)
and the continuous NIFTY future (`NSE:NIFTY26NOVFUT`, `cont_flag=1`, volume only).
Bars are matched on timestamp; a bar with no futures bar adds no volume.

**Indicators** (all on the index bar, known at its close):
- VWAP: session VWAP, reset 09:15, typical price (O+H+L+C)/4, weighted by futures volume.
- EMA9: 9-period EMA of the close, continuous across days.
- ATR: 14-period Wilder ATR of the 5-minute bars, continuous across days.

**Setup (variant `vwap_ema`, the user's primary).**
- Stretch up at a bar's close: close − VWAP ≥ k × ATR **and** close > EMA9. Stretch
  down is the mirror image. A stretch arms the side and tracks the extreme (highest high
  / lowest low since arming).
- Trigger: the first later bar whose close is lower than the previous close (after a
  stretch up) or higher (after a stretch down), while the close is still on the
  stretched side of the mean. If that bar closes at or through the mean, the side is
  disarmed with no trade.
- Entry: the next bar's open (no look-ahead). Entry bars from 09:30 to 14:30 only. One
  position at a time; a new stretch is needed to arm again. Everything resets daily.

**Exit.**
- Target: price touches the mean. The level for bar j is the mean at bar j−1's close.
- Stop: price trades beyond the extreme of the stretch.
- If target and stop are both inside one bar, the stop counts (conservative). An open
  already through either level exits at the open.
- Flat at the 15:15 bar's open.

**Comparison variants** (reported, never selected over the primary): `vwap` (no EMA9
condition) and `ema` (mean = EMA9 for the stretch, the target and the trigger test).

**Grid.** k ∈ {0.5, 1.0, 1.5, 2.0}.

**Costs.** Results in NIFTY index points. Primary cost: 2 points per round trip (a
proxy for an ATM option's bid-ask plus charges at delta ~0.5). Sensitivity: 1 and 4.

**Split and selection.** Trading days in date order; the first half is in-sample (IS),
the second half out-of-sample (OOS). For each variant, k is chosen on IS only: highest
net mean points per trade with at least 30 IS trades. OOS is reported for that k, and
the full grid is shown for transparency.

**Pass bar (primary variant, OOS, at 2-point cost):** at least 40 trades, net mean > 0,
profit factor ≥ 1.2. Anything else is FAIL, and the idea is not taken to options.

## Addendum 2026-10-26 — BankNifty (fixed before its run)

The user asked for the same test on BankNifty after NIFTY failed. Rules, grid, split,
selection and pass bar are unchanged. Data: NIFTY BANK index with the continuous
BANKNIFTY future (`NSE:BANKNIFTY26NOVFUT`) for volume. Costs scale with the index level
(BankNifty is about 2.3× NIFTY): primary 5 points per round trip, sensitivity 2.5 and 10.
Results are reported on their own, never pooled with NIFTY. Because this is a second
try of the same idea, a BankNifty PASS would need a forward paper run before any
options work, not straight to Phase 2.

## Phase 2 — ATM options (only if Phase 1 passes)

Not run yet. The option-chain recorder holds only 3 sessions (last 2026-10-07), too few
to price a year of trades. If Phase 1 passes, the options test needs a premium source to
be agreed first (e.g. restart the recorder and forward-paper the signals).
