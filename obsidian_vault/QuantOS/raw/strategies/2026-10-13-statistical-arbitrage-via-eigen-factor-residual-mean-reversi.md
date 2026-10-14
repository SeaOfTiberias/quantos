---
title: 'Statistical Arbitrage via Eigen-Factor Residual Mean Reversion'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\statarb_duckling_strategy_spec.md'
checksum: c61ac21672e1d4be15827bf62406cc212427e345c1644fff42333673fc043e48
body_checksum: a3a544f4077fac7dcf5b3a798dff570f23671ead3878ddd0b700529d452979cc
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# Statistical Arbitrage via Eigen-Factor Residual Mean Reversion

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\statarb_duckling_strategy_spec.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

**Source Reference:** `quant_strategy.MP4` (Based on NYU Research by Marco Avellaneda & Sergio Lee)

---

## 1. Executive Summary & Core Analogy

The strategy described in `quant_strategy.MP4` is an institutional **Statistical Arbitrage (StatArb) Equity Market-Neutral** model. 

### The "Duckling" Analogy
* **The Mother Duck (The Factor/Family):** Stocks within the same sector or market cluster move together driven by macro factor exposures (e.g., Banking, Energy, Market Beta).
* **The Ducklings (Individual Stocks):** An individual stock occasionally strays from its sector "family" due to short-term order flow imbalances or noise.
* **The Edge:** When a stock strays beyond its historical volatility allowance without fundamental news, it creates a mean-reverting gap. The strategy **buys the straggler** (undervalued stock) and **shorts the family** (or buys the runaway and shorts the family), profiting as the gap closes regardless of broader market direction.

---

## 2. Quantitative & Mathematical Architecture

### Phase A: Factor Decomposition via PCA (Principal Component Analysis)
Rather than manually assigning stocks to rigid sector buckets, the algorithm uses **Eigen-Portfolios / PCA** across a 1,400+ equity universe:
1. **Extract 15 Dominant Risk Factors:**
   * **Factor 1:** Overall Market Beta (the main driver).
   * **Factor 2:** Tug-of-war dynamics (e.g., Oil vs. Airlines/Banks).
   * **Factors 3–15:** Industry and cross-sectional style risk factors.
2. **Explanatory Power:** These 15 factors explain ~50% of an individual stock's daily return. The remaining 50% is idiosyncratic noise (the "wander").

### Phase B: Residual Extraction & Normalization
For each stock $i$, regression against the 15 eigen-factors yields the residual return $\epsilon_i(t)$:
$$\text{Return}_i(t) = \sum_{k=1}^{15} \beta_{i,k} F_k(t) + \epsilon_i(t)$$

An $s$-score (Z-score of the cumulative residual process) is computed over a **60-day rolling lookback window**:
$$s = \frac{\text{Residual Position}}{\text{Historical Residual Standard Deviation}}$$

---

## 3. Systematic Trading Rules

| Parameter | Specification / Threshold |
| :--- | :--- |
| **Lookback Window** | 60 trading days |
| **Universe** | Large-cap liquid equities (e.g., S&P 500 / Nifty 500) |
| **Entry Trigger** | $|s| \ge 1.25$ (Price strays $> 1.25\times$ historical standard deviation) |
| **Long Entry** | Buy stock $i$, Short the 15-factor synthetic benchmark (when $s \le -1.25$) |
| **Short Entry** | Short stock $i$, Buy the 15-factor synthetic benchmark (when $s \ge +1.25$) |
| **Exit Trigger** | $s \approx 0$ (Price reverts back to the 60-day mean) |
| **Position Delta** | Strictly Market Neutral ($\Delta \approx 0$) |

---

## 4. Historical Track Record & The August 2007 Quant Meltdown

### The Golden Decade (1997 – 2006)
* **Performance:** Produced positive net returns for **10 consecutive years** including transaction costs.
* **Sharpe Ratio:** **1.44** (unleveraged, highly consistent returns with low correlation to market direction).

### The August 2007 Liquidation Cascade (The "Quant Crisis")
* **What Happened:** In August 2007, multiple multi-billion-dollar StatArb hedge funds faced margin calls and rushed to liquidate simultaneously.
* **The Failure Mode:** Forced liquidations caused funds to sell their "stragglers" (longs) and buy back their "runaways" (shorts). This **widened the spread** instead of reverting it, resulting in a 5%–10% loss in days for quantitative models.
* **Lesson on Crowding:** Pure mathematical statistical arbitrage is vulnerable to **crowded trade unwinds**. Once the forced liquidations cleared (within 2 weeks), prices reverted to the mean, but over-leveraged funds had already been wiped out.

---

## 5. Practical Implementation Guidelines for QuantOS

1. **Do Not Trade Single Pairs:** StatArb requires a **broad basket** (at least 30–50 simultaneous pairs/spreads) to allow the law of large numbers to work.
2. **Incorporate Stop-Loss / Time Limits:** Always enforce a max holding period (e.g., 10–15 days) and a hard stop-loss if $|s| \ge 3.0$ to protect against permanent fundamental regime shifts.
3. **Use Transaction Cost Models:** Ensure all backtests account for STT, borrow costs (for shorting legs in Indian markets), and bid-ask slippage.
