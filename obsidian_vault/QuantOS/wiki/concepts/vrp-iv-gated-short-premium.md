---
title: IV-Gated Short Premium (VRP Follow-up)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: vrp-iv-gated-short-premium
candidate: "VRP follow-up"
family: volatility-premium
instrument: index-options
status: closed
verdict: FAIL
first_tested: 2026-10-06
verdict_date: 2026-10-06
profit_factor: 0.709
sharpe: -0.397
trades: 50
bar: "Segment A (fresh 2019–2023), net, strangle: PF > 1 and Sharpe > 0.5; gated Sharpe > ungated; no quarter > 50% of P&L; ≥ 30 gated trades"
headline: "Selling NIFTY weekly premium only when ATM IV is in its top third lost money on never-seen 2019–2023 data: high IV arrived at the start of the COVID crash, not after it."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-iv-gated-short-premium-strangle-straddle-iron-condor-methodo, 2026-10-13-iv-gated-short-premium-addendum-data-quality-rules-2026-10-0, 2026-10-13-iv-gated-short-premium-results
---

# IV-Gated Short Premium (VRP Follow-up)

> [!abstract] Compiled page
> Written from `[[2026-10-13-iv-gated-short-premium-strangle-straddle-iron-condor-methodo]]`, `[[2026-10-13-iv-gated-short-premium-addendum-data-quality-rules-2026-10-0]]` and `[[2026-10-13-iv-gated-short-premium-results]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

The proper, pre-registered test of the exploratory pattern in [[vrp-short-strangle]]'s IV-tercile cut, where high entry-IV trades had done far better. It sells NIFTY weekly premium only when at-the-money IV is high relative to its own past year. The verdict was taken only on 2019–2023 data never examined for this question `[[2026-10-13-iv-gated-short-premium-strangle-straddle-iron-condor-methodo]]`.

## Mechanics

- **Segments**: warm-up (first 40 cycles); **A, fresh, 2019 → 2023-07-21 (the verdict)**; B, 2023–2026 (where the pattern was found; reported only); C, from 2026-07-23 (too few cycles to judge).
- **Gate**: ATM IV percentile against the previous 52 cycles ≥ 0.67. When the gate is closed, capital sits idle and earns 0.
- **Arms**: short strangle at about 0.20 delta (primary); short straddle and short iron condor with about 0.05-delta wings (secondary). All held to expiry with no stops.
- **Costs**: real NSE charges with date-correct STT. Returns are on margin (12% of the forward for strangle and straddle; wing width for the condor). Idle weeks count as 0 in the Sharpe series.

`[[2026-10-13-iv-gated-short-premium-strangle-straddle-iron-condor-methodo]]`

**Data-quality addendum.** The first run was voided: always-on selling returned +327% a year on margin. Legacy bhavcopy files carry placeholder closes for untraded contracts, and pre-2020 expiry settlements are 0. The rerun uses traded contracts only (volume > 0) and treats a zero settlement as missing. These rules were written after seeing the void run, so the rerun is not fully blind; they are hygiene and cut profit rather than creating it `[[2026-10-13-iv-gated-short-premium-addendum-data-quality-rules-2026-10-0]]`.

## Verdict

**FAIL, all three arms, Segment A** `[[2026-10-13-iv-gated-short-premium-results]]`:

| Arm | Gated (50 trades) PF / Sharpe / return a year | Ungated (181 trades) PF / Sharpe |
|---|---|---|
| Strangle (primary) | 0.709 / −0.397 / −26.1% | 1.080 / 0.153 |
| Straddle | 1.005 / 0.006 / +0.6% | 1.136 / 0.270 |
| Iron condor | 0.793 / −0.324 / −38.0% | 1.214 / 0.522 |

The gate opened the week of 2020-03-06 (strangle −70.6% of margin) and stayed open through the COVID crash; 2020 Q1–Q2 alone lost −95.7% of margin. In Segment B, the pattern's home, the gated strangle still beat always-on (Sharpe 0.74 vs 0.35). That is what a pattern that doesn't generalise looks like. The ungated condor's 0.52 was never a pre-registered candidate and is not a finding `[[2026-10-13-iv-gated-short-premium-results]]`.

## Relation to other concepts

- Closes the open follow-up listed on [[vrp-short-strangle]].
- The sixth attempt to condition on volatility state, after the five in the [[strategy-search]] record ([[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]], [[event-proximity-vol]]). It differs by gating a premium-selling trade rather than predicting forward volatility, and it failed for a mechanical reason: high IV leads into crashes.
