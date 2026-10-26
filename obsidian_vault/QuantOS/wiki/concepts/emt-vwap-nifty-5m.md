---
title: EMT Exhaustion Mean Reversion to VWAP, NIFTY 5-minute
compiled: 2026-10-26
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: emt-vwap-nifty-5m
candidate: "EMT phase 1"
family: mean-reversion
instrument: index-options
status: closed
verdict: FAIL
first_tested: 2026-10-26
verdict_date: 2026-10-26
profit_factor: 0.77
sharpe:
trades: 921
bar: "OOS (primary vwap_ema, 2-pt cost): n >= 40, net mean > 0, PF >= 1.2"
headline: "Fading a 5-minute NIFTY or BankNifty stretch from VWAP on the first bar back fails on both indices (NIFTY loses even before costs; BankNifty's small out-of-sample gross gain is below costs), so it was never taken to options."
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-26-emt-exhaustion-mean-theory-on-nifty-5-minute-methodology, 2026-10-26-emt-on-nifty-5-minute-phase-1-results-index-points, 2026-10-26-emt-exhaustion-mean-theory-on-nifty-5-minute-methodology-2, 2026-10-26-emt-on-nifty-bank-5-minute-phase-1-results-index-points
---

# EMT Exhaustion Mean Reversion to VWAP, NIFTY 5-minute

> [!abstract] Compiled page
> Written from `[[2026-10-26-emt-exhaustion-mean-theory-on-nifty-5-minute-methodology]]`, `[[2026-10-26-emt-on-nifty-5-minute-phase-1-results-index-points]]`, the methodology's BankNifty addendum `[[2026-10-26-emt-exhaustion-mean-theory-on-nifty-5-minute-methodology-2]]` and `[[2026-10-26-emt-on-nifty-bank-5-minute-phase-1-results-index-points]]` on 2026-10-26. Context and retrieval only — rules in this layer never execute.

## Definition

The user's "exhaustion mean theory" idea for trading NIFTY ATM options intraday: when NIFTY stretches away from its mean on the 5-minute chart, the first bar that turns back toward the mean is the entry, selling after a stretch up and buying after a stretch down. The user chose the variant tested here from a short list on 2026-10-26: VWAP as the mean with an EMA9 confirmation, the stretch as a multiple of ATR, exit at the mean with a stop beyond the stretch extreme, and index points first, options only if that passed.

## Mechanics

- **Mean:** session VWAP of (O+H+L+C)/4, weighted by the continuous NIFTY future's volume, reset at 09:15.
- **Stretch:** close at least k × ATR(14) from VWAP and beyond EMA9 on the same side; k swept over 0.5, 1, 1.5 and 2.
- **Signal:** the first later bar that closes back toward the mean while still on the stretched side. Entry at the next open, 09:30 to 14:30.
- **Exit:** target at a touch of the mean, stop beyond the stretch extreme (the stop counts if both fall in one bar), flat at 15:15.
- **Test:** about one year of Fyers 5-minute bars (247 sessions, 2025-10-27 to 2026-10-26). k chosen on the first half, judged on the second, with a 2-point round-trip cost as the proxy for ATM option spread plus charges.

## Verdict

**FAIL** `[[2026-10-26-emt-on-nifty-5-minute-phase-1-results-index-points]]`. Out-of-sample, the primary variant at the IS-chosen k = 0.5 took 921 trades, 37% winners, −0.59 points per trade gross and −2.59 net, PF 0.77, t = −3.1.

| OOS, 2-pt cost | n | win | gross pts | net pts | PF |
|---|---|---|---|---|---|
| vwap_ema k=0.5 (chosen) | 921 | 37% | −0.59 | −2.59 | 0.77 |
| vwap_ema k=1 | 783 | 37% | −0.11 | −2.11 | 0.83 |
| vwap_ema k=1.5 | 588 | 32% | −0.24 | −2.24 | 0.83 |
| vwap_ema k=2 | 426 | 27% | −1.17 | −3.17 | 0.78 |
| vwap only, k=0.5 | 965 | 38% | −0.71 | −2.71 | 0.76 |
| ema (mean = EMA9), k=0.5 | 1065 | 49% | −1.08 | −3.08 | 0.59 |

Every cell of the grid is negative before costs, in-sample and out-of-sample, for all three ways of defining the mean. The edge is not hidden by costs: there is none to cost. About 60% of trades hit the stop (average risk about 19 points) before reaching the mean. The OOS shorts alone were +1.9 points gross (−0.06 net, t ≈ 0). That's a post-hoc slice, not a finding.

Phase 2 (ATM options) was not run, as the methodology required.

### BankNifty (same day, same rules)

The user asked for the same test on BankNifty after NIFTY failed. The rules were unchanged and the costs were scaled to the index level (5 points per round trip, sensitivity 2.5 and 10), fixed in an addendum before the run `[[2026-10-26-emt-exhaustion-mean-theory-on-nifty-5-minute-methodology-2]]`. **FAIL** `[[2026-10-26-emt-on-nifty-bank-5-minute-phase-1-results-index-points]]`. OOS, primary variant, IS-chosen k = 0.5: 921 trades, 41% winners, +1.20 points gross, −3.80 net, PF 0.88, t = −1.5.

| BankNifty OOS, 5-pt cost | n | win | gross pts | net pts | PF |
|---|---|---|---|---|---|
| vwap_ema k=0.5 (chosen) | 921 | 41% | +1.20 | −3.80 | 0.88 |
| vwap_ema k=1 | 748 | 40% | +2.94 | −2.06 | 0.94 |
| vwap_ema k=1.5 | 547 | 35% | +3.39 | −1.61 | 0.96 |
| vwap_ema k=2 | 399 | 29% | −1.77 | −6.77 | 0.85 |

In-sample, every k lost 4.7 to 10.4 points per trade before costs. The out-of-sample half is slightly positive before costs but never clears them, even at the 2.5-point cost (PF 0.96). On both indices the shorts did better than the longs out-of-sample (BankNifty shorts +6.9 points gross, PF 1.06, t ≈ 0.5). That's consistent across both indices but still a post-hoc slice from one six-month window, so it isn't a tested result.

## Relation to other concepts

Another 5-minute NIFTY intraday rule that fails before option pricing even enters, like [[nifty-ema-options-s8-4]]. The trend-following side of the same chart did no better there. Compare [[orb-options-scalping-candidate-18]] for the intraday index-options work that did get as far as option re-pricing.
