---
title: Strategy Search
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/index
quantos:
  layer: wiki
  generated: true
---

# Strategy Search

> [!abstract] Compiled page
> Hub page for every backtested strategy candidate in this project, compiled 2026-09-17 from the methodology/results docs filed under `raw/strategies/`. Context and retrieval only — nothing here executes, and nothing here is a claim that any of these strategies works.

## Definition

The running record of every trading strategy this project has taken through a pre-registered backtest, from Darvas/SEPA (the first, informally tested before this project's pre-registration discipline existed) through candidate 20. One page per candidate, linked below, each carrying its entry/exit rule, cost model, and verdict with the actual numbers — not a summary claim.

## The state of the search, plainly

Of the candidates below with a completed, cost-aware verdict, **exactly one has passed its own pre-registered bar**: [[orb-options-scalping-candidate-18]]. It is not yet live — real capital is gated on a separate go/no-go checklist. Every other completed candidate failed, including several that looked promising on a raw or gross-of-cost read before the project's own cost model or an adversarial review caught the gap. Two candidates are still open (no verdict yet, not failures): [[momentum-turnover-candidate-11]] (a live paper walk-forward, minimum 4 quarters before any verdict) and the ORB [[orb-options-scalping-candidate-18|condition-mining exercise]] on top of the one passing candidate.

Five independently-constructed volatility/regime-conditioning signals were tried and all five failed on their own terms: [[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]], and [[event-proximity-vol]]. This is treated in this project's own record as a closed line of inquiry, not a reason to try a sixth construction.

## Candidates, roughly chronological

| Candidate | Verdict | Bar | Numbers |
|---|---|---|---|
| [[darvas-sepa-s7-3]] | FAIL | PF>1.0, Sharpe>0.5 | PF 0.75, Sharpe -1.25 (realistic); PF 1.11, Sharpe 0.22 (best-case, still fails) |
| [[rs-momentum-rotation-s8-3]] | FAIL (vs. benchmarks) | beats Nifty 500 + Nifty Alpha 50 | -15.6pt vs Nifty 500, -64.6pt vs Alpha 50 |
| [[nifty-ema-options-s8-4]] | FAIL | PF>1.0, Sharpe>0.5 | PF 1.00, Sharpe 0.03 |
| [[vrp-short-strangle]] | FAIL | PF>1.0, Sharpe>0.5 | PF 1.034, Sharpe 0.092 (net) |
| [[regime-classifier-s8-1]] | FAIL | monotonic forward-vol separation | non-monotonic, wrong-direction |
| [[pairs-trading-candidate-12]] | FAIL | PF>1.0, Sharpe>0.5 | PF 0.94, Sharpe -0.17 |
| [[expiry-day-effect-gutcheck-candidate-13]] | weak/inconclusive | visibly exceeds baseline | -10% to +19% vs baseline, thin n=31 |
| [[dow-theory-trend-candidate-14]] | FAIL | PF>1.0, Sharpe>0.5 | PF 0.88 despite Sharpe 2.23 (real rupee loss) |
| [[breakout-1010-banknifty-candidate-15]] | mechanical PASS, synthetic premium only | PF>1.0, Sharpe>0.5 | PF 1.11, Sharpe 0.65; ₹54/trade avg edge |
| [[momentum-turnover-candidate-11]] | OPEN — live paper walk-forward | OOS Sharpe > 0.5 | in-sample Sharpe 0.81 (quarterly); OOS pending, ≥4 quarters |
| [[iv-minus-rv-vol-spread]] | FAIL | Q5 > Q1 earned premium & hit rate | Q5 premium/hit-rate both below Q1 |
| [[nifty-banknifty-option-skew]] | FAIL | monotonic Q1→Q5 forward vol | non-monotonic both underlyings |
| [[ml-factor-combination-candidate-16]] | FAIL | 4-of-4 criteria, all required | beat-baseline criterion is a turnover-cost artifact |
| [[pairs-trading-v2-candidate-17]] | FAIL | PF>1.0, Sharpe>0.5 | PF 1.04, Sharpe 0.14 (bug-fixed re-run) |
| [[atm-iv-term-structure]] | FAIL | monotonic Q1→Q5 forward vol | non-monotonic both underlyings |
| [[orb-options-scalping-candidate-18]] | **PASS** (not yet live) | PF>1.0, Sharpe>0.5, Stressed variant | NIFTY PF 1.23/Sharpe 0.88; BankNifty PF 1.16/Sharpe 0.95 |
| [[candle-confirm-momentum-gutcheck-candidate-19]] | no edge | signal beats unconditional baseline | signal-conditioned move ≈ baseline |
| [[event-proximity-vol]] | FAIL | event days show higher forward vol | event days show LOWER forward vol (wrong direction) |
| [[goodnight-scalper-candidate-20]] | FAIL | PF>1.0, Sharpe>0.5, Stressed variant | PF 0.54, Sharpe -2.80 |
| [[regime-filtered-dual-momentum-s1]] | mixed / not held as validated | PF>1.0, Sharpe>0.5 equity-curve | pooled-trade Sharpe 0.51 passes; equity-curve Sharpe 0.45 and a first/second-half degradation flag do not |
| [[mean-reversion-alpha50-gutcheck-s2]] | weak / not pursued to a backtest | gap visibly exceeds baseline | +0.06 to +0.43pp gaps on a clustered sample |

## Related infrastructure

- [[Stan_Weinstein_Stage_Analysis]] — the stage classifier reused unmodified as a candidate condition in the ORB condition-mining exercise, not itself a backtested strategy.
