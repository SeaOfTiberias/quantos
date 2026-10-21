# Earnings-gap drift gut-check (price/volume proxy for PEAD)

**Date:** 2026-10-21 · **Script:** `scripts/gutcheck_earnings_gap_drift.py` · **Verdict:** FAIL for the long side, weak/decaying for the short side — not adoptable as a signal.

## Why

TechM (+8.5% on 8× volume) and HCLTech (+8.4% on 7× volume) gapped up on results the week of 2026-10-15, and the question was whether to chase them with call spreads. The textbook answer is post-earnings-announcement drift (PEAD): after a big results surprise, prices keep moving the same way for weeks. The earlier PEAD candidate was shelved as inconclusive because it needed fundamental-surprise data (XBRL results) we could not get reliably. This version needs only price and volume: a large one-day move on very heavy volume stands in for "results surprise".

## Pre-registered design (written before any result was seen)

| Item | Rule |
|---|---|
| Data | NSE cash-market bhavcopy, 2016-01-01 to 2026-06-25 (2,586 sessions), EQ series |
| Universe | The 213 stocks with F&O contracts on 2026-10-19 (`agent/universe_fno_2026-10-19.txt`), close ≥ ₹50 |
| Up event | Close / previous close − 1 ≥ +5% **and** volume ≥ 4× the trailing 50-session average (day itself excluded) |
| Down event | Same with ≤ −5% |
| De-duplication | At most one event per stock per 20 sessions |
| Entry | Close of the session **after** the event (what a trader can actually get) |
| Measure | Return over 5 / 10 / 20 sessions from entry, minus the equal-weight average of the universe over the same window (market-adjusted "excess") |
| Corporate actions | Any window containing a single-day move > 35% (other than the event) is dropped |
| Pass condition | Excess return of the expected sign in **both** halves (2016–2020 and 2021–2026) |

Known bias: survivorship. Today's F&O list includes stocks that did well enough to stay in (or get into) F&O, which favours finding up-drift. No option prices or costs are modelled; this tests the underlying only.

## Results

Baseline: any stock, any 20-session window, raw mean +1.77% (median +1.19%).

### Up events (n = 1,870)

| Subset | n | 5d excess | 10d excess | 20d excess | 20d median | 20d beat market | t (20d) |
|---|---|---|---|---|---|---|---|
| All | 1,870 | −0.02% | +0.07% | +0.26% | −0.82% | 45.5% | +1.1 |
| 2016–2020 | 710 | −0.25% | +0.07% | **−0.25%** | −0.72% | 46.3% | −0.7 |
| 2021–2026 | 1,160 | +0.12% | +0.08% | +0.57% | −0.90% | 44.9% | +1.8 |
| Volume ≥ 8× | 525 | +0.05% | +0.15% | +1.13% | −0.13% | 49.3% | +2.5 |
| Move ≥ 8% | 814 | +0.01% | +0.05% | +0.44% | −0.82% | 45.7% | +1.0 |

By year (20d excess): 2016 +0.91, 2017 +0.01, 2018 +0.01, 2019 +0.57, 2020 −1.74, 2021 −0.69, 2022 +0.07, 2023 +1.81, 2024 +1.10, 2025 +0.12, 2026 +1.25.

**Fails the pre-registered test** (sign flips between halves). The typical (median) stock *lags* the market after a big up-gap, and only 45% beat it over 20 sessions; the small positive mean comes from a few large winners. A bull call spread caps exactly those winners, so for the way this would be traded the result is worse than the mean suggests. The volume ≥ 8× subset (t +2.5) was one of several cuts looked at after the fact and still has a negative median; treat it as a lead, not a finding.

### Down events (n = 783)

| Subset | n | 5d excess | 10d excess | 20d excess | 20d median | 20d beat market | t (20d) |
|---|---|---|---|---|---|---|---|
| All | 783 | −0.34% | −0.56% | **−0.79%** | −1.39% | 43.4% | −2.3 |
| 2016–2020 | 315 | −0.49% | −0.64% | −1.30% | −1.85% | 40.0% | −2.4 |
| 2021–2026 | 468 | −0.23% | −0.50% | −0.45% | −0.84% | 45.7% | −1.0 |
| Volume ≥ 8× | 250 | −0.26% | −0.72% | −1.05% | −1.58% | 42.8% | −1.9 |
| Move ≤ −8% | 368 | −0.83% | −1.28% | **−1.79%** | −2.02% | 40.2% | −3.5 |

By year (20d excess): 2016 −1.48, 2017 −1.88, 2018 −0.23, 2019 +0.31, 2020 −4.24, 2021 −2.80, 2022 −1.78, 2023 −1.72, 2024 −0.03, **2025 +0.57, 2026 +2.15**.

Passes the sign test (negative in both halves), and larger drops drift more. But the effect is small (about −1% to −2% over 20 sessions versus the market), the recent half is not significant (t −1.0), and in 2025–2026 big down-gappers have *outperformed* afterwards. Decaying or reversed; not enough on its own to pay option spreads.

## What it means for discretionary trades

- Chasing a stock after a big results gap-up is not supported: the median outcome is underperformance. Waiting for a pullback, or skipping, is consistent with the data.
- A bearish trade after a big results drop had a historical tailwind, but it has faded and recently reversed; it needs its own reason (e.g. a confirmed support break) rather than relying on drift.

## Status

Gut-check only. Not a strategy candidate; no rules derived. A follow-up worth running if this line is reopened: the volume ≥ 8× up-subset on a holdout period with costed option spreads.
