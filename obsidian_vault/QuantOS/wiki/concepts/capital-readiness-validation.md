---
title: Capital-Readiness Validation
compiled: 2026-10-13
tags:
  - wiki/concept
  - process/validation
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-quantos-full-project-state-for-external-review, 2026-10-13-candidate-18-orb-options-scalping-real-capital-tracked-equit, 2026-10-13-candidate-18-orb-options-scalping-capital-allocation-positio, 2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p
---

# Capital-Readiness Validation

> [!abstract] Compiled page
> Written from `[[2026-10-13-quantos-full-project-state-for-external-review]]`, `[[2026-10-13-candidate-18-orb-options-scalping-real-capital-tracked-equit]]`, `[[2026-10-13-candidate-18-orb-options-scalping-capital-allocation-positio]]` and `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

The second stage of this project's validation, after the cheap statistical screen. A candidate that passes the pooled per-trade test (`has_positive_edge`: profit factor > 1.0 and Sharpe > 0.5) is replayed through a cash-and-positions ledger at real starting capitals and sizing policies. That answers what pooled statistics cannot: whether the account survives, what sizing is safe, the drawdown in rupees, and how efficiently capital is used `[[2026-10-13-quantos-full-project-state-for-external-review]]`.

## Mechanics

- **Why it exists**: the pooled screen sums each trade's percentage return with no compounding and no sizing. Until 2026-09-24 it also used a hard-coded annualisation (144 trades a year) that overstated Sharpe for slow strategies and understated it for fast ones. Nothing in the process required the ledger stage when a candidate first passed. Candidate 11 passed in July, and the ledger approach only appeared in late September, prompted by an unrelated bug hunt `[[2026-10-13-quantos-full-project-state-for-external-review]]`.
- **Equity curve**: one account, one cash pool, trades skipped when cash runs short. Metrics: CAGR, daily-return Sharpe, Sortino, Calmar, Ulcer Index, max drawdown in % and ₹, drawdown duration, and trades skipped `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]`.
- **Sizing**: Kelly fractions are derived on the mining window only and tested on the untouched holdout `[[2026-10-13-candidate-18-orb-options-scalping-capital-allocation-positio]]`. Where many positions are open at once, single-trade Kelly is the wrong tool. Darvas Bucket B averaged 12.2 open positions (max 29), so its fraction was grid-searched on the real overlapping trade history instead (`optimal_fraction_by_growth`, 9% of equity) `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]`.

## What it found

| Candidate | Finding |
|---|---|
| [[orb-options-scalping-candidate-18]] | A **cliff**: ₹50,000 fell to about ₹1,965 (97.7% max drawdown), while ₹55,000 compounded to about ₹5.1L. A lot costs ₹7,000–25,000, and once early losses push cash below that, the account is locked out of the trades that would let it recover. Under fixed 1-lot sizing every tier from ₹60,000 up earned the same absolute profit, so extra capital sat idle `[[2026-10-13-candidate-18-orb-options-scalping-real-capital-tracked-equit]]`. On the holdout, full Kelly (31%) still drew down 74–93%. Quarter to half Kelly (about 8–16%) with at least ₹1L was the defensible range `[[2026-10-13-candidate-18-orb-options-scalping-capital-allocation-positio]]` |
| [[darvas-atr-stop-bucket-b]] | No cliff (equities size down smoothly). The problem was capacity, not survival. At about 9% per trade with ₹1–2.5L or more, it was cleanly profitable with the smallest drawdowns tested `[[2026-10-13-darvas-atr-stop-bucket-b-real-capital-tracked-equity-curve-p]]` |

## Relation to other concepts

[[strategy-search]] is the record of the first-stage screen across every candidate. This page covers the second stage, which only [[orb-options-scalping-candidate-18]] and [[darvas-atr-stop-bucket-b]] reached. [[rs-momentum-rotation-s8-3]] is the earlier warning of the same gap: a pooled-trade pass that lost to both benchmarks once tracked as a real account.
