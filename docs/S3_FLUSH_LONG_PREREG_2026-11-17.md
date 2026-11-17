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

## Amendment before the full run (2026-11-17, from the worked cases, no results seen)

HDFCBANK on 2026-09-09 closed at its low and opened there the next day. The registered stop (the low − 0.1 ATR) sat 0.19% below the entry, so the 0.25% cost alone was −2.3R. A stop that close is an artefact of the rule, not a trade anyone would take.

**Amended stop:** the lower of (the signal low − 0.1 × ATR) and (the entry − 0.5 × ATR). Everything else is unchanged.

The other worked cases (TATACONSUM 12 flushes, 8 MAP; HDFCBANK 17, 6 MAP; COALINDIA 2026-01-20, 04-10 and 07-28) classified as the definitions say:
- TATACONSUM 2026-09-28: close 960, inside D bull OB 953–969.3 and W demand 930.1–963.7;
- COALINDIA 2026-04-10: inside W bull OB 408.1–434.8; target the W CPR BC 450.46; hit, +1.6R.

## Result (run 2026-11-17, `scripts/research/s3_flush_test.py`): FAIL, H1 and H2

| Group | n | Net R, 2021–23 | Net R, 2024–26 | 10-session excess (2021–23 / 2024–26) |
|---|---|---|---|---|
| H1, MAP | 1497 | −0.21 | −0.02 | −0.78% / −0.34% |
| NO MAP | 2483 | −0.11 | −0.17 | −0.06% / −0.29% |
| H2, every S3 | 3980 | −0.15 | −0.11 | −0.32% / −0.31% |

Bought at the next open, the flush loses in both halves, at map demand or not. The map group does beat the rest in 2024–26 (−0.02 vs −0.17), but it is still below 0.

**Why the descriptive study looked positive.** That study measured from the signal close; this test enters at the next open. The whole bounce is the overnight gap.

| Measure | Overall | 2021–23 | 2024–26 |
|---|---|---|---|
| Entry at the signal close (reported) | +0.21R | +0.24R | +0.18R |
| Entry at the next open (scored) | −0.13R | −0.15R | −0.11R |

**Reported lead, the strongest of the day.** Market flushes: S3 closes on days NIFTY itself fell more than 1%, entered at the signal close.

| Period | n | Close-entry R |
|---|---|---|
| 2021–23 | 871 | +0.44 |
| 2024–26 | 1027 | +0.43 |

Stock-specific flushes made +0.05R and −0.04R. The effect is a market-wide overnight rebound after sell-offs, not a stock signal. It is a candidate for its own pre-registration, testable on NIFTY/BANKNIFTY futures, where costs are smallest. It is not a result.
