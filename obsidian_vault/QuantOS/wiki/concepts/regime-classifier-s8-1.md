---
title: VIX-Level Regime Classifier (S8-1)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/failed
  - vol-conditioning
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-s8-1-regime-classifier-validation
---

# VIX-Level Regime Classifier (S8-1)

> [!abstract] Compiled page
> Written from `[[2026-09-17-s8-1-regime-classifier-validation]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

`core/regime/classifier.py`'s production regime classifier, which scores India VIX into absolute LOW/ELEVATED/HIGH/EXTREME/etc. bands (TRENDING_BULL, TRENDING_BEAR, RANGING, VOLATILE, UNCERTAIN) — this is the first of five independently-constructed volatility/regime-conditioning signals this project tested, and the one already live in production code, checked here against what it was actually meant to predict.

## Mechanics

Replayed 1254 real trading days (2021-06-28 to 2026-07-17), scoring each day's regime label and comparing it against that day's own forward NIFTY return (5/10/20-day) and forward 20-day realized volatility.

## Verdict

**FAIL** — the classifier does not reliably separate forward outcomes `[[2026-09-17-s8-1-regime-classifier-validation]]`:

| Regime | n | Mean 10d fwd % | Mean 20d realized vol |
|---|---|---|---|
| TRENDING_BULL | 334 | 0.41 | 0.63 |
| TRENDING_BEAR | 106 | 0.39 | 0.85 |
| RANGING | 172 | -0.33 | 0.83 |
| VOLATILE | 39 | 1.93 | 1.27 |
| UNCERTAIN | 603 | 0.46 | 0.83 |

Two specific failures: TRENDING_BEAR precedes a slightly *higher* forward return than TRENDING_BULL, and RANGING's forward realized vol (0.83) is not meaningfully lower than VOLATILE's (1.27) despite VOLATILE having the *highest* mean forward return of any label — the classifier does not separate calm from turbulent the way its own naming implies, and the system that reads it cuts position size on VOLATILE, the regime that historically preceded the best forward returns.

## Relation to other concepts

The structural diagnosis of this failure — VIX is scored as an absolute *level*, never checked against whether that level was actually justified by what volatility did next — directly motivated [[iv-minus-rv-vol-spread]], the first of four follow-on attempts to build a vol signal that does check the payoff rather than the level alone. All five attempts in this line ([[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]], [[event-proximity-vol]]) failed independently; see [[strategy-search]] for the closed-line summary.
