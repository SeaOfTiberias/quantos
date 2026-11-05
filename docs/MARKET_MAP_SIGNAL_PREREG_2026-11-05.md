# Market Map HTF layer: signal pre-registration (DRAFT 2026-11-05, for the user's approval)

Sprint S4. Written before any L1 code exists and before any outcome is seen. It runs in S8, on
the engine S5 builds exactly to `docs/MARKET_MAP_DEFINITIONS.md` v1 (frozen 0067700).

**The question:** do the v1 higher-timeframe levels and zones mark places where price turns more
often than comparable prices that aren't levels? Each family is tested separately, then the HTF
strong zone, then Ochoa's three hot zones. This is not a P&L test. Anything that passes becomes a
filter or flag (S8); a trading rule built on it needs its own pre-registration.

**Out of scope here:** the biases (two-period relationships, CPR and value-area width, CPR
trend, premium/discount, alignment). They are situations, pre-registered in S7. The 2026-11-04
FAIL of the 100-day price map (`docs/PRICE_MAP_ZONES_PREREG_2026-10-28.md`) is a different
definition and doesn't carry over either way.

## What S3 taught, and how this test uses it

| S3 lesson (2026-11-04) | Here |
|---|---|
| A wider band rejects more often by construction (rejection from the near edge, break from the far edge). The weak-zone "pass" was width. | Every control is width-matched: the placebo is the same band mirrored, and the strong-vs-single-family comparison is within width bins. |
| The frozen placebo rule produced almost no placebos, so amendment 2 was needed. | The placebo rule and its one fallback are both fixed here, chosen by a count-only check whose threshold is fixed here too (§5). |
| Support and resistance differences ran in opposite directions (−4.3 / +2.1 pp): in a rising sample, supports hold and resistances break, level or not. | The primary measure is **side-balanced**: the mean of the support difference and the resistance difference (§6). |
| The universe was today's F&O list (survivorship). | The universe is chosen on each date from the bhavcopy, delisted names included (§1). |

## 1. Data and no look-ahead

- **Bars:** NSE daily bhavcopy, split- and bonus-adjusted (`core/techno_funda/prices.py`), 2010-01-01 to 2026-10-23. Weekly, monthly, quarterly and yearly bars are built from them as definitions §0 says. A stock's record that restarts at an unexplained jump (a new SEGMENT in `prices.py`) starts afresh: no element crosses a segment boundary.
- **Universe on date D:** NSE EQ-series stocks ranked in the top 500 by median daily traded value (`TOTTRDVAL`) over the 60 sessions before D. Delisted and renamed stocks take part while they qualify. Indices are not in this test (their history arrives in S6).
- **Event period:** sessions from 2013-01-01 to 2026-09-22. The start leaves three years for monthly structure and ATR warm-up. The end leaves 20 sessions of outcome before the data ends.
- **Point in time:** the map for D is built only from bars completed before D (definitions §0). Weekly elements change at most once a week, monthly ones once a month, and so on. A swing counts only from its confirmation bar.
- **Not testable historically:** the weekly money zone and weekly VPOC need 5-minute bars (definitions §4), which exist only for the last 100 days. They are left out of this test and stay "untested". Monthly, quarterly and yearly profiles come from daily bars and are in.
- **ATR:** ATR(W) as of D, from completed weekly bars (definitions §0). Every distance below is in ATR(W).

## 2. What is tested (the hypotheses)

Each row is one hypothesis: its events against its own placebos.

| # | Hypothesis | Elements (definitions v1) | Band |
|---|---|---|---|
| H1 | structure | swing highs/lows, protected and weak levels (§1–2), multi-touch levels (§3.2) | the level, or §3.2's min–max |
| H2 | imbalance | demand/supply zones (§3.1), order blocks (§3.3), LVN edges (§5) | the zone, or the level |
| H3 | liquidity | EQH/EQL while live (§3.4) | the level |
| H4 | volume | M/Q/Y money zone and VPOC levels, their virgin levels, HVN shelves (§4, §5) | the level, or the shelf |
| H5 | pivot | floor, CPR, Camarilla and the previous period's high/low that are map levels (§4) | the level; the CPR is [BC, TC] |
| H6 | HTF strong zone | clusters with ≥ 2 families (§6) | the cluster |
| H7 | DPZ | Ochoa's double pivot hot zone (§6.1) | min–max of its members |
| H8 | GPZ | Ochoa's golden pivot zone (§6.1) | the period's CPR [BC, TC] |
| H9 | MTZ | Ochoa's multiple timeframe hot zone (§6.1) | min–max of its members |

- An element is in a hypothesis from the bar it exists until it is invalidated, retired or broken (by its own v1 rule). Pivots live for their period only.
- Elements that are computed and shown but not map levels (definitions §4: H5/L5; weekly and quarterly R3/R4/S3/S4; hidden layers) are not tested.
- **Overlapping elements of one hypothesis** that are entered on the same day count as one event, on the union of their bands.

## 3. The event

On session D, price **enters** a band [low, high] when:

1. the close of D−1 is more than **0.1 ATR(W)** outside the band; and
2. D's high–low range overlaps the band.

- Previous close above the band: a **support** test, near edge = high. Below: a **resistance** test, near edge = low.
- **One event per stock per hypothesis per band per session.**
- **Skip rule:** a band of the same stock and hypothesis that overlaps an event counted in the previous **10 sessions** is skipped. This keeps one drawn-out test from counting several times. Placebos are de-duplicated the same way, within their own kind.

## 4. The outcome

First passage on **daily closes**, from D's close through the close of D+19 (20 sessions):

- **Rejected:** a close beyond the near edge by **0.5 ATR(W)**, back the way price came (support: close ≥ high + 0.5 ATR(W)).
- **Broken:** a close beyond the far edge by **0.5 ATR(W)** (support: close ≤ low − 0.5 ATR(W)).
- **Neither in 20 sessions:** a timeout. It is reported and left out of the rate.
- Closes are used, not highs and lows, for two reasons: v1 breaks are close-based (definitions §0), and closes are in time order, so the S3 question of which print in a bar came first doesn't arise.

**Rejection rate** = rejected / (rejected + broken).

## 5. Placebo (width- and distance-matched)

**Built per candidate, not per event** (S3 amendment 1 B). A candidate is every band of the hypothesis on D with the previous close C more than 0.1 ATR(W) outside it.

- The placebo band is the band mirrored through C: [2C − high, 2C − low]. It has the same width and the same distance from C, on the other side, and is tested from the opposite side.
- It then goes through the same event and outcome rules. If price never enters it, there is no placebo event.

**Validity, rule P1 (primary).** The placebo band must be:
- more than **0.3 ATR(W)** from every HTF strong zone (§6 of the definitions) on D; and
- not overlapping any element of the hypothesis under test (no padding).

**Fallback, rule P2.** The placebo band must not overlap any element of the hypothesis under test, with no padding (the strong-zone clearance is dropped).

**Choosing between them: a count-only check, before any outcome.** Once S5's engine exists, a runner pass over every third session counts, for each hypothesis, the events and the entered P1 placebos. It looks at **counts only, never outcomes**, and its output is committed before the full run.
- A hypothesis uses P1 if its entered P1 placebos number at least **25% of its events** and at least **300**.
- Otherwise it uses P2 under the same two thresholds.
- If P2 also falls short, the hypothesis is reported as **not testable (placebo scarcity)**. That is neither a pass nor a fail. No third rule is invented.
- For H6 (strong zones), the P1 clearance from other strong zones still applies, since a band can't be cleared from itself.

## 6. Measures

- **Per side:** support difference = zone support rate − placebo support rate; likewise for resistance. (A placebo's side is its own test side.)
- **Primary measure, side-balanced difference** = (support difference + resistance difference) / 2.
- **Bootstrap:** 10,000 resamples of **calendar weeks** with replacement, seed 20261105. Each resample takes every event and placebo event of the drawn weeks. Weeks are used because events across stocks move together, and the 20-session outcomes overlap.
  - 95% interval: the 2.5th–97.5th percentile of the side-balanced difference.
  - Two-sided p-value: 2 × min(share of resamples ≤ 0, share ≥ 0).
- **Multiple testing:** Holm–Bonferroni over the hypotheses that are testable (up to nine), at a family-wise α of 0.05.

## 7. Pass criteria, each hypothesis separately (all must hold)

1. Side-balanced difference **≥ 5 percentage points**.
2. Its bootstrap p-value **passes Holm** at α = 0.05 across the testable hypotheses.
3. Side-balanced difference **above 0 in both halves**, split at the hypothesis's median event date.
4. Side-balanced difference **above 0 on both sides**: the support difference and the resistance difference are each above 0.
5. At least **300 events** with an outcome, and at least **300 placebo events** with an outcome.

**Additional criteria for two hypotheses:**
- **H8 GPZ: GPZ CPR against plain CPR.** Ochoa's claim is that a GPZ is stronger than the CPR alone. So H8 must also beat the CPR bands of the same period kinds that are **not** GPZs, within CPR-width terciles (the mean of the tercile differences, side-balanced): **≥ 5 pp**, with a bootstrap 95% interval that excludes 0.
  - Definitions §6.1 shows that an H3/L3 GPZ is exactly a period that closed in the bottom/top 22.5% of its range. A pass is reported as "the CPR after a close in the outer 22.5% of the range turns price", which is what it measures. GPZs with a money-zone member are reported separately.
- **H6 strong zone: against single-family elements.** Strong zones must beat single-family bands within the same **width bins** (0, (0, 0.25], (0.25, 0.5], > 0.5 ATR(W); mean of the bin differences, side-balanced) by **> 0**. This replaces S3's unmatched criterion 4.

A fail is reported as a fail, hypothesis by hypothesis. Thresholds, windows, the universe and the v1 definitions are not re-tuned in this round.

## 8. Reported only (not part of pass or fail)

- Per timeframe of the element: W, M, Q, Y. For H5, per pivot kind (floor, CPR, Camarilla, previous high/low).
- **Virgin levels by age:** 1, 2–3, 4–12 and > 12 periods (definitions §4: "the signal test scores by age").
- **H3 liquidity:** the sweep rate (a wick beyond the level and a close back inside on the same day) against placebo. SMC reads EQH/EQL as targets that get swept, which a rejection rate alone doesn't capture.
- **H9 MTZ:** the rate by the number of periods in the zone (2, 3, 4).
- **H6:** the family combinations in the zone.
- **Weinstein stage split**, as S3 amendment 1 A: stage × side, with and against the HTF trend.
- ATR% terciles, band-width terciles, timeouts, and the two eras 2013–2019 and 2020–2026.
- Which placebo rule (P1 or P2) each hypothesis used, and the count check behind it.

None of these changes a verdict. A strong cell in a failed hypothesis is a lead for a new, separately pre-registered test, never a rescue.

## 9. Afterwards

- **A pass:** in S8 the hypothesis's elements are promoted to screener filters and `pick_structure` flags that affect ranking, with "passed its test" on every screen. Alerts and filters, never orders. Any exit or entry rule built on them needs its own pre-registration and the user's go-ahead.
- **A fail:** the elements stay on the map as markers, labelled "failed its test". No trigger, alert or filter is built on them. A v2 definition is new and needs its own test.
- **Not testable:** labelled "untested (placebo scarcity)", and treated like a fail for filters.
- The S10 re-look at failed strategies may use only conditions that passed here.

## 10. Order of work

1. The user approves this document; it is committed. Only then does S5's L1 code start.
2. S5 builds the engine and the runner, with unit tests on synthetic fixtures.
3. The count-only check (§5) runs and its counts are committed before the full run.
4. S8 runs the full test once and commits the results before reporting them.
