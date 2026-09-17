---
title: ORB Options Scalping (Candidate 18)
compiled: 2026-09-17
tags:
  - wiki/concept
  - strategy/passed
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-09-17-opening-range-breakout-options-scalping-methodology-pre-comm, 2026-09-17-orb-options-scalping-backtest-results-candidate-18, 2026-09-17-orb-options-scalping-condition-mining-methodology-pre-commit, 2026-09-17-orb-condition-mining-results, 2026-09-17-orb-options-scalping-event-triggered-stop-out-spread-probe-s
---

# ORB Options Scalping (Candidate 18)

> [!abstract] Compiled page
> Written from `[[2026-09-17-opening-range-breakout-options-scalping-methodology-pre-comm]]`, `[[2026-09-17-orb-options-scalping-backtest-results-candidate-18]]`, `[[2026-09-17-orb-options-scalping-condition-mining-methodology-pre-commit]]`, `[[2026-09-17-orb-condition-mining-results]]`, and `[[2026-09-17-orb-options-scalping-event-triggered-stop-out-spread-probe-s]]` on 2026-09-17. Context and retrieval only — rules in this layer never execute.

## Definition

A self-designed classic Opening Range Breakout, traded as NIFTY and BankNifty index options — the only strategy in this project's search to pass its own pre-registered cost bar. Raised as a use for otherwise-idle TradingView Premium; the user explicitly chose to hold it to this project's full validated-edge standard rather than build it as a discretionary tool.

## Mechanics

- **Range**: the first three 5-minute candles of the session (09:15–09:30 IST) set `(high, low)`.
- **Entry**: from the 4th candle onward, on candle CLOSE (not intrabar): close above range high → CALL; close below range low → PUT. First occurrence only, one trade per day. Executes at the next candle's open.
- **Exit**: broker-side trailing stop (opposite side of the opening range at entry; once price moves one range-width favorably, trails to the low/high of the prior 3 candles, ratchets only) OR a secondary hard 25%-of-premium stop, whichever fires first, OR the 15:20 IST session flatten.
- **Contracts**: BankNifty nearest monthly; NIFTY nearest weekly with a DTE<2 floor rolling to the next weekly. Strike is nearest ATM at entry, fixed.
- **Premium**: Black-Scholes reconstruction from the real index level + a contemporaneous India VIX-derived IV input (not a real traded option price — no historical intraday option data exists on this project's data source for any expired contract).
- **Cost model**: Clean (no slippage) and Stressed (+15bps/leg) reported side by side; the Stressed number gates any live-capital decision.

## Verdict

**PASS on the Stressed variant, both indices, independently** (never pooled) `[[2026-09-17-orb-options-scalping-backtest-results-candidate-18]]`:

| | NIFTY | BankNifty |
|---|---|---|
| Trades | 1036 (2022–2026) | 1268 (2021–2026) |
| Profit factor | 1.23 (Stratified, locked-final) | 1.16 |
| Sharpe | 0.88 | 0.95 |

This is the *Stratified* variant — the final, most rigorously cost-modeled read after several post-hoc stress tests, expiry-day-aware. The bar (PF>1.0, Sharpe>0.5) is cleared with margin on both indices, and per-year results are mostly consistent (NIFTY dips in 2023 and 2026; BankNifty dips in 2022 and 2025; neither index goes structurally negative).

**Not yet live.** A separate go/no-go checklist gates real capital, independent of this backtest passing.

### Condition-mining follow-up (informative, not a new strategy)

A separate, pre-registered exercise asked whether the *unmodified* signal could be gated to fire only under conditions resembling its historical wins, rather than firing on ~95–98% of trading days — explicitly designed to avoid the same trap that made this project's regime/vol-conditioning line fail 5-for-5. Of five candidate conditions (index trend stage, day-of-week, opening-range width, gap-at-open, DTE bucket), tested with a strict 3-step bar (minimum n=30 per side, mining-set improvement, holdout confirmation on the most recent 20% by date):

- **Informative** (cleared all three steps): `monday_or_friday` on NIFTY (holdout n=83, PF 1.14, Sharpe 1.14); `big_gap` on BankNifty (holdout n=109, PF 1.44, Sharpe 1.62).
- **Not informative** (failed the holdout step despite passing on the mining set): NIFTY's `stage2` and `wide_range`; BankNifty's `monday_or_friday`, `wide_range`, `dte_10_plus`.

Per the pre-registration, a condition clearing this bar is a hypothesis for a *new*, separately pre-registered candidate — not an immediate change to what candidate 18 fires on, and not a capital decision `[[2026-09-17-orb-options-scalping-condition-mining-methodology-pre-commit]]`.

### Stop-out spread probe (pending)

The Stratified cost model's spread samples were all measured on a fixed clock during calm moments — the strategy's real exits are stop-outs, which happen during fast-market moments a fixed clock never observes. A live probe snapshots the real bid-ask spread at the instant a stop-out actually fires; the result is not read until N≥20 stop-out events per index AND at least 4 calendar weeks have elapsed since 2026-09-03 (earliest possible clear: 2026-10-01) `[[2026-09-17-orb-options-scalping-event-triggered-stop-out-spread-probe-s]]`.

## Relation to other concepts

- The regime/vol-conditioning line this project ran five times — [[regime-classifier-s8-1]], [[iv-minus-rv-vol-spread]], [[nifty-banknifty-option-skew]], [[atm-iv-term-structure]], [[event-proximity-vol]] — is explicitly the trap the condition-mining exercise above was designed not to repeat: mining a signal's own trade outcomes for "what made it win" without a mining/holdout split is the same rescue-narrative maneuver as reporting a regime-filtered subset as the headline.
- [[breakout-1010-banknifty-candidate-15]] shares this candidate's synthetic-Black-Scholes-premium limitation and its cost-sensitivity risk, but failed where this passed — the two are the same instrument family (BankNifty options) tested to different results.
