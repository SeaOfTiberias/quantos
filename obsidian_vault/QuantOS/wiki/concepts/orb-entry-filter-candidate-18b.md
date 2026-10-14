---
title: ORB Entry Filter (Candidate 18b)
compiled: 2026-10-13
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: orb-entry-filter-candidate-18b
candidate: "18b"
family: intraday-options
instrument: index-options
status: retired
verdict: FAIL
first_tested: 2026-09-22
verdict_date: 2026-09-30
profit_factor:
sharpe:
trades: 1035
bar: "Prospective: N ≥ 20 new filtered trades per index AND ≥ 8 weeks (due 2026-11-17); superseded by the index-points test, which needed the filtered-vs-other difference to be significant"
headline: "Gating candidate 18 to NIFTY Mondays/Fridays and BankNifty big-gap days showed no significant edge in index points (p 0.46 / 0.32), so the mined filters were labelled a pricing artifact; stopped with candidate 18."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-13-candidate-18b-orb-entry-filter-methodology-pre-committed-202, 2026-10-13-candidate-18b-filters-edge-in-index-points, 2026-10-13-orb-condition-mining-results, 2026-10-13-strategy-status-snapshot-2026-10-13
---

# ORB Entry Filter (Candidate 18b)

> [!abstract] Compiled page
> Written from `[[2026-10-13-candidate-18b-orb-entry-filter-methodology-pre-committed-202]]`, `[[2026-10-13-candidate-18b-filters-edge-in-index-points]]`, `[[2026-10-13-orb-condition-mining-results]]` and `[[2026-10-13-strategy-status-snapshot-2026-10-13]]` on 2026-10-13. Context and retrieval only — rules in this layer never execute.

## Definition

Candidate 18's unchanged signal with an entry gate taken from its condition mining, one gate per index. It was named "18b" at the user's request: a distinct strategy with its own live process and verdict, but disclosed as a descendant of 18 `[[2026-10-13-candidate-18b-orb-entry-filter-methodology-pre-committed-202]]`.

## Mechanics

- **NIFTY**: trade only on Mondays and Fridays. **BankNifty**: trade only when `|gap_pct| > 0.3`. No cross-application, no re-tuning of the thresholds.
- **Why prospective**: re-backtesting the same 2021–2026 window would be circular, because the mining already saw that data. The verdict was to rest only on genuinely new paper trades: N ≥ 20 per index AND ≥ 8 weeks after the 2026-09-22 switch-on, so due 2026-11-17. Results would be compared against unfiltered 18 over the same window.
- **₹50,000 narrative** (addendum, 2026-09-22): one pooled account across both indices, reported only on 2026-11-17, descriptive only.
- **Paper-log defect** (addendum, 2026-09-30): the dry-run executor had not enforced the 25% premium stop. Four rules, fixed before any 18b numbers were viewed, govern both views: as-logged and stop-enforced.

`[[2026-10-13-candidate-18b-orb-entry-filter-methodology-pre-committed-202]]`

## Verdict

**FAIL (pricing artifact)**. A pre-registered index-points test (exit rules V0, no option pricing) found neither filter separates a real edge `[[2026-10-13-candidate-18b-filters-edge-in-index-points]]`:

| Index | Filter | Filtered n, pts/trade | Other n, pts/trade | p (one-sided) | Filtered net ₹/trade after futures costs |
|---|---|---|---|---|---|
| NIFTY | Monday/Friday | 417, +2.07 | 639, +1.55 | 0.463 | −418 |
| BankNifty | gap > 0.3% | 618, +4.73 | 605, −2.05 | 0.320 | −322 |

The live paper timers were stopped with candidate 18 on 2026-09-30, so the prospective gate due 2026-11-17 cannot collect trades `[[2026-10-13-strategy-status-snapshot-2026-10-13]]`.

## Relation to other concepts

A direct descendant of [[orb-options-scalping-candidate-18]], whose condition-mining exercise produced both filters. The filters looked real under synthetic option pricing and vanished in index points, the same pricing problem that ended candidate 18.
