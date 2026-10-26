---
title: Strategy register — 2026-10-26
compiled: 2026-10-26
tags:
  - wiki/report
quantos:
  layer: wiki
  generated: true
---

# Strategy register — 2026-10-26

> [!abstract] Generated report
> Written by `python scripts/vault.py report` from the strategy-record properties on each `wiki/strategy` page (SCHEMA.md, "Strategy records"). Regenerate rather than edit. Numbers are each test's headline as recorded on its page; the page holds the evidence and its sources. Nothing here is a claim that a strategy is profitable.

## Summary

- **42** strategy records: 31 FAIL, 4 MIXED, 3 INCONCLUSIVE, 2 OPEN, 2 N/A.
- **Running now:** 5 ([[darvas-atr-stop-bucket-b]], [[momentum-turnover-candidate-11]], [[surge-spread-forward-23b]], [[fno-screener]], [[trade-watcher]]).
- **Real capital deployed:** none.

## Running now

| Strategy | Status | Verdict | Capital | Next gate | Gate date |
|---|---|---|---|---|---|
| [[darvas-atr-stop-bucket-b\|Darvas ATR-Scaled Stop, Bucket B]] | live-paper | **MIXED** | ₹5,00,000 paper; 9% of equity per position | User decision on the paper run after the 2026-10-24 fill finding; no move to real capital on the current evidence |  |
| [[momentum-turnover-candidate-11\|Momentum Turnover Ablation / Walk-Forward (Candidate 11)]] | live-paper | **OPEN** | ₹10,00,000 paper | Verdict only after 4 completed out-of-sample quarters; next quarterly rebalance 2026-12-31 | 2026-12-31 |
| [[surge-spread-forward-23b\|Wide Surge Bull Call Spreads, Forward Paper Test (Candidate 23b)]] | live-paper | **OPEN** | none (paper; read-only logger, no order code) | 60 closed paper trades (about 2½–3 months at ~25 surges a month); no P&L reported before then |  |
| [[fno-screener\|F&O Screener (Evening Call/Put Candidates)]] | live-tool | **N/A** | none (the user trades candidates manually) | Review the hit rate once 20–30 candidates exist |  |
| [[trade-watcher\|Trade Watcher (Discretionary Exit Alerts)]] | live-tool | **N/A** | the user's own manual positions | Stage 2 (real stop orders at the broker) only with the user's explicit go-ahead after stage 1 proves itself |  |

## By status

| Status | Total | PASS | FAIL | MIXED | INCONCLUSIVE | OPEN | N/A |
|---|---|---|---|---|---|---|---|
| live-paper | 3 |  |  | 1 |  | 2 |  |
| live-tool | 2 |  |  |  |  |  | 2 |
| closed | 32 |  | 28 | 2 | 2 |  |  |
| retired | 3 |  | 3 |  |  |  |  |
| shelved | 2 |  |  | 1 | 1 |  |  |

## By family

| Family | Total | PASS | FAIL | MIXED | INCONCLUSIVE | OPEN | N/A |
|---|---|---|---|---|---|---|---|
| breakout | 6 |  | 5 | 1 |  |  |  |
| momentum | 6 |  | 3 | 1 |  | 2 |  |
| trend | 2 |  | 1 | 1 |  |  |  |
| mean-reversion | 2 |  | 1 |  | 1 |  |  |
| stat-arb | 4 |  | 4 |  |  |  |  |
| volatility-premium | 2 |  | 2 |  |  |  |  |
| vol-conditioning | 5 |  | 5 |  |  |  |  |
| intraday-options | 8 |  | 7 | 1 |  |  |  |
| calendar-effect | 1 |  |  |  | 1 |  |  |
| event-drift | 3 |  | 2 |  | 1 |  |  |
| ml-factor | 1 |  | 1 |  |  |  |  |
| discretionary-aid | 2 |  |  |  |  |  | 2 |

## By instrument

| Instrument | Total | PASS | FAIL | MIXED | INCONCLUSIVE | OPEN | N/A |
|---|---|---|---|---|---|---|---|
| equity-cash | 13 |  | 8 | 2 | 2 | 1 |  |
| stock-futures | 5 |  | 4 | 1 |  |  |  |
| index-futures | 3 |  | 3 |  |  |  |  |
| index-options | 14 |  | 11 | 1 | 1 |  | 1 |
| stock-options | 5 |  | 3 |  |  | 1 | 1 |
| mixed | 2 |  | 2 |  |  |  |  |

## Register (newest verdict first)

| Strategy | Cand. | Family | Instrument | Status | Verdict | Verdict date | PF | Sharpe | Trades | Headline |
|---|---|---|---|---|---|---|---|---|---|---|
| [[emt-vwap-nifty-5m\|EMT Exhaustion Mean Reversion to VWAP, NIFTY 5-minute]] | EMT phase 1 | mean-reversion | index-options | closed | **FAIL** | 2026-10-26 | 0.77 |  | 921 | Fading a 5-minute NIFTY or BankNifty stretch from VWAP on the first bar back fails on both indices, and NIFTY shorts alone fail on two fresh years, so it was never taken to options. |
| [[fno-screener-cci-sma-filters\|CCI(34)/EMA52 and SMA 5/40 as F&O Screener Filters]] | screener filter 2026-10-26 | trend | stock-futures | closed | **MIXED** | 2026-10-26 |  |  | 2612 | Both daily indicators agree with 93-99% of screener picks already, so as filters they remove almost nothing; 1 of 9 tests clears the bar on a 0.02%-per-trade change, so neither is worth adding. |
| [[fx-eurusd-gbpusd-cointegration\|EUR/USD vs GBP/USD Cointegration]] | New tracks B (spec 1.1) | stat-arb | mixed | closed | **FAIL** | 2026-10-25 | 0.71 | -0.20 | 100 | A rolling Johansen/ADF/half-life pair trade on EUR/USD and GBP/USD lost money over 2000–2026, even at 1-pip costs. |
| [[put-setups-mid-range-downtrend\|Put Setups (Mirrored Darvas vs Mid-Range Downtrends)]] | Put setups A / B-A / C (2026-10-25) | breakout | stock-futures | closed | **FAIL** | 2026-10-25 |  |  | 667 | Counted once per episode, none of three put setups predicts a 5-session fall: the live mirrored-Darvas put rule (+0.06% excess, second half -0.32%), adding laggard names, and a failed-rally-in-a-downtrend setup all fail. |
| [[surge-bull-put-credit\|Surge Bull Put Credit Spread (IV Rank Gate)]] | New tracks A (spec 2.2b) | momentum | stock-options | closed | **FAIL** | 2026-10-25 | 1.01 | 0.01 | 128 | Selling ~35-delta put spreads on non-52-week-high surges with IV rank >= 0.70 broke even after costs: 77% of trades won, but stops cost more than the wins made, and the first half lost. |
| [[darvas-atr-stop-bucket-b\|Darvas ATR-Scaled Stop, Bucket B]] | Darvas line 3 (ATR stop) | breakout | equity-cash | live-paper | **MIXED** | 2026-10-24 |  |  | 991 | The 2016–2023 out-of-sample pass (+2.16%/trade) relied on filling stops that had trailed above the market; with realistic next-open fills it makes +0.38% net and trails its universe by 1.09% a trade. Still on paper; status is the user's call. |
| [[darvas-bucket-b-cues\|Darvas Bucket B Cue Tests (Universe, Entry Filters, Exits)]] | Darvas line 3 add-ons, T1–T8 | breakout | equity-cash | closed | **FAIL** | 2026-10-24 |  |  | 1950 | All 8 pre-registered tests failed: no small-cap universe edge, and none of four entry filters or three exits beat the baseline Bucket B rule. |
| [[earnings-gap-drift\|Earnings-Gap Drift (price/volume PEAD proxy)]] | gut-check | event-drift | equity-cash | closed | **FAIL** | 2026-10-21 |  |  | 2653 | Buying after a ±5% move on ≥ 4× volume, entered the next day, shows no up-drift (median stock lags the market) and only a small, fading down-drift that reversed in 2025–26 — not a signal. |
| [[surge-spread-candidate-23\|Surge Option Spreads (Candidate 23)]] | 23 | momentum | stock-options | closed | **FAIL** | 2026-10-15 | 0.92 | -0.10 | 1748 | Stage 1 found real continuation after +5% surges below the 52-week high, but bull call spreads on closing option prices lost it to bid-ask: no strike pair cleared PF 1 in 2020–24 at a realistic spread cost. |
| [[surge-spread-forward-23b\|Wide Surge Bull Call Spreads, Forward Paper Test (Candidate 23b)]] | 23b | momentum | stock-options | live-paper | **OPEN** |  |  |  |  | Forward paper test of one fixed wide bull call spread (L2W4) on +5% surges below the 52-week high, filled at live bid/ask at 15:15 IST; separates a real 2025–26 change from best-of-16 luck. |
| [[statarb-residual-mean-reversion\|StatArb Residual Mean Reversion ("Straying Duckling")]] | 22 | stat-arb | stock-futures | closed | **FAIL** | 2026-10-13 | 0.86 | -0.76 | 2245 | Avellaneda–Lee residual s-scores did not predict reversion on BankNifty or Nifty 50 stock futures; gross edge about zero against costs; residual/pairs mean reversion on NSE futures retired. |
| [[fno-screener\|F&O Screener (Evening Call/Put Candidates)]] | — | discretionary-aid | stock-options | live-tool | **N/A** |  |  |  |  | Evening Telegram list of stock call/put candidates for discretionary 1–5 day swings; no orders; first live run 2026-10-12. |
| [[trade-watcher\|Trade Watcher (Discretionary Exit Alerts)]] | — | discretionary-aid | index-options | live-tool | **N/A** |  |  |  |  | Alerts-only exit manager for the user's manual option trades (Telegram, no order code); stage 2 real stop orders need an explicit go-ahead. |
| [[vrp-iv-gated-short-premium\|IV-Gated Short Premium (VRP Follow-up)]] | VRP follow-up | volatility-premium | index-options | closed | **FAIL** | 2026-10-06 | 0.71 | -0.40 | 50 | Selling NIFTY weekly premium only when ATM IV is in its top third lost money on never-seen 2019–2023 data: high IV arrived at the start of the COVID crash, not after it. |
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
