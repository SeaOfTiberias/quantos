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

## Results

_Not run yet._
