# Buy the S3 flush, at map demand: pre-registration (2026-11-17)

Written and committed before any run. The user approved it on 2026-11-17.

**Where it came from.** The descriptive study of the same day (`R3_BREAKOUT_PREREG_2026-11-17.md`, addendum) found that F&O stocks closing below ET's S3 out-gain the baseline over 10 sessions in both halves: +1.47% vs +1.30% in 2021–23 and +1.23% vs +0.60% in 2024–26. It was the only pivot-screen pattern of the day that held in 2024–26. That finding is the source, so this test is not independent of it. The pass mark is therefore set on the trade, net of costs, in 2024–26 by itself.

## Signal

The signal is a daily close below S3 = P − 2(H − L) of the previous session (ET's levels, checked to the paisa). The previous close must not have been below its own S3.

- **Universe:** F&O stocks in the 2026-11-13 Fyers master that are in the L1 store (218).
- **Period:** 2021-01-01 to the last date with 10 sessions after it.
- **Data:** split- and bonus-adjusted daily bars.

## Map groups, fixed before the run

The map is the L1 card (`core.market_map.card.card` over `structure.l1_read`), built from bars through the signal day. Nothing after the signal day is used.

- **MAP:** at least one of these holds.
  - (a) The close sits inside a daily zone of kind demand, bull OB or bull FVG (`zones_d.inside`).
  - (b) The close sits inside an HTF zone (`zones.inside`).
  - (c) Sweep and hold: a level from `call_plan.structural_levels(card, bars, "CE")` lies within the signal bar. That is, low ≤ level ≤ close, and the level is taken from the card of the previous session so that the flush itself does not move it.
- **NO MAP:** every other signal.

## Trade

- **Entry:** the next session's open.
- **Stop:** the signal bar's low − 0.1 × ATR(14).
- **Target:** `call_plan.target(card, "CE", entry)`, the nearest level at least 1 ATR above, if it is at least 1R away; otherwise 2R.
- **Exit:** after 10 sessions, at the close. A bar touching both the stop and the target counts as a stop.
- **Costs:** R is net of 0.25% of the entry price per round trip.

Ten-session excess means the return from the next open to the close 10 sessions on, minus the equal-weight universe over the same span, minus 0.25%.

## Pass

There are two scored hypotheses, each judged on its own.

- **H1, MAP group:** all of these must hold:
  - mean net R ≥ +0.20 in 2024–26, with n ≥ 75 there;
  - mean net R ≥ 0 in 2021–23;
  - 10-session excess > 0 in both halves;
  - mean net R above the NO MAP group in 2024–26 (otherwise the map adds nothing).
- **H2, every S3 signal:** mean net R ≥ +0.20 in 2024–26 with n ≥ 150, ≥ 0 in 2021–23, and 10-session excess > 0 in both halves.

Anything else is a FAIL, reported as failed and not re-tuned this round.

## Reported, not scored

- Entry at the signal close instead of the next open.
- Whether NIFTY itself closed down more than 1% that day (a market flush vs a stock-specific one).
- The MAP sub-kinds (a), (b) and (c) separately.

Before the full run, five worked cases are printed and checked by hand.

## If it passes

It goes into the call plans as a long pick source, on paper, next to Darvas. The 20:00 job would flag new S3 flushes that sit at map demand. It would not go to real money: that still needs the forward paper record and the user's release.
