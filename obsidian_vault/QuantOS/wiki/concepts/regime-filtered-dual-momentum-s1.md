---
title: Regime-Filtered Dual-Momentum (Strategy 1)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/mixed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-regime-filtered-dual-momentum-methodology-pre-committed-2026, 2026-09-17-strategy-1-regime-filtered-dual-momentum-backtest
---

# Regime-Filtered Dual-Momentum (Strategy 1)

> [!abstract] Compiled page
> Written from `[[2026-09-17-regime-filtered-dual-momentum-methodology-pre-committed-2026]]` and `[[2026-09-17-strategy-1-regime-filtered-dual-momentum-backtest]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

One of three fully-specified strategy proposals brought in the same session; the only one of the three actually tested (a PEAD-adjacent proposal was rejected outright, [[mean-reversion-alpha50-gutcheck-s2]] was shelved as inconclusive). A Nifty 200 rotation combining a trend filter, a composite momentum score, and ATR-based stops — disclosed up front as inheriting real risk from two already-failed lineages ([[regime-classifier-s8-1]]'s regime-conditioning family, [[rs-momentum-rotation-s8-3]]'s momentum-rotation family), with different mechanics from both.

## Mechanics

- **Filter 1 (trend)**: EMA50 > EMA200 on the stock's own daily closes.
- **Filter 2 (momentum)**: `0.5 × Return_90d + 0.5 × Return_180d`, top 15 by score among Filter-1 passers, weekly rebalance, entries at next session's open.
- **Filter 3 (regime)**: NIFTY 50 > its own EMA200 — informational only, never the go/no-go basis, per this project's established convention after [[regime-classifier-s8-1]]'s 0-for-2 record.
- **Exit**: initial stop at 2.5×ATR14, Chandelier trail at 2×ATR14 (whichever is tighter governs — the Chandelier line is the operative stop almost all the time by construction of these two multipliers), asymmetric top-15-enter/top-25-hold band.
- **Cost model**: S8-3's exact `DELIVERY_COST_MODEL`, reused unchanged.

## Verdict

**Mixed — passes its own pooled-trade convention, but not held as validated once read the way this project reads a rotation strategy** `[[2026-09-17-strategy-1-regime-filtered-dual-momentum-backtest]]`:

| Cut | Trades | Pooled PF | Pooled Sharpe | Equity-curve Sharpe |
|---|---|---|---|---|
| Unfiltered (headline) | 873 | 1.24 | 0.82 | 0.70 |
| Coverage-clean (2023-09-29+) | 767 | 1.14 | 0.51 | **0.45** |

The unfiltered pooled-trade result clears `has_positive_edge` comfortably. But: it loses to Nifty Alpha 50 buy-and-hold by -53.2pt total return / -12.0pt CAGR (it does beat plain Nifty 50, by +5.5pt); the coverage-clean sub-period (removing the pre-point-in-time-data static-snapshot years) drops the equity-curve Sharpe to 0.45, just under the 0.5 bar this project's own precedent treats as the real threshold for a rotation strategy; and a first-half/second-half stability check flags real degradation (first half Sharpe 1.37, second half -0.01, a gap over the 0.5 threshold that marks a real warning).

## Relation to other concepts

Shares [[rs-momentum-rotation-s8-3]]'s survivorship-bias correction requirement (point-in-time Nifty 200 membership) and [[regime-classifier-s8-1]]'s informational-only regime-filter convention. As of this writing no wiki-citable source records a final, separately-adjudicated closing verdict beyond the numbers above — the degradation flag and the sub-0.5 coverage-clean equity-curve Sharpe are the open concerns a reader should weigh before treating the headline PASS as sufficient.
