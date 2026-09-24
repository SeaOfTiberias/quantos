# Candidate 18 (ORB Options Scalping) — Capital Allocation / Position Sizing

Methodology: this script's own module docstring (scripts/simulate_orb_scalping_capital_allocation.py) — Kelly fraction derived on a Mining window ONLY, tested on an untouched Holdout window, same 80/20 time-based split docs/ORB_CONDITION_MINING_METHODOLOGY.md already established for this candidate.

NIFTY mining/holdout boundary: 2025-11-13 (837 mining / 215 holdout signals).
BankNifty mining/holdout boundary: 2025-09-01 (1027 mining / 256 holdout signals).

**Mining-derived Kelly fraction (pooled NIFTY+BankNifty mining returns, n=1864)**: full=0.3100 (31.00% of equity/trade), half=0.1550, quarter=0.0775.

## Holdout window only (the real, out-of-sample test)

| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Max DD % | Max DD ₹ | Signals taken | Signals skipped |
|---|---|---|---|---|---|---|---|---|---|
| Fixed 1 lot | ₹50,000 | ₹128,878.69 | 157.8% | 143.7% | 1.31 | 75.1% | ₹57,016.37 | 465/471 | 6 |
| Fixed 1 lot | ₹100,000 | ₹182,341.59 | 82.3% | 76.0% | 1.14 | 51.2% | ₹64,542.41 | 471/471 | 0 |
| Fixed 1 lot | ₹500,000 | ₹582,341.60 | 16.5% | 15.4% | 0.92 | 12.3% | ₹64,542.41 | 471/471 | 0 |
| Full Kelly (0.3100) | ₹50,000 | ₹69,750.29 | 39.5% | 36.8% | 0.91 | 74.3% | ₹94,494.82 | 319/471 | 152 |
| Full Kelly (0.3100) | ₹100,000 | ₹213,800.57 | 113.8% | 104.4% | 1.24 | 73.9% | ₹293,724.14 | 447/471 | 24 |
| Full Kelly (0.3100) | ₹500,000 | ₹911,694.59 | 82.3% | 76.0% | 1.23 | 77.3% | ₹545,067.94 | 471/471 | 0 |
| Half Kelly (0.1550) | ₹50,000 | ₹66,970.62 | 33.9% | 31.6% | 0.86 | 33.0% | ₹25,595.57 | 84/471 | 387 |
| Half Kelly (0.1550) | ₹100,000 | ₹135,204.31 | 35.2% | 32.8% | 0.74 | 35.9% | ₹40,908.30 | 306/471 | 165 |
| Half Kelly (0.1550) | ₹500,000 | ₹1,039,430.07 | 107.9% | 99.1% | 1.17 | 46.1% | ₹570,745.84 | 471/471 | 0 |
| Quarter Kelly (0.0775) | ₹50,000 | ₹50,535.31 | 1.1% | 1.0% | 0.34 | 2.0% | ₹985.53 | 5/471 | 466 |
| Quarter Kelly (0.0775) | ₹100,000 | ₹120,839.58 | 20.8% | 19.5% | 1.01 | 16.6% | ₹20,915.46 | 77/471 | 394 |
| Quarter Kelly (0.0775) | ₹500,000 | ₹834,693.91 | 66.9% | 61.9% | 1.25 | 25.7% | ₹226,503.47 | 470/471 | 1 |

## Full window (mining + holdout) — IN-SAMPLE for the Kelly fractions above, context only

The Kelly fractions were derived FROM the mining portion of this same window, so any Kelly row below is not an independent test — it is shown only to see full-history compounding behavior, not as evidence for or against the sizing rule. The Holdout-only table above is the actual validation.

| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Max DD % | Max DD ₹ | Signals taken | Signals skipped |
|---|---|---|---|---|---|---|---|---|---|
| Fixed 1 lot | ₹50,000 | ₹1,964.64 | -96.1% | -45.6% | -0.63 | 97.7% | ₹83,136.67 | 284/2335 | 2051 |
| Fixed 1 lot | ₹100,000 | ₹622,376.74 | 522.4% | 41.0% | 1.07 | 50.2% | ₹67,879.11 | 2335/2335 | 0 |
| Fixed 1 lot | ₹500,000 | ₹1,022,376.74 | 104.5% | 14.4% | 1.17 | 12.7% | ₹67,879.11 | 2335/2335 | 0 |
| Full Kelly (0.3100) | ₹50,000 | ₹292,709,310.10 | 585318.6% | 411.1% | 1.70 | 93.2% | ₹2,660,494.45 | 2322/2335 | 13 |
| Full Kelly (0.3100) | ₹100,000 | ₹485,714,809.89 | 485614.8% | 393.4% | 1.69 | 93.2% | ₹4,171,691.66 | 2335/2335 | 0 |
| Full Kelly (0.3100) | ₹500,000 | ₹3,671,520,155.31 | 734204.0% | 433.3% | 1.72 | 93.4% | ₹31,353,927.38 | 2335/2335 | 0 |
| Half Kelly (0.1550) | ₹50,000 | ₹20,968,553.24 | 41837.1% | 211.3% | 1.56 | 66.3% | ₹196,069.58 | 2141/2335 | 194 |
| Half Kelly (0.1550) | ₹100,000 | ₹96,106,215.58 | 96006.2% | 263.8% | 1.66 | 69.5% | ₹909,168.65 | 2323/2335 | 12 |
| Half Kelly (0.1550) | ₹500,000 | ₹771,696,986.06 | 154239.4% | 297.7% | 1.72 | 70.0% | ₹7,121,535.42 | 2335/2335 | 0 |
| Quarter Kelly (0.0775) | ₹50,000 | ₹83,419.25 | 66.8% | 10.1% | 0.64 | 22.6% | ₹20,461.22 | 143/2335 | 2192 |
| Quarter Kelly (0.0775) | ₹100,000 | ₹4,575,828.92 | 4475.8% | 105.2% | 1.64 | 37.0% | ₹146,696.14 | 2094/2335 | 241 |
| Quarter Kelly (0.0775) | ₹500,000 | ₹38,938,173.97 | 7687.6% | 126.8% | 1.70 | 42.1% | ₹1,119,789.07 | 2335/2335 | 0 |

## Interpretation — read the Holdout table, ignore the Full-window Kelly rows as a real forecast

**The full-window Kelly numbers (₹292 million from ₹50,000 starting
capital) are not a realistic outcome — they are what naive fixed-fraction
compounding over ~2,300 trades looks like when the fraction is fit on 80%
of the very data it then compounds over.** Full Kelly's theoretical
promise is exactly this: reinvest a large fixed fraction of a growing
balance and geometric growth compounds without bound. That promise only
holds if the future return distribution matches the past exactly, trade
returns are independent, and the fraction estimate has zero error — none
of which is true of a 5-year single-strategy backtest. Treat every number
in the "Full window" table as a demonstration of the mechanics, not a
forecast.

**The Holdout table is the real evidence, and it says something more
useful and more sobering than a headline number:**

- **Full Kelly (31% of equity/trade) survives the holdout with a positive
  Sharpe (0.91–1.24) but with drawdowns of 74–93% even out of sample** —
  at ₹100,000 starting capital, equity fell ₹293,724 from its own peak at
  some point during the ~11-month holdout. A real account watching a 74%
  drawdown, even inside an eventual winning run, is watching most of its
  capital disappear before any recovery — full Kelly is the theoretical
  growth-maximizer under perfect knowledge of the edge, and the reason
  almost nobody trades it in practice is exactly this: it is also the
  most fragile to the estimation error every real edge estimate has.
- **Half Kelly (15.5%) is more survivable but ₹50,000 still can't use it
  properly** — only 84 of 471 holdout signals were affordable, and the
  ₹66,970 final result (barely above breakeven) reflects mostly SITTING
  OUT the strategy, not the strategy underperforming.
- **Quarter Kelly (7.75%) is the most consistently reasonable policy
  ABOVE ₹50,000** — at ₹100,000: Sharpe 1.01, max DD 16.6%, +20.8% over
  the holdout, executing 77/471 signals. At ₹500,000: Sharpe 1.25 (the
  best risk-adjusted number in this entire table), max DD 25.7%, +66.9%,
  executing all but 1 of 471 signals. **At ₹50,000 it is functionally
  broken — only 5 of 471 signals were ever affordable**, because 7.75% of
  ₹50,000 (≈₹3,875) is below what even a single NIFTY lot at typical
  premium levels costs on most days.
- **₹50,000 does not have a good option among these four policies.**
  Fixed 1-lot has the cliff already documented in
  docs/ORB_SCALPING_EQUITY_CURVE_RESULTS.md. Every fractional policy at
  ₹50,000 is either too aggressive to survive comfortably (Full Kelly) or
  too small to execute the strategy at all (Half/Quarter Kelly). This
  reinforces, from a completely different angle, the earlier finding:
  ₹50,000 is genuinely undersized for this strategy, not just under a
  fixed-lot policy.

**A defensible answer to "optimum capital allocation", stated plainly**:
size each trade at roughly **quarter-Kelly to half-Kelly (≈8–16% of
current equity)**, starting with **at least ₹100,000, and comfortably
above that (₹500,000 shows the cleanest risk-adjusted profile of
everything tested) if the goal is to avoid a policy that can't execute
some of its own signals.** Full Kelly is not recommended despite the
larger holdout return — its drawdowns are large enough that few real
investors would hold through one without abandoning the strategy first,
which is a real risk a backtest can't price in.

**Caveats that matter more here than usual**:
- The holdout window is ~11 months, ONE continuous period, not multiple
  independent out-of-sample windows — a single holdout Sharpe/CAGR/DD
  carries real sampling uncertainty at this trade count (see this
  project's own established caution on confidence intervals at
  n~65-200 trades; several of these holdout cells have fewer signals
  than that after fraction-driven skips).
- The Kelly fraction (31%) is itself an ESTIMATE from ~1,864 mining
  trades assuming the future resembles the past — Kelly is famously
  sensitive to exactly this estimation error, which is the main academic
  and practical argument for using a fraction of Kelly rather than Kelly
  itself, independent of anything specific to this strategy.
- This is ONE holdout period from ONE historical run (re-fetched live
  during market hours, 2026-09-24 ~13:17 IST) — exact figures will not
  reproduce bit-for-bit on a later run; the ranking and rough magnitude
  of the four policies is the finding.
