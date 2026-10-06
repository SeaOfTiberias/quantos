# IV-Gated Short Premium — Addendum: Data-Quality Rules (2026-10-06)

Addendum to docs/VRP_IV_GATED_METHODOLOGY.md (commit 0749279), which
stays unedited. Written after the first run, and that run is **void**.

## Why the first run is void

The first run (code 02565a6) used 2019-2023 legacy-schema bhavcopy files
that had never been used in this project before. Its results were not
credible. In Segment A, always-on selling returned +327%/yr on margin
(strangle, Sharpe 2.9) and +805%/yr (iron condor). Checking individual
trades showed two data defects, not a market effect:

1. **Untraded contracts carry a placeholder `close`.** Example: 2020-12-11,
   NIFTY 11350 PE (16% OTM): close 423.3, but volume 0, OI 0,
   open/high/low 0. A contract that never traded that day showed a
   price that made a far-OTM strike look like 0.20 delta. The strangle
   "sold" it, it expired worthless, and the run booked a fake profit.
   2023+ files (the original VRP window) had no such selections.
2. **Expiry-day settlement is 0 in early legacy files.** Every expiry
   from 2019-02-14 through 2020-01-30 reports `settle_price` 0.0 on its
   own expiry day. The shared-settlement quirk simulator.py relies on
   only starts holding after that. All of these fell in the gate's
   warm-up (first gated cycle 2020-01-31), so they did not enter the
   verdict figures, but they would have entered any later use.

The first run also produced verdicts (all three arms FAIL in Segment A).
They are not reported as results anywhere, because the inputs were wrong.

## The two rules, applied to every segment

1. **Traded contracts only.** A row is used only if its `volume` > 0 on
   that day. This applies everywhere a price is read on the entry day:
   the put-call-parity forward, the ATM strike and its IV, the strangle
   legs, and the condor wings.
2. **No zero settlements.** A settlement value of 0 (or missing) is
   treated as "missing settlement": the trade is counted as not
   settled, never priced at 0.

Nothing else changes: not the gate (0.67 / 52 / 40), the deltas, the
margin model, the cost schedule, the segments or the pass bar.

## Disclosure

These rules were written after seeing the void run's figures. They are
data-hygiene rules that any options backtest needs, and they were chosen
because of the two defects above, not because of how they move the
result. They don't target either direction: rule 1 can remove trades
that win or lose, and rule 2 only affects warm-up cycles. Still, the
rerun is not as clean as a fully blind pre-registration, and its
write-up must say so.
