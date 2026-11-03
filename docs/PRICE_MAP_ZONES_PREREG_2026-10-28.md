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

**Placebo**

- For a strong-zone event at [low, high] with previous close C, the placebo band is the zone mirrored through C: [2C − high, 2C − low].
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

## Results

_Not run yet._
