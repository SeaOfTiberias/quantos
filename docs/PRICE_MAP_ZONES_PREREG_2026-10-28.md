# Price-map zones: pre-registration (2026-10-28)

Written before the test runs. The question is whether the price map's **strong zones**
(core/price_map, commits fba727f and 3eeea6a) mark places where price turns, more often than
comparable prices that are not zones. This is not a P&L test. If zones pass, a trading rule built
on them (a zone alert, a screener filter, a target in front of a zone) needs its own
pre-registration.

## What is frozen

The zone definition exactly as committed. It is not tuned in this round.

- **Sources:**
  - swing lows and highs that price left by at least 1 ATR(14) within 5 sessions;
  - the 5-minute volume profile over the last 100 calendar days: composite POC, value area, shelves at 1.5 × the median bucket, and naked POCs from the last 20 sessions;
  - daily Camarilla L3/L4/H3/H4 and the daily P;
  - weekly and monthly classical P, S1, S2, R1, R2.
- **Zones:**
  - levels within 0.3 ATR of each other cluster, up to 0.45 ATR wide;
  - weights: swing 2, volume 2, weekly or monthly pivot 1, daily pivot 0.5;
  - **strong** means at least two families agree and the score is at least 4.

## Data and no look-ahead

- **Universe:** every F&O stock in the Fyers master, indices excluded.
- **Period:** 3 Nov 2025 to 27 Oct 2026, about 245 sessions.
- **No look-ahead:** for each stock and each session D, the map is rebuilt from data **before D** only. That means daily bars up to D−1 and 5-minute bars from D−100 days to D−1, the same windows the live map uses. A swing near D−1 counts as soon as the live map would count it.
- **Bars used to score outcomes:** 5-minute bars of session D and the next 4 sessions.

## The event

On session D, price **enters** a strong zone [low, high] when:

1. the previous session's close was outside the zone by more than 0.1 ATR; and
2. a 5-minute bar of session D trades into the zone.

The first such bar is the entry, and the zone edge price reaches first is the **near edge**.

- Coming from above, the zone is tested as support. Coming from below, it is tested as resistance.
- One event per stock per zone per session.
- A zone already entered in the previous 5 sessions is skipped, so a single drawn-out test isn't counted several times.

## The outcome

From the entry bar on, first passage over 5 sessions of 5-minute bars:

- **Rejected:** price trades 0.5 ATR back out of the zone, past the near edge, in the direction it came from.
- **Broken:** price trades 0.5 ATR past the far edge.
- **Both in the same bar:** counted as broken (conservative).
- **Neither within 5 sessions:** a timeout. Reported, and left out of the rate.

**Rejection rate** = rejected / (rejected + broken).

## Controls

- **Placebo levels.** For each strong-zone event, take the same stock and session, and a level the same distance from the previous close on the **opposite** side. It must not be within 0.3 ATR of any zone, strong or weak. The placebo is a band of the same width as the event's zone, and it gets the same event and outcome rules. If no such level exists, that event has no placebo.
- **Weak zones.** Every zone that is not strong, with the same event and outcome rules.

## Pass criteria (all must hold)

1. The strong-zone rejection rate exceeds the placebo rate by **at least 5 percentage points**.
2. A 95% bootstrap confidence interval of that difference, resampling by session, **excludes 0**.
3. The difference is **above 0 in both halves**, split at the median event date.
4. Strong zones beat weak zones: their rejection rate is higher than the weak-zone rate.
5. At least **300** strong-zone events (rejected + broken).

A fail is reported as a fail. Weights, widths, sources and the scoring bar are not re-tuned in this round.

## Reported but not part of pass or fail

- support and resistance separately;
- which family combinations make up the zone;
- ATR% terciles (does it hold on volatile names?);
- timeout rate.

## Afterwards

- **If it passes:**
  - zone alerts for watched stocks ("possible trade opportunity", logged as ideas) go live;
  - a "first obstacle under 0.75R" screener filter gets its own pre-registration.

  Both are alerts or filters, never orders.
- **If it fails:** maps stay as markers for reading a trade, and no trigger is built on them.

---

## Amendment 1 (2026-11-04, before any runner code exists)

Written in Market Map sprint session S3, before the runner exists and before any result is seen.
Nothing above changes: the zone definition, events, outcomes, controls and pass criteria 1-5 stay
frozen. This amendment does two things:

- it adds one reported-only split;
- it writes down the operational rules the text above leaves open, so the runner has no free choices.

### A. Macro-context split (reported only, not part of pass or fail)

The design's nesting principle (docs/MARKET_MAP_ENGINE_DESIGN.md §3) says a micro level behaves
differently with and against the higher-timeframe (HTF) trend. A pooled rate can hide that, so the
split is declared now.

- **Stage on day D:** Weinstein stage of the stock from `core/vault/stages.py` `classify`.
  - The clauses are the `quantos-stages` block of `obsidian_vault/QuantOS/brain/Stan_Weinstein_Stage_Analysis.md` as committed at the time of this amendment.
  - They are evaluated on the stock's Fyers daily bars **up to D−1**.
  - An unclassified result (warm-up) is its own row, never guessed.
- **Cells:** stage (1, 2, 3, 4, unclassified) × test side (support, resistance). For each cell:
  - strong-zone events and rejection rate;
  - placebo events and rejection rate;
  - the difference.
- **Labels:**
  - **with the HTF trend:** support in stage 2, resistance in stage 4;
  - **against it:** resistance in stage 2, support in stage 4;
  - **no HTF trend:** stages 1 and 3.
- The "with" and "against" groups are also reported pooled, with their own session bootstrap (same settings as below).
- None of this changes the verdict. If "with" looks strong and the pooled test fails, the verdict is still FAIL. The split is a lead for a new, separately pre-registered test (sprint S7/S8), not a rescue.

### B. Operational rules (fixed now, not tuned)

**Data**

- **Universe:** the 218 F&O stocks in the VM's Fyers master on 2026-11-04 (`scripts/price_map.py fno_symbols`).
  - Names that left F&O during the year are missing. This survivorship gap is reported, not fixed.
  - A stock with no bars for a session simply has no events that session.
- **Bars:** Fyers, as the live map uses them:
  - daily bars for the 365 calendar days before D (the live `m.daily(s, 365)` window);
  - 5-minute bars for the 99 calendar days before D (`INTRADAY_DAYS`), sessions before D only;
  - outcome 5-minute bars from session D and the next 4 sessions.

  All bars are fetched once, from 2024-06-01 (daily) and 2025-07-20 (5-minute) to 2026-11-03, and then sliced per D. No bar from D or later enters D's map.
- **Map:** `core/price_map/build.build_map(symbol, daily, intraday, D)`, unchanged. `levels.py` has been identical since the pre-registration; `build.py` only gained `shift()`, which the test doesn't use.
- **ATR:** the map's own ATR(14) for D, from completed daily bars before D. Every "0.1 / 0.3 / 0.5 ATR" above uses it.

**Event**

- **Previous close:** the close of session D−1.
- **Entry:** the first 5-minute bar of D whose range overlaps [low, high], when the previous close is more than 0.1 ATR above the zone's high (a support test) or below its low (a resistance test). The near edge is the high for support, the low for resistance.
- **One test per zone per session:** a zone's test side is fixed by the previous close, so each zone gives at most one event on D.
- **The 5-session skip, across rebuilt maps:** maps are rebuilt every session, so "the same zone" is defined as a strong zone of the same stock whose [low, high] overlaps the range of an event already counted in the previous 5 sessions. Such a zone is skipped. Weak zones and placebos are de-duplicated the same way, each within its own kind.

**Outcome** (first passage, 5-minute bars, from the entry bar through the end of session D+4)

- **Rejection:** for support, a high ≥ near edge + 0.5 ATR; for resistance, a low ≤ near edge − 0.5 ATR.
- **Break:** for support, a low ≤ zone low − 0.5 ATR; for resistance, a high ≥ zone high + 0.5 ATR.
- **The entry bar can only break.** Its high (for a support test) may have printed before it entered the zone, and the order of prints inside a bar is unknown. Counting a rejection on it could credit a move that came first, so rejection is checked from the next bar on. This is the conservative reading of "both in the same bar counts as broken".
- **Fewer than 4 later sessions** in the data (events near the end of the period) is a timeout.

**Placebo** (corrected 2026-11-04 in this same amendment, still before any data was fetched or any runner code written)

- **Built per strong-zone candidate, not per event.** A candidate is every strong zone in D's map with the previous close more than 0.1 ATR outside it, which is the set that *can* produce an event.
  - The literal reading ("for each strong-zone event", then the same entry rule on D) would make a placebo exist only when price entered the zone on one side of C *and* the mirror band on the other, on the same day.
  - That restricts placebos to wide two-sided days, a different and break-prone population, and would bias the comparison in the zones' favour.
  - Building placebos from candidates gives them the same distance-from-C distribution as the zones, which is the control's purpose.
- For a strong-zone candidate at [low, high] with previous close C, the placebo band is the zone mirrored through C: [2C − high, 2C − low].
  - The band is the same width, at the same distance from C on the other side, tested from the opposite side. A zone tested as support gives a placebo tested as resistance.
- **Valid** only if the band stays more than 0.3 ATR from every zone of D's map, strong or weak: no zone's [low − 0.3 ATR, high + 0.3 ATR] overlaps it.
- The band then goes through the same entry and outcome rules on D. If price never enters it, there is no placebo event, just as a zone that isn't entered has no event.
- The placebo rate is computed over all placebo events.

**Statistics**

- **Rates:** pooled over events, rejected / (rejected + broken). Difference = strong rate − placebo rate.
- **Bootstrap (criterion 2):** 10,000 resamples of sessions D with replacement, seed 20261104. Each resample takes every strong-zone and placebo event of the drawn sessions. The interval is the 2.5th-97.5th percentile of the difference.
- **Halves (criterion 3):** split at the median strong-zone event date. Placebo events go to the half of their own date.
- **Criterion 5:** counts strong-zone events with an outcome (rejected + broken), timeouts excluded.

---

## Amendment 2 (2026-11-04, the user's decision, before any outcome was seen)

**What a smoke run showed.** A 3-stock smoke run of the runner (f60d7a3) was inspected for event
**counts only**, never outcomes. It showed the frozen placebo rule can't produce a usable control:

- maps hold about 21 zones within roughly ±8 ATR of price, so a band "more than 0.3 ATR from every zone, strong or weak" almost never exists near price;
- on the sampled sessions, 443 of 1,743 strong candidates had a valid placebo, mostly beyond the map's outermost zone, and 1 was entered (against 261 strong-zone entries);
- scaled up, that's about 200 placebo events against about 19,000 strong ones. Criterion 2 would be decided by placebo scarcity, not by the zones.

**The user's choice (rule C), replacing the 0.3-ATR clearance in "Controls":** a placebo band is valid when it is:

- more than **0.3 ATR from every strong zone**, and
- **not overlapping any weak zone** (no padding).

Expected placebo events: about 1,700. Everything else (mirroring through the previous close,
entry and outcome rules, criteria 1-5) is unchanged.

Options considered, with sample counts and no outcomes:

| Rule | Valid placebos | Entered |
|---|---|---|
| frozen (all zones, 0.3 ATR) | 443 | 1 |
| A (strong zones only, 0.3 ATR) | 872 | 36 |
| B (all zones, no padding) | 776 | 14 |
| **C (strong 0.3 ATR + no weak overlap)** | 649 | 8 |

Strong candidates: 1,743; strong zones entered: 261 (3 stocks, every third session).

---

## Results

**Verdict: FAIL**

Run 2026-11-04 01:26 IST by `scripts/run_zone_test.py` on 218 F&O stocks, sessions 2025-11-03..2026-10-27. Events with an outcome (rejected + broken); timeouts reported separately.

| | rejection rate | rejected / scored | events (incl. timeouts) | timeouts |
|---|---|---|---|---|
| strong | 60.1% | 13587 / 22620 | 23162 | 542 |
| placebo | 61.1% | 887 / 1451 | 1463 | 12 |
| weak | 53.9% | 10609 / 19697 | 19847 | 150 |

Difference strong - placebo: **-1.1 pp**, 95% session-bootstrap CI [-4.2, +2.1] pp (10,000 draws, seed 20261104).

Halves, split at the median strong-event date 2026-04-28:

- first: strong 60.2% (n=11262), placebo 61.3% (n=770), diff -1.1 pp
- second: strong 60.0% (n=11358), placebo 60.9% (n=681), diff -1.0 pp

| Criterion | Result |
|---|---|
| 1 strong - placebo >= 5pp | **FAIL** |
| 2 95% CI excludes 0 | **FAIL** |
| 3 diff > 0 in both halves | **FAIL** |
| 4 strong rate > weak rate | pass |
| 5 >= 300 strong events | pass |

### Reported only (not part of pass or fail)

**Support and resistance:**

| side | strong | placebo | diff |
|---|---|---|---|
| support | 59.6% (n=11838) | 63.9% (n=710) | -4.3 pp |
| resistance | 60.5% (n=10782) | 58.4% (n=741) | +2.1 pp |

**Family combinations (strong zones):**

| families | rate | n |
|---|---|---|
| pivot+swing+volume | 61.1% | 10418 |
| pivot+volume | 60.0% | 5447 |
| pivot+swing | 58.8% | 4828 |
| swing+volume | 57.7% | 1927 |

**ATR% terciles** (cuts 2.32%, 3% from strong events):

| tercile | strong | placebo | diff |
|---|---|---|---|
| low | 60.6% (n=7564) | 60.0% (n=510) | +0.6 pp |
| mid | 59.7% (n=7595) | 60.1% (n=494) | -0.4 pp |
| high | 59.9% (n=7461) | 63.5% (n=447) | -3.6 pp |

**Amendment 1 A: HTF stage split** (stage on D from daily bars to D−1):

| stage | side | HTF | strong | placebo | diff |
|---|---|---|---|---|---|
| 1 | support | none | 56.9% (n=1345) | 61.8% (n=68) | -4.9 pp |
| 1 | resistance | none | 61.0% (n=1115) | 57.4% (n=61) | +3.6 pp |
| 2 | support | with | 61.4% (n=5393) | 68.5% (n=165) | -7.1 pp |
| 2 | resistance | against | 61.1% (n=4320) | 59.6% (n=453) | +1.5 pp |
| 3 | support | none | 58.2% (n=1650) | 62.3% (n=122) | -4.1 pp |
| 3 | resistance | none | 61.7% (n=1571) | 53.8% (n=80) | +8.0 pp |
| 4 | support | against | 58.7% (n=3423) | 63.1% (n=352) | -4.4 pp |
| 4 | resistance | with | 59.2% (n=3753) | 58.2% (n=146) | +1.0 pp |
| unclassified | support | unclassified | 55.6% (n=27) | 33.3% (n=3) | +22.2 pp |
| unclassified | resistance | unclassified | 60.9% (n=23) | 0.0% (n=1) | +60.9 pp |

| HTF | strong | placebo | diff | 95% CI |
|---|---|---|---|---|
| with | 60.5% (n=9146) | 63.7% (n=311) | -3.2 pp | [-8.6, +2.4] |
| against | 60.1% (n=7743) | 61.1% (n=805) | -1.1 pp | [-5.4, +3.2] |
| none | 59.4% (n=5681) | 59.2% (n=331) | +0.2 pp | [-5.4, +5.9] |

Note: a placebo's HTF label follows its own test side (a stage-2 placebo tested as resistance is 'against'), so the with/against placebo groups are not the mirrors of the zone groups.

### Notes on reading the results

- **Criterion 4's pass is band width, not information.**
  - Rejection is measured from the near edge and a break from the far edge, so a wider band rejects more often by construction.
  - Weak zones are much narrower than strong ones: median 0.06 ATR against 0.36, and 38% are a single price. Zero-width weak bands reject 50.2% of the time, which is what symmetric geometry gives.
  - The placebo control is width-matched; the weak-zone control is not.
- **The FAIL doesn't depend on that geometry.** Placebos are slightly narrower than strong zones (mean 0.28 vs 0.34 ATR), which favours the zones, and the zones still don't beat them.
- **The HTF split (amendment 1 A) gives no lead.** Zones tested with the higher-timeframe trend are 3.2 pp *below* their placebos, CI [−8.6, +2.4]. No cell suggests a conditioned test worth pre-registering from this result.
- **Data:** 218 F&O stocks (today's list; names that left F&O are missing), Fyers bars fetched 2026-11-04, runner at commit c7eb053 (rules) / 30aa030.
  - Events: `data_cache/zone_test/events.csv` (not committed: derived from cached broker data, regenerable with the two scripts).

### What follows (from "Afterwards", above)

- The price map's strong zones **failed** their test. Maps stay as markers for reading a trade; no trigger, alert-as-opportunity or filter is built on them.
- `map_read` labels these zones "failed its test" instead of "untested" (design §2: a failed item is still shown, never filters).
- The 640-840-type multi-year zones (S5) are a different definition. They get their own pre-registered test in S4; this result doesn't carry over to them either way.
