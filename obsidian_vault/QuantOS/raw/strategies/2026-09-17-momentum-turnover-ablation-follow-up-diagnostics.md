---
title: 'Momentum Turnover Ablation — Follow-Up Diagnostics'
ingested: 2026-09-17
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_RESULTS.md'
checksum: aebac09cb87b426b1c19264c55963abf22a59c3ccd6ebbf7d729c43f27002134
body_checksum: 3256d78d1fadb951204ba11af3bdd560a9626e8f28563aa94520149f9fc8a7a0
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Momentum Turnover Ablation — Follow-Up Diagnostics

> [!info] Ingested source
> Filed 2026-09-17 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_RESULTS.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Methodology: docs/MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_METHODOLOGY.md. Addendum to docs/MOMENTUM_TURNOVER_ABLATION_RESULTS.md (original quarterly run, not modified here). Real point-in-time coverage starts 2023-09-29 (core/rotation/nifty500_reconstitution.py's earliest EVENTS entry).

## Diagnostic 1 — coverage-clean sub-period

Quarterly rebalances on/after 2023-09-29 only, as a fresh ₹1,000,000 account: 13 rebalance dates.

- Total return: 30.9%
- CAGR: 10.0%
- Sharpe: 0.77
- Max drawdown: 21.6%
- Trades: 228

Compare to the original full-window quarterly result (CAGR 10.2%, Sharpe 0.81, 244 trades) — a large gap between these two numbers means the original result was meaningfully propped up by the pre-coverage static snapshot period.

## Diagnostic 2 — first-half vs second-half stability (full-window trades, pooled per-trade)

- First half:  n=122, PF=2.135, Sharpe=0.269
- Second half: n=122, PF=1.219, Sharpe=0.07
- Degradation flag (first-half Sharpe minus second-half Sharpe > 0.5): NO

## Interpretation

Neither diagnostic alone is a pass/fail verdict — see the methodology doc's framing. A clean coverage-clean result AND no degradation flag makes quarterly momentum a stronger candidate for a full, separately pre-registered strategy test. Either one failing means the original ablation's headline number was doing less work than it looked like.
