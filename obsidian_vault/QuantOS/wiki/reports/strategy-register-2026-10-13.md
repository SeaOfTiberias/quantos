---
title: Strategy register — 2026-10-13
compiled: 2026-10-13
tags:
  - wiki/report
quantos:
  layer: wiki
  generated: true
---

# Strategy register — 2026-10-13

> [!abstract] Generated report
> Written by `python scripts/vault.py report` from the strategy-record properties on each `wiki/strategy` page (SCHEMA.md, "Strategy records"). Regenerate rather than edit. Numbers are each test's headline as recorded on its page; the page holds the evidence and its sources. Nothing here is a claim that a strategy is profitable.

## Summary

- **33** strategy records: 1 PASS, 24 FAIL, 2 MIXED, 3 INCONCLUSIVE, 1 OPEN, 2 N/A.
- **Running now:** 4 ([[darvas-atr-stop-bucket-b]], [[momentum-turnover-candidate-11]], [[fno-screener]], [[trade-watcher]]).
- **Real capital deployed:** none.

## Running now

| Strategy | Status | Verdict | Capital | Next gate | Gate date |
|---|---|---|---|---|---|
| [[darvas-atr-stop-bucket-b\|Darvas ATR-Scaled Stop, Bucket B]] | live-paper | **PASS** | ₹5,00,000 paper; 9% of equity per position | User's explicit go-ahead to flip dry_run to real capital (plan: ₹5L real after a few days of paper) |  |
| [[momentum-turnover-candidate-11\|Momentum Turnover Ablation / Walk-Forward (Candidate 11)]] | live-paper | **OPEN** | ₹10,00,000 paper | Verdict only after 4 completed out-of-sample quarters; next quarterly rebalance 2026-12-31 | 2026-12-31 |
| [[fno-screener\|F&O Screener (Evening Call/Put Candidates)]] | live-tool | **N/A** | none (the user trades candidates manually) | Review the hit rate once 20–30 candidates exist |  |
| [[trade-watcher\|Trade Watcher (Discretionary Exit Alerts)]] | live-tool | **N/A** | the user's own manual positions | Stage 2 (real stop orders at the broker) only with the user's explicit go-ahead after stage 1 proves itself |  |

## By status

| Status | Total | PASS | FAIL | MIXED | INCONCLUSIVE | OPEN | N/A |
|---|---|---|---|---|---|---|---|
| live-paper | 2 | 1 |  |  |  | 1 |  |
| live-tool | 2 |  |  |  |  |  | 2 |
| closed | 24 |  | 21 | 1 | 2 |  |  |
| retired | 3 |  | 3 |  |  |  |  |
| shelved | 2 |  |  | 1 | 1 |  |  |

## By family

| Family | Total | PASS | FAIL | MIXED | INCONCLUSIVE | OPEN | N/A |
|---|---|---|---|---|---|---|---|
| breakout | 4 | 1 | 3 |  |  |  |  |
| momentum | 3 |  | 1 | 1 |  | 1 |  |
| trend | 1 |  | 1 |  |  |  |  |
| mean-reversion | 1 |  |  |  | 1 |  |  |
| stat-arb | 3 |  | 3 |  |  |  |  |
| volatility-premium | 2 |  | 2 |  |  |  |  |
| vol-conditioning | 5 |  | 5 |  |  |  |  |
| intraday-options | 8 |  | 7 | 1 |  |  |  |
| calendar-effect | 1 |  |  |  | 1 |  |  |
| event-drift | 2 |  | 1 |  | 1 |  |  |
| ml-factor | 1 |  | 1 |  |  |  |  |
| discretionary-aid | 2 |  |  |  |  |  | 2 |

## By instrument

| Instrument | Total | PASS | FAIL | MIXED | INCONCLUSIVE | OPEN | N/A |
|---|---|---|---|---|---|---|---|
| equity-cash | 11 | 1 | 6 | 1 | 2 | 1 |  |
| stock-futures | 3 |  | 3 |  |  |  |  |
| index-futures | 3 |  | 3 |  |  |  |  |
| index-options | 13 |  | 10 | 1 | 1 |  | 1 |
| stock-options | 2 |  | 1 |  |  |  | 1 |
| mixed | 1 |  | 1 |  |  |  |  |

## Register (newest verdict first)

| Strategy | Cand. | Family | Instrument | Status | Verdict | Verdict date | PF | Sharpe | Trades | Headline |
|---|---|---|---|---|---|---|---|---|---|---|
| [[statarb-residual-mean-reversion\|StatArb Residual Mean Reversion ("Straying Duckling")]] | 22 | stat-arb | stock-futures | closed | **FAIL** | 2026-10-13 | 0.86 | -0.76 | 2245 | Avellaneda–Lee residual s-scores did not predict reversion on BankNifty or Nifty 50 stock futures; gross edge about zero against costs; residual/pairs mean reversion on NSE futures retired. |
| [[fno-screener\|F&O Screener (Evening Call/Put Candidates)]] | — | discretionary-aid | stock-options | live-tool | **N/A** |  |  |  |  | Evening Telegram list of stock call/put candidates for discretionary 1–5 day swings; no orders; first live run 2026-10-12. |
| [[trade-watcher\|Trade Watcher (Discretionary Exit Alerts)]] | — | discretionary-aid | index-options | live-tool | **N/A** |  |  |  |  | Alerts-only exit manager for the user's manual option trades (Telegram, no order code); stage 2 real stop orders need an explicit go-ahead. |
| [[vrp-iv-gated-short-premium\|IV-Gated Short Premium (VRP Follow-up)]] | VRP follow-up | volatility-premium | index-options | closed | **FAIL** | 2026-10-06 | 0.71 | -0.40 | 50 | Selling NIFTY weekly premium only when ATM IV is in its top third lost money on never-seen 2019–2023 data: high IV arrived at the start of the COVID crash, not after it. |
| [[darvas-atr-stop-bucket-b\|Darvas ATR-Scaled Stop, Bucket B]] | Darvas line 3 (ATR stop) | breakout | equity-cash | live-paper | **PASS** | 2026-10-05 | 1.46 | 1.79 | 991 | Only validated live strategy: in-sample pass, failed a falsification pass, then passed a frozen-rules 2016–2023 out-of-sample test; paper trading since 2026-10-08. |
| [[ema8-second-trade\|EMA-8 Slope, Second Trade of the Day]] | — | intraday-options | index-futures | closed | **FAIL** | 2026-10-01 |  |  | 1313 | The NIFTY pattern from a TradingView run (second trade of the day beats the first) held statistically on BankNifty but lost ₹487/trade after futures costs. |
| [[trend-day-filter-candidate-21\|Trend-Day Filter (Candidate 21)]] | 21 | intraday-options | index-futures | closed | **FAIL** | 2026-10-01 | 0.81 |  | 224 | Trading only 'trend days' with a 2×ATR trail lost money after futures costs on both indices (NIFTY −₹295/trade, BankNifty −₹718/trade). |
| [[orb-entry-filter-candidate-18b\|ORB Entry Filter (Candidate 18b)]] | 18b | intraday-options | index-options | retired | **FAIL** | 2026-09-30 |  |  | 1035 | Gating candidate 18 to NIFTY Mondays/Fridays and BankNifty big-gap days showed no significant edge in index points (p 0.46 / 0.32), so the mined filters were labelled a pricing artifact; stopped with candidate 18. |
| [[orb-options-scalping-candidate-18\|ORB Options Scalping (Candidate 18)]] | 18 | intraday-options | index-options | retired | **FAIL** | 2026-09-30 | 0.85 | -1.14 | 1056 | Passed its original backtest on both indices, then failed on both once option premiums were priced with a convention calibrated to real quotes; closed and timers stopped 2026-09-30. |
| [[index-reconstitution-effect\|Index Reconstitution Effect]] | — | event-drift | equity-cash | closed | **FAIL** | 2026-09-25 |  |  |  | Closed as untradeable: the required short leg has no F&O coverage, so the strategy cannot be run as designed. |
| [[pead-earnings-drift\|PEAD (Post-Earnings Announcement Drift)]] | — | event-drift | equity-cash | shelved | **INCONCLUSIVE** | 2026-09-25 |  |  |  | Shelved as inconclusive: not enough new data to test it properly, so it is neither a clean fail nor adoptable. |
| [[darvas-box-width\|Darvas Box-Width Buckets (Static Exit)]] | Darvas line 1 (box width) | breakout | equity-cash | closed | **FAIL** | 2026-09-22 | 0.69 | -1.77 | 210 | Wider Darvas boxes looked better on raw forward returns, but every width bucket loses money once a real stop, target and costs are applied. |
| [[darvas-trailing-stop\|Darvas Trailing Stop/Target]] | Darvas line 2 (trailing stop) | breakout | equity-cash | closed | **FAIL** | 2026-09-22 | 1.00 | 0.01 | 210 | Trailing the stop and target to each new higher box improved every cell, but Bucket B's mining set landed exactly at breakeven (PF 1.00, Sharpe 0.01). |
| [[goodnight-scalper-candidate-20\|Good Night Stock-Options Scalper (Candidate 20)]] | 20 | intraday-options | stock-options | closed | **FAIL** | 2026-09-17 | 0.54 | -2.80 | 444 | Overnight-gap stock-option scalp passed with clean costs but inverted under real measured spreads (PF 0.54, Sharpe −2.80). |
| [[candle-confirm-momentum-gutcheck-candidate-19\|Candle-Confirm Momentum (Candidate 19, Gut-Check)]] | 19 | intraday-options | index-options | closed | **FAIL** | 2026-08-04 |  |  | 1133 | Candle-agreement entries won about 50% of the time with returns indistinguishable from baseline: no edge to take further. |
| [[atm-iv-term-structure\|NIFTY / BankNifty ATM IV Term Structure]] | — | vol-conditioning | index-options | closed | **FAIL** | 2026-07-27 |  |  |  | ATM IV term structure reproduced the same non-monotonic smile as the other vol-conditioning signals on both underlyings. |
| [[breakout-1010-banknifty-candidate-15\|10:10 Breakout on BankNifty Options (Candidate 15)]] | 15 | intraday-options | index-options | shelved | **MIXED** | 2026-07-27 | 1.11 | 0.65 | 1273 | A marginal mechanical pass (₹54/trade average) on synthetic option prices only, an edge a real spread could erase; shelved, never re-opened. |
| [[dow-theory-trend-candidate-14\|Dow Theory / Market Structure Trend Following (Candidate 14)]] | 14 | trend | index-futures | closed | **FAIL** | 2026-07-27 | 0.88 | 2.23 | 3650 | Sharpe 2.23 looked strong but profit factor stayed below 1 in every year except 2024: a real rupee loss, with costs 2.6× the gross edge. |
| [[event-proximity-vol\|Known-Event (RBI/Budget) Proximity vs Forward Volatility]] | — | vol-conditioning | index-options | closed | **FAIL** | 2026-07-27 |  |  |  | Days near known RBI and Budget events showed lower forward volatility than ordinary days, the opposite of the hypothesis; fifth vol-conditioning fail. |
| [[ml-factor-combination-candidate-16\|ML Multi-Factor Stock Ranking (Candidate 16)]] | 16 | ml-factor | equity-cash | closed | **FAIL** | 2026-07-27 |  | 0.29 | 236 | The ML ranking's apparent win over the single-factor baseline was a turnover-cost artifact; gross, the baseline was as good. Sharpe 0.29. |
| [[pairs-trading-v2-candidate-17\|Sector-Cointegrated Pairs Trading v2, Bug-Fixed (Candidate 17)]] | 17 | stat-arb | stock-futures | closed | **FAIL** | 2026-07-27 | 1.04 | 0.14 | 4535 | Bug-fixed pairs re-run turned net P&L positive (+₹23.5L) but Sharpe stayed 0.14; the late-fold collapse persisted, read as a regime shift. |
| [[expiry-day-effect-gutcheck-candidate-13\|F&O Monthly Expiry-Day Effect (Candidate 13, Gut-Check)]] | 13 | calendar-effect | index-options | closed | **INCONCLUSIVE** | 2026-07-26 |  |  | 31 | Expiry days were quieter, not louder, than ordinary days on only 31 expiries; no full backtest built. |
| [[pairs-trading-candidate-12\|Sector-Cointegrated Stock-Futures Pairs Trading (Candidate 12)]] | 12 | stat-arb | stock-futures | closed | **FAIL** | 2026-07-26 | 0.94 | -0.17 | 4705 | Same-sector cointegrated stock-futures pairs: folds 1–5 profitable, folds 6–8 collapse, net −₹38.2L. |
| [[momentum-turnover-candidate-11\|Momentum Turnover Ablation / Walk-Forward (Candidate 11)]] | 11 | momentum | equity-cash | live-paper | **OPEN** |  |  | 0.81 | 244 | Quarterly rebalance of the S8-3 ranking closed most of the in-sample Sharpe gap (0.81 vs 0.34); now a ₹10L quarterly paper walk-forward, no verdict before 4 quarters. |
| [[nifty-banknifty-option-skew\|NIFTY / BankNifty Option Skew]] | — | vol-conditioning | index-options | closed | **FAIL** | 2026-07-25 |  |  |  | Option skew showed an endpoint gap but no monotonic forward-volatility ordering on either NIFTY or BankNifty. |
| [[iv-minus-rv-vol-spread\|IV-minus-RV Vol Spread]] | — | vol-conditioning | index-options | closed | **FAIL** | 2026-07-24 |  |  | 1228 | The richest IV-minus-RV quintile earned less premium and hit less often than the cheapest: wrong direction. |
| [[mean-reversion-alpha50-gutcheck-s2\|Mean-Reversion on Nifty Alpha 50 (Strategy 2, Gut-Check)]] | S2 | mean-reversion | equity-cash | closed | **INCONCLUSIVE** | 2026-07-24 |  |  | 1159 | RSI mean-reversion on Alpha 50 stocks showed a small, inconsistent gap (+0.06 pp at 20 days) on about 394 independent dates; no backtest built. |
| [[regime-filtered-dual-momentum-s1\|Regime-Filtered Dual-Momentum (Strategy 1)]] | S1 | momentum | equity-cash | closed | **MIXED** | 2026-07-24 | 1.24 | 0.82 | 873 | Pooled-trade pass (PF 1.24, Sharpe 0.82) but equity-curve Sharpe 0.45 in the clean sub-period, a half-split degradation flag and a −53 pt gap to Alpha 50; not adopted. |
| [[rs-momentum-rotation-s8-3\|52-Week-High RS Momentum Rotation (S8-3)]] | S8-3 | momentum | equity-cash | retired | **FAIL** | 2026-07-23 | 1.18 | 0.34 | 2104 | Passed the pooled-trade screen but lost to Nifty 500 (−15.6 pt) and Nifty Alpha 50 (−64.6 pt) once survivorship-corrected; weekly dry run and pilot switched off 2026-10-12. |
| [[vrp-short-strangle\|Options VRP Short Strangle]] | VRP | volatility-premium | index-options | closed | **FAIL** | 2026-07-23 | 1.03 | 0.09 | 157 | Selling weekly NIFTY strangles wins 70.7% of the time but the occasional large loss leaves Sharpe at 0.09 net. |
| [[darvas-sepa-s7-3\|Darvas Box / SEPA Breakout (S7-3)]] | S7-3 | breakout | equity-cash | closed | **FAIL** | 2026-07-19 | 0.75 | -1.25 | 690 | The original Darvas/SEPA breakout failed its first pre-registered backtest; even zero-slippage costs missed the Sharpe bar (0.22). |
| [[nifty-ema-options-s8-4\|NIFTY EMA9/21 Options Strategy (S8-4)]] | S8-4 | intraday-options | index-options | closed | **FAIL** | 2026-07-19 | 1.00 | 0.03 | 693 | Backtest of the live discretionary NIFTY EMA9/21 options exits: the baseline sits at breakeven (PF 1.00, Sharpe 0.03) and neither proposed fix clears the bar. |
| [[regime-classifier-s8-1\|VIX-Level Regime Classifier (S8-1)]] | S8-1 | vol-conditioning | mixed | closed | **FAIL** | 2026-07-19 |  |  |  | The live regime classifier does not separate forward outcomes; VOLATILE, where the system cuts size, preceded the best forward returns. |
