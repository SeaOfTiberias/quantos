# Darvas ATR-Stop (Bucket B) — Real Capital-Tracked Equity Curve & Position Sizing

Methodology: this script's own module docstring (scripts/simulate_darvas_atr_stop_equity_curve.py). Bucket B (35% < box width <= 50%) trades only -- the only bucket that cleared this candidate's pre-registered bar (docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md). No new backtest run, no Fyers data fetched -- pure post-processing of the already-committed cache (C:\Users\Admin\.quantos\darvas_atr_stop_results.json).

Mining/Holdout boundary: 2026-02-15 (210 mining / 67 holdout trades, 277 total).
Mining-derived Kelly fraction (n=210): full=0.4590 (45.90% of equity/trade), half=0.2295, quarter=0.1148.

## Full-window results by starting capital and sizing policy

| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Sortino | Calmar | Ulcer Index | Max DD % | Max DD ₹ | Max DD duration | Trades taken | Trades skipped (insufficient cash) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fixed Rs100k/trade | ₹25,000 | ₹16,779.10 | -32.9% | -3.3% | -0.16 | -0.25 | -0.07 | 16.44 | 50.2% | ₹13,936.17 | 841d | 70/277 | 207 |
| Fixed Rs100k/trade | ₹50,000 | ₹35,465.80 | -29.1% | -2.9% | -0.12 | -0.19 | -0.06 | 15.45 | 47.3% | ₹26,237.26 | 841d | 71/277 | 206 |
| Fixed Rs100k/trade | ₹75,000 | ₹54,687.54 | -27.1% | -2.7% | -0.08 | -0.13 | -0.06 | 14.61 | 45.5% | ₹38,660.31 | 673d | 63/277 | 214 |
| Fixed Rs100k/trade | ₹100,000 | ₹74,096.34 | -25.9% | -2.5% | -0.09 | -0.14 | -0.06 | 14.73 | 45.6% | ₹52,434.81 | 621d | 75/277 | 202 |
| Fixed Rs100k/trade | ₹250,000 | ₹265,711.75 | 6.3% | 0.5% | 0.10 | 0.18 | 0.01 | 10.84 | 37.6% | ₹115,882.50 | 621d | 115/277 | 162 |
| Fixed Rs100k/trade | ₹500,000 | ₹552,362.11 | 10.5% | 0.8% | 0.14 | 0.25 | 0.03 | 5.76 | 27.5% | ₹152,379.44 | 673d | 158/277 | 119 |
| Full Kelly (0.4590) | ₹25,000 | ₹20,836.15 | -16.7% | -1.5% | -0.07 | -0.10 | -0.04 | 12.54 | 41.0% | ₹11,406.78 | 621d | 114/277 | 163 |
| Full Kelly (0.4590) | ₹50,000 | ₹47,340.95 | -5.3% | -0.5% | 0.02 | 0.04 | -0.01 | 11.66 | 38.7% | ₹22,974.92 | 621d | 112/277 | 165 |
| Full Kelly (0.4590) | ₹75,000 | ₹75,559.65 | 0.8% | 0.1% | 0.07 | 0.11 | 0.00 | 10.69 | 37.3% | ₹32,916.33 | 621d | 115/277 | 162 |
| Full Kelly (0.4590) | ₹100,000 | ₹105,719.39 | 5.7% | 0.5% | 0.10 | 0.17 | 0.01 | 10.52 | 37.1% | ₹45,694.87 | 621d | 116/277 | 161 |
| Full Kelly (0.4590) | ₹250,000 | ₹271,309.02 | 8.5% | 0.7% | 0.12 | 0.20 | 0.02 | 10.30 | 36.3% | ₹112,165.21 | 621d | 119/277 | 158 |
| Full Kelly (0.4590) | ₹500,000 | ₹546,991.26 | 9.4% | 0.8% | 0.12 | 0.21 | 0.02 | 10.32 | 36.4% | ₹226,451.50 | 621d | 116/277 | 161 |
| Half Kelly (0.2295) | ₹25,000 | ₹25,227.84 | 0.9% | 0.1% | 0.05 | 0.08 | 0.00 | 5.92 | 27.6% | ₹7,655.02 | 792d | 140/277 | 137 |
| Half Kelly (0.2295) | ₹50,000 | ₹48,860.28 | -2.3% | -0.2% | 0.02 | 0.04 | -0.01 | 6.07 | 27.3% | ₹14,698.54 | 792d | 146/277 | 131 |
| Half Kelly (0.2295) | ₹75,000 | ₹78,381.05 | 4.5% | 0.4% | 0.09 | 0.15 | 0.01 | 5.88 | 27.6% | ₹22,836.12 | 622d | 144/277 | 133 |
| Half Kelly (0.2295) | ₹100,000 | ₹101,171.17 | 1.2% | 0.1% | 0.06 | 0.10 | 0.00 | 6.25 | 28.3% | ₹31,055.48 | 622d | 146/277 | 131 |
| Half Kelly (0.2295) | ₹250,000 | ₹269,797.85 | 7.9% | 0.7% | 0.12 | 0.20 | 0.02 | 5.89 | 27.5% | ₹75,931.30 | 597d | 154/277 | 123 |
| Half Kelly (0.2295) | ₹500,000 | ₹540,172.77 | 8.0% | 0.7% | 0.12 | 0.20 | 0.02 | 5.87 | 27.5% | ₹152,258.99 | 597d | 156/277 | 121 |
| Quarter Kelly (0.1148) | ₹25,000 | ₹27,574.05 | 10.3% | 0.8% | 0.17 | 0.30 | 0.06 | 3.07 | 14.2% | ₹4,024.87 | 336d | 187/277 | 90 |
| Quarter Kelly (0.1148) | ₹50,000 | ₹57,281.04 | 14.6% | 1.2% | 0.22 | 0.40 | 0.07 | 3.13 | 15.8% | ₹9,307.92 | 337d | 198/277 | 79 |
| Quarter Kelly (0.1148) | ₹75,000 | ₹85,623.35 | 14.2% | 1.1% | 0.22 | 0.39 | 0.07 | 3.22 | 16.3% | ₹14,378.86 | 337d | 201/277 | 76 |
| Quarter Kelly (0.1148) | ₹100,000 | ₹119,859.52 | 19.9% | 1.6% | 0.28 | 0.51 | 0.09 | 3.12 | 16.7% | ₹19,806.74 | 337d | 197/277 | 80 |
| Quarter Kelly (0.1148) | ₹250,000 | ₹290,962.45 | 16.4% | 1.3% | 0.24 | 0.42 | 0.07 | 3.77 | 19.4% | ₹57,556.24 | 658d | 200/277 | 77 |
| Quarter Kelly (0.1148) | ₹500,000 | ₹580,539.42 | 16.1% | 1.3% | 0.23 | 0.41 | 0.07 | 3.78 | 19.7% | ₹116,687.89 | 658d | 198/277 | 79 |

## Holdout-only results (the real out-of-sample test for the Kelly fractions)

The Kelly fractions were derived from the Mining trades only; this table applies them to the untouched Holdout trades, same discipline as candidate 18's own capital-allocation analysis.

| Sizing policy | Starting capital | Final equity | Total return % | CAGR % | Sharpe | Sortino | Calmar | Ulcer Index | Max DD % | Max DD ₹ | Max DD duration | Trades taken | Trades skipped (insufficient cash) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fixed Rs100k/trade | ₹25,000 | ₹30,560.68 | 22.2% | 55.9% | 1.38 | 3.48 | 5.17 | 7.16 | 10.8% | ₹3,264.36 | 80d | 19/67 | 48 |
| Fixed Rs100k/trade | ₹50,000 | ₹59,026.22 | 18.1% | 44.4% | 1.06 | 2.52 | 4.04 | 7.67 | 11.0% | ₹6,713.81 | 96d | 19/67 | 48 |
| Fixed Rs100k/trade | ₹75,000 | ₹87,692.81 | 16.9% | 41.3% | 0.95 | 2.25 | 3.22 | 7.48 | 12.8% | ₹12,898.95 | 96d | 20/67 | 47 |
| Fixed Rs100k/trade | ₹100,000 | ₹119,979.68 | 20.0% | 49.6% | 1.15 | 2.93 | 4.88 | 6.66 | 10.2% | ₹12,437.76 | 96d | 21/67 | 46 |
| Fixed Rs100k/trade | ₹250,000 | ₹318,121.12 | 27.2% | 70.4% | 2.45 | 7.30 | 12.53 | 1.81 | 5.6% | ₹15,996.32 | 43d | 29/67 | 38 |
| Fixed Rs100k/trade | ₹500,000 | ₹561,010.01 | 12.2% | 29.0% | 1.54 | 3.17 | 3.97 | 3.58 | 7.3% | ₹39,384.61 | 105d | 41/67 | 26 |
| Full Kelly (0.4590) | ₹25,000 | ₹31,411.41 | 25.6% | 65.7% | 2.35 | 6.86 | 10.60 | 1.57 | 6.2% | ₹1,738.89 | 52d | 24/67 | 43 |
| Full Kelly (0.4590) | ₹50,000 | ₹63,723.66 | 27.4% | 71.0% | 2.48 | 7.88 | 12.17 | 1.51 | 5.8% | ₹3,279.08 | 52d | 26/67 | 41 |
| Full Kelly (0.4590) | ₹75,000 | ₹96,211.04 | 28.3% | 73.5% | 2.43 | 7.54 | 12.40 | 1.50 | 5.9% | ₹4,995.50 | 53d | 25/67 | 42 |
| Full Kelly (0.4590) | ₹100,000 | ₹128,834.51 | 28.8% | 75.2% | 2.33 | 6.61 | 12.55 | 1.65 | 6.0% | ₹6,725.18 | 33d | 29/67 | 38 |
| Full Kelly (0.4590) | ₹250,000 | ₹323,762.98 | 29.5% | 77.2% | 2.44 | 7.37 | 13.12 | 1.51 | 5.9% | ₹16,525.59 | 51d | 26/67 | 41 |
| Full Kelly (0.4590) | ₹500,000 | ₹649,479.31 | 29.9% | 78.4% | 2.37 | 6.93 | 13.52 | 1.55 | 5.8% | ₹32,548.30 | 33d | 29/67 | 38 |
| Half Kelly (0.2295) | ₹25,000 | ₹25,676.88 | 2.7% | 6.1% | 0.42 | 0.76 | 0.68 | 5.32 | 8.9% | ₹2,374.34 | 109d | 32/67 | 35 |
| Half Kelly (0.2295) | ₹50,000 | ₹53,779.53 | 7.6% | 17.5% | 0.92 | 1.74 | 1.97 | 5.30 | 8.9% | ₹4,858.29 | 130d | 36/67 | 31 |
| Half Kelly (0.2295) | ₹75,000 | ₹80,870.54 | 7.8% | 18.1% | 0.94 | 1.79 | 1.96 | 5.51 | 9.2% | ₹7,601.73 | 130d | 35/67 | 32 |
| Half Kelly (0.2295) | ₹100,000 | ₹106,678.11 | 6.7% | 15.4% | 0.83 | 1.55 | 1.78 | 5.28 | 8.7% | ₹9,443.80 | 109d | 36/67 | 31 |
| Half Kelly (0.2295) | ₹250,000 | ₹278,559.61 | 11.4% | 27.0% | 1.30 | 2.57 | 3.12 | 4.31 | 8.7% | ₹23,779.69 | 105d | 37/67 | 30 |
| Half Kelly (0.2295) | ₹500,000 | ₹559,137.39 | 11.8% | 28.1% | 1.34 | 2.65 | 3.24 | 4.25 | 8.7% | ₹47,540.26 | 105d | 36/67 | 31 |
| Quarter Kelly (0.1148) | ₹25,000 | ₹24,407.91 | -2.4% | -5.2% | -0.50 | -0.73 | -0.59 | 5.05 | 8.7% | ₹2,236.30 | 134d | 44/67 | 23 |
| Quarter Kelly (0.1148) | ₹50,000 | ₹50,585.56 | 1.2% | 2.6% | 0.30 | 0.49 | 0.38 | 3.78 | 7.0% | ₹3,591.68 | 130d | 44/67 | 23 |
| Quarter Kelly (0.1148) | ₹75,000 | ₹77,687.56 | 3.6% | 8.1% | 0.73 | 1.26 | 1.18 | 3.87 | 6.8% | ₹5,332.13 | 130d | 44/67 | 23 |
| Quarter Kelly (0.1148) | ₹100,000 | ₹104,021.62 | 4.0% | 9.1% | 0.81 | 1.40 | 1.46 | 3.80 | 6.2% | ₹6,512.40 | 130d | 45/67 | 22 |
| Quarter Kelly (0.1148) | ₹250,000 | ₹258,884.21 | 3.5% | 8.0% | 0.74 | 1.25 | 1.28 | 3.82 | 6.3% | ₹16,315.42 | 130d | 46/67 | 21 |
| Quarter Kelly (0.1148) | ₹500,000 | ₹518,061.95 | 3.6% | 8.2% | 0.75 | 1.28 | 1.34 | 3.62 | 6.1% | ₹31,885.44 | 109d | 46/67 | 21 |

## Capital floor threshold (Fixed Rs100k/trade policy)

Smallest tested starting capital with ZERO trades skipped for insufficient cash: **none of the tested tiers cleared it**. This is an empirical reading against the tested capital tiers only, not a theoretical minimum -- see the full table above for every tier's actual skip count.

## Interpretation

**This is a genuinely different failure mode than candidate 18's, not a repeat of it.** There is no near-total-wipeout cliff anywhere in this table — the worst observed max drawdown across every policy and capital tier is ~50% (Fixed Rs100k/trade at ₹25,000), nowhere close to ORB scalping's 97.7% wipeout. Equities size down smoothly to whatever cash remains (confirmed in this script's own unit tests); there's no hard "1 lot or nothing" cliff the way options-lot granularity creates one.

**What's wrong instead is capacity, not survival.** The Fixed Rs100k/trade policy — this candidate's own backtest convention — **loses money on the full window at every capital tier from ₹25,000 to ₹100,000** (CAGR -2.5% to -3.3%, Sharpe -0.08 to -0.16), and even at ₹500,000 still skips 119 of 277 signals (43%) for insufficient cash. This isn't "too poor to survive" — it's "too many concurrent overlapping breakout signals compete for a fixed ₹100,000 target each," a real structural mismatch between the backtest's own sizing convention and how many positions this strategy actually wants open at once. **No tested capital tier — up to ₹500,000 — ever fully funds the fixed-notional policy.**

**Quarter Kelly (11.48% of equity/trade) is the standout on the full window**, same conclusion as candidate 18's own analysis: best Sharpe (0.17–0.28), best Calmar (0.06–0.09), lowest Ulcer Index (3.1–3.8 vs. 10–16 for the other policies), and lowest max drawdown (14–20% vs. 27–50%) — positive at every capital tier tested, unlike fixed-notional or full/half Kelly.

**Read the Holdout-only table with real suspicion, not confidence.** Full Kelly's holdout numbers (Sharpe 2.3–2.5, CAGR 65–78%, Calmar 10–13.5) look spectacular, but the holdout window is only 67 signals total, and as few as 19–46 of those actually executed once sizing/cash constraints are applied — a sample this small producing numbers this good is the classic shape of a lucky regime, not a validated result (this project's own established caution on small-n confidence intervals applies directly here). Full-window numbers, built on 4x the trade count, are the more trustworthy read, and they tell a much more modest story (Full Kelly there is only marginally positive, Sharpe 0.02–0.14).

**A real methodological gap this run exposed, not papered over**: the Kelly fraction here (45.9% full, from `core/backtest/equity_curve.py::kelly_fraction`) was derived assuming ONE trade at a time, the same as candidate 18's own Kelly analysis — but unlike ORB scalping's essentially-sequential one-trade-per-day-per-index pattern, Darvas routinely holds MANY overlapping positions in different symbols simultaneously. Applying a single-trade-optimal fraction independently to every new signal without accounting for how many other positions are already open understates true concurrent risk (several 46%-sized positions open at once is a very different risk profile than one). This wasn't corrected here — a proper portfolio-level Kelly formulation (accounting for the typical number of concurrent open positions) is a real follow-up, not yet built, and the fractions above should be read as a single-trade-optimal reference point, not a portfolio-safe one.

**Practical reading**: if this candidate is ever deployed, quarter-Kelly-style sizing (~10-12% of equity per trade) with at least ₹100,000-250,000 capital is the best-evidenced choice from this run — not because it avoids a cliff (there isn't one), but because it's the only policy that's consistently profitable, on the larger and more trustworthy full-window sample, at every capital level tested.
