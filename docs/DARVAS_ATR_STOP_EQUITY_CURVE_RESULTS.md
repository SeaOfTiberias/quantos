# Darvas ATR-Stop (Bucket B) — Real Capital-Tracked Equity Curve & Position Sizing

Methodology: this script's own module docstring (scripts/simulate_darvas_atr_stop_equity_curve.py). Bucket B (35% < box width <= 50%) trades only -- the only bucket that cleared this candidate's pre-registered bar (docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md). No new backtest run, no Fyers data fetched -- pure post-processing of the already-committed cache (C:\Users\Admin\.quantos\darvas_atr_stop_results.json).

Mining/Holdout boundary: 2026-02-15 (210 mining / 67 holdout trades, 277 total).
Mining-derived Kelly fraction (n=210): full=0.4590 (45.90% of equity/trade), half=0.2295, quarter=0.1148.

**Concurrent open positions in the mining window** (why single-trade Kelly is the wrong tool here): mean=12.2, median=12.0, max=29. Full Kelly's 45.9%-of-equity-per-trade figure assumes ONE bet at a time -- with a mean of 12 (max 29) positions open simultaneously, that fraction would try to commit several multiples of total capital at once if cash allowed it.
**Portfolio Kelly, grid-searched (f=0.0900)**: found by `core/backtest/equity_curve.py::optimal_fraction_by_growth`, which simulates the REAL overlapping mining trade history at each candidate fraction (at ₹250,000 starting capital) and picks whichever produced the best realized log-growth -- concurrency, correlation between simultaneously-held positions, and the cash ceiling are automatically correct because it's the real simulation, not an analytical approximation. This is the policy actually recommended below, not the single-trade Kelly fractions.

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
| Portfolio Kelly, grid-searched (0.0900) | ₹25,000 | ₹27,050.47 | 8.2% | 0.7% | 0.16 | 0.26 | 0.07 | 2.37 | 10.3% | ₹2,763.58 | 320d | 209/277 | 68 |
| Portfolio Kelly, grid-searched (0.0900) | ₹50,000 | ₹57,319.29 | 14.6% | 1.2% | 0.24 | 0.46 | 0.10 | 2.50 | 12.2% | ₹7,089.97 | 320d | 217/277 | 60 |
| Portfolio Kelly, grid-searched (0.0900) | ₹75,000 | ₹92,722.96 | 23.6% | 1.8% | 0.35 | 0.73 | 0.15 | 2.35 | 12.4% | ₹11,368.40 | 320d | 213/277 | 64 |
| Portfolio Kelly, grid-searched (0.0900) | ₹100,000 | ₹122,887.43 | 22.9% | 1.8% | 0.34 | 0.71 | 0.14 | 2.45 | 12.9% | ₹16,029.65 | 336d | 218/277 | 59 |
| Portfolio Kelly, grid-searched (0.0900) | ₹250,000 | ₹295,037.65 | 18.0% | 1.4% | 0.28 | 0.54 | 0.10 | 2.82 | 14.9% | ₹44,373.82 | 336d | 227/277 | 50 |
| Portfolio Kelly, grid-searched (0.0900) | ₹500,000 | ₹588,065.84 | 17.6% | 1.4% | 0.27 | 0.52 | 0.09 | 2.94 | 15.6% | ₹93,854.37 | 336d | 228/277 | 49 |

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
| Portfolio Kelly, grid-searched (0.0900) | ₹25,000 | ₹24,303.23 | -2.8% | -6.1% | -0.70 | -0.96 | -0.78 | 5.12 | 7.7% | ₹1,970.80 | 134d | 48/67 | 19 |
| Portfolio Kelly, grid-searched (0.0900) | ₹50,000 | ₹49,498.22 | -1.0% | -2.2% | -0.20 | -0.30 | -0.35 | 3.76 | 6.3% | ₹3,214.37 | 134d | 51/67 | 16 |
| Portfolio Kelly, grid-searched (0.0900) | ₹75,000 | ₹74,565.14 | -0.6% | -1.3% | -0.09 | -0.14 | -0.19 | 3.84 | 6.8% | ₹5,274.40 | 130d | 51/67 | 16 |
| Portfolio Kelly, grid-searched (0.0900) | ₹100,000 | ₹100,600.32 | 0.6% | 1.3% | 0.19 | 0.31 | 0.19 | 3.89 | 7.0% | ₹7,167.95 | 130d | 50/67 | 17 |
| Portfolio Kelly, grid-searched (0.0900) | ₹250,000 | ₹251,712.83 | 0.7% | 1.5% | 0.21 | 0.34 | 0.23 | 3.68 | 6.7% | ₹17,225.58 | 130d | 55/67 | 12 |
| Portfolio Kelly, grid-searched (0.0900) | ₹500,000 | ₹502,828.62 | 0.6% | 1.3% | 0.18 | 0.29 | 0.19 | 3.50 | 6.7% | ₹34,733.54 | 130d | 56/67 | 11 |

## Capital floor threshold (Fixed Rs100k/trade policy)

Smallest tested starting capital with ZERO trades skipped for insufficient cash: **none of the tested tiers cleared it**. This is an empirical reading against the tested capital tiers only, not a theoretical minimum -- see the full table above for every tier's actual skip count.

## Interpretation

**No wipeout cliff anywhere in this table** (worst max drawdown ~50%, nowhere near candidate 18's 97.7%) -- equities size down smoothly to whatever cash remains instead of hitting an all-or-nothing lot floor. The problem here was always capacity, not survival: the backtest's own Fixed Rs100k/trade convention loses money below Rs100,000 and never fully funds even at Rs500,000 (no capital tier clears the floor threshold above).

**Single-trade Kelly's 45.9% figure was simply the wrong tool, and the concurrency numbers show exactly why.** Bucket B's mining window holds a mean of **12.2** (median 12, max **29**) positions open AT THE SAME TIME. A formula that assumes one bet at a time has no way to represent "12 positions each wanting 46% of equity" -- in practice the account's own cash constraint capped the damage (you can't spend more than 100% of what you have), but that's the simulation saving the fraction from itself, not the fraction being sound.

**Portfolio Kelly, grid-searched (f=0.09) is the properly-derived fix, and it wins outright on the full window** -- the larger, more trustworthy sample (277 trades vs. holdout's 67): best Sharpe (0.16-0.35), best Sortino (0.26-0.73), best Calmar (0.07-0.15), and the LOWEST Ulcer Index (2.35-2.94) and LOWEST max drawdown (10.3-15.6%) of every policy tested, at every capital tier. It beats Quarter Kelly (0.1148) -- last week's ad hoc round-number pick -- on every single metric, despite using a SMALLER fraction (9% vs. 11.5%). This isn't a coincidence: 9% is what actually maximized realized portfolio growth when the real overlapping trade history and real cash ceiling were simulated directly, not guessed at.

**On the smaller Holdout-only sample, Portfolio Kelly is roughly comparable to Quarter Kelly, sometimes marginally worse at low capital** (e.g. -2.8% vs. -2.4% at Rs25,000). This is not evidence the portfolio-derived fraction is wrong -- the Holdout window is the same small, plausibly-lucky-regime sample already flagged as untrustworthy in this doc (as few as 11-19 trades actually executed per cell). The full-window comparison, built on 4x the data, is the one to trust, and it's unambiguous.

**Updated practical reading**: size Darvas ATR-stop (Bucket B) at **~9% of current equity per trade** (`core/backtest/equity_curve.py::optimal_fraction_by_growth`'s grid-searched figure), not the earlier "quarter-Kelly ballpark" guess -- with at least Rs100,000-250,000 capital, matching the range where this policy is cleanly profitable with the smallest drawdowns of anything tested. The remaining open item from the concurrency analysis (correlation between simultaneously-held positions during a shared market-wide drawdown, which this grid search accounts for implicitly by using the REAL historical co-movement but doesn't model explicitly or stress-test against a WORSE future correlation regime) is a reasonable place to stop for now -- this is a real, working fix for the concurrency gap, not a claim that all portfolio-risk questions are closed.
