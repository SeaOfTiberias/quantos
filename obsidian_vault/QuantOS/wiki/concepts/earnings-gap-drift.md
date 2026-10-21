---
title: Earnings-Gap Drift (price/volume PEAD proxy)
compiled: 2026-10-21
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: earnings-gap-drift
candidate: "gut-check"
family: event-drift
instrument: equity-cash
status: closed
verdict: FAIL
first_tested: 2026-10-21
verdict_date: 2026-10-21
profit_factor:
sharpe:
trades: 2653
bar: "Market-adjusted 20-session excess return of the expected sign in both 2016–2020 and 2021–2026 (pre-registered)"
headline: "Buying after a ±5% move on ≥ 4× volume, entered the next day, shows no up-drift (median stock lags the market) and only a small, fading down-drift that reversed in 2025–26 — not a signal."
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-21-earnings-gap-drift-gut-check-price-volume-proxy-for-pead
---

# Earnings-Gap Drift (price/volume PEAD proxy)

> [!abstract] Compiled page
> Written from `[[2026-10-21-earnings-gap-drift-gut-check-price-volume-proxy-for-pead]]` on 2026-10-21. Context and retrieval only — rules in this layer never execute.

## Definition

A test of whether NSE F&O stocks keep drifting after a results-style shock, using only price and volume: a one-day close-to-close move of at least ±5% on at least 4× the trailing 50-session average volume stands in for a results surprise. It was run to decide whether to chase TechM (+8.5% on 8× volume) and HCLTech (+8.4% on 7×) with call spreads in October 2026 `[[2026-10-21-earnings-gap-drift-gut-check-price-volume-proxy-for-pead]]`.

## Mechanics

- **Data**: NSE cash bhavcopy, 2016-01-01 to 2026-06-25 (2,586 sessions), EQ series.
- **Universe**: the 213 stocks with F&O contracts on 2026-10-19, close ≥ ₹50. This carries survivorship bias, which favours finding up-drift.
- **Events**: at most one per stock per 20 sessions. Windows containing another single-day move > 35% are dropped as likely corporate actions.
- **Entry**: the close of the session *after* the event.
- **Measure**: return over 5/10/20 sessions minus the equal-weight universe over the same window.
- **Pass**: same-sign excess in both 2016–2020 and 2021–2026, fixed before results were seen.
- No option prices or costs are modelled.

`[[2026-10-21-earnings-gap-drift-gut-check-price-volume-proxy-for-pead]]`

## Results

| Side | n | 20d excess (all) | 2016–2020 | 2021–2026 | 20d median | Beat market | Verdict |
|---|---|---|---|---|---|---|---|
| Up | 1,870 | +0.26% (t 1.1) | −0.25% | +0.57% (t 1.8) | −0.82% | 45.5% | **FAIL** (sign flips) |
| Down | 783 | −0.79% (t −2.3) | −1.30% (t −2.4) | −0.45% (t −1.0) | −1.39% | 43.4% | passes sign test, weak and decaying |

Up side:
- The small positive mean comes from a minority of large winners. The *typical* stock lags the market afterwards.
- A capped bull call spread forfeits exactly that tail.
- Volume ≥ 8× gave +1.13% (t 2.5), but its median is still −0.13%, and it was one of several cuts looked at after the fact.

Down side:
- Larger drops drift more: moves ≤ −8% gave −1.79% over 20 sessions (t −3.5).
- But yearly 20d excess turned positive in 2025 (+0.57%) and 2026 (+2.15%). Recent big down-gappers have *outperformed* afterwards.

`[[2026-10-21-earnings-gap-drift-gut-check-price-volume-proxy-for-pead]]`

## Relation to other concepts

- **The price-only cousin of [[pead-earnings-drift]].** That candidate was shelved because results-surprise data was unavailable. This test sidesteps the data problem and finds no tradable long-side drift.
- **Consistent with [[surge-spread-candidate-23]] once the entry day is accounted for.**
  - Candidate 23's Stage 1 entered at the *surge-day close* on +5% surges (any volume, futures, 2019–2026). It found a small 5-day continuation: all surges +0.34% mining / +0.84% holdout, skewed, median −0.13%.
  - This test enters one session later and finds 5-day up excess of −0.02%.
  - Read together, whatever continuation exists sits mostly in the first session after the surge, and is gone by the time a next-day entry is possible.
  - This is an inference from two differently built tests, not a measured result.
- **Option costs would make it worse.** Candidate 23's Stage 2 showed bull call spreads losing the surge continuation to bid-ask. The forward test of that idea at live prices is [[surge-spread-forward-23b]].
