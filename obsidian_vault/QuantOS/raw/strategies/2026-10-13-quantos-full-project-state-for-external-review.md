---
title: 'QuantOS — Full Project State for External Review'
ingested: 2026-10-13
origin: 'D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\PROJECT_STATE_FOR_EXTERNAL_REVIEW.md'
checksum: 201a787bec62e3f1fe8b98475584b63c9ec9e082963f59773f8734fd2ddfd830
body_checksum: d65700cccbb8c2a6bfe4ac2e6d5a647873623220a1ab9e64a50e1ac9794e74ea
tags:
  - source/strategies
quantos:
  layer: raw
  immutable: true
---

# QuantOS — Full Project State for External Review

> [!info] Ingested source
> Filed 2026-10-13 from `D:\Exodus_14_14\QuantOS\quantos\obsidian_vault\QuantOS\raw\_inbox\PROJECT_STATE_FOR_EXTERNAL_REVIEW.md`. Do not edit — wiki pages cite this
> file's contents, and `vault lint` re-hashes it to check.

Written 2026-09-25. This document is a handoff summary of an ~11-week
algorithmic trading research project (QuantOS, NSE/India-focused,
single-operator). It is being submitted to an external AI system for a
second opinion on process, methodology, and what to do next. It is
written to be read cold, by a system with zero prior context.

The blunt framing the operator wants on record: **after ~11 weeks and
~20+ strategy candidates, zero real capital has been deployed on any
strategy.** The process used a cheap statistical screen (profit factor
and Sharpe ratio on pooled, unweighted per-trade returns) to gate every
candidate, and did not build real-capital equity-curve/position-sizing
validation for a candidate until months after the first candidate ever
passed that cheap screen. This document lays out the full strategy list,
what was tested, what the results were, and the specific process gaps
that were only identified in the final week of this document's own
history — the operator wants an outside system's read on whether this
process is sound, wasteful, or salvageable, and what a better version of
it looks like.

## 1. What this project is

An automated NSE (India) equities + index-options trading research and
execution system, single operator, self-hosted (Oracle free-tier VM,
Fyers broker API, SQLite/Postgres, systemd timers). Goal as originally
stated: find and deploy a real, statistically-validated, cost-net
profitable trading strategy with real capital.

Core backtest infrastructure: `core/backtest/parser.py` computes pooled
per-trade metrics (profit factor, Sharpe, win rate, max drawdown-as-%,
net profit-as-%) from a list of trades, and defines the standing gate
used across nearly every candidate: **`has_positive_edge` = profit factor
> 1.0 AND Sharpe > 0.5**. Until 2026-09-24, the Sharpe calculation used a
HARDCODED annualization factor (144 trades/year, i.e. ~12/month)
regardless of a strategy's actual trading frequency — a bug that silently
overstated Sharpe for slow-trading strategies and understated it for
fast-trading ones. This was found and fixed project-wide that day (see
section 4).

## 2. Full list of strategy candidates tested

Numbered roughly in the order they were attempted. "PASS/FAIL" refers
ONLY to the pooled PF>1/Sharpe>0.5 screen described above, not to any
real-capital validation (see section 4 for why that distinction now
matters).

| # | Strategy | Asset class | Verdict | Notes |
|---|---|---|---|---|
| 1 | S8-3 rotation (momentum/basket, top-N Nifty 500) | Equities | RETIRED | Initial +8pt alpha vs. benchmark was later found to be pure survivorship bias (point-in-time universe reconstruction was missing); after fixing that, it LOSES to both the Nifty 500 and Nifty Alpha 50 benchmarks. Retired 2026-08-18. |
| 11 | Momentum turnover ablation (regime-conditioned momentum rotation) | Equities | PASSED initial gate, then PAUSED for out-of-sample walk-forward | First candidate to clear the PF/Sharpe bar (2026-07-25). Currently LIVE on the VM in PAPER-TRADING ONLY (dry_run) since 2026-07-27. Its own pre-registered walk-forward methodology does not permit a verdict until roughly 2027 Q3 — i.e. it has been running unattended, unvalidated toward a real capital decision, for 2+ months with over a year left before its own rule allows a conclusion. |
| 12 | Pairs trading (v1) | Equities (long/short pairs) | FAIL | Closed 2026-07-26. |
| 13 | Expiry-day effect | Index options | FAIL | Quieter than baseline; closed 2026-07-26. |
| 14 | Dow theory / market-structure trend-following | Futures | FAIL | Real net loss; transaction costs were 2.6x the gross edge. Closed 2026-07-27. |
| 15 | 10:10 opening breakout (BankNifty options) | Index options | Marginal PASS (PF 1.11, Sharpe 0.65 pooled) | Originally characterized as "edge smaller than realistic spread" and effectively shelved; a later Sharpe-annualization correction (section 4) would raise its Sharpe further (~0.85), which was never revisited as a reason to reopen it. |
| 16 | ML factor combination | Equities | FAIL | Apparent edge was a turnover-cost artifact; the un-turned-over baseline wins gross. Closed 2026-07-27. |
| 17 | Pairs trading (v2, bug-fixed) | Equities | FAIL (fragile) | Closed 2026-07-27: "fold collapse is a real regime shift," a substantive, independent finding. A later Sharpe-correction pass found the pooled Sharpe (-0.17 → ~0.14 → ~0.56 once correctly annualized) technically crosses the 0.5 bar on an approximated window — reported as a fragile, unresolved flip, not re-opened. |
| 18 | ORB (opening-range breakout) options scalping, NIFTY + BankNifty | Index options | PASS (PF/Sharpe, "Stratified" locked-final cost variant) | See section 3 — this is the candidate with the most work done post-screen, and the one that exposed the core process gap. |
| 18b | ORB entry-filtered variant (NIFTY Mon/Fri only, BankNifty big-gap-day only) | Index options | PENDING — live since 2026-09-22 | Own pre-registered gate: N≥20 new trades per index AND ≥8 weeks elapsed before any verdict. Not due until 2026-11-17. Currently 0.3 weeks in. |
| 19 | Candle-confirm momentum | Equities | FAIL | Fails at a cheap gut-check (~50% win rate) before a full backtest was even justified. Closed 2026-08-04. |
| 20 | Goodnight scalper (overnight-gap options scalp) | Index options | FAIL | Stressed-cost Sharpe -2.80; liquidity concern confirmed via a recurring probe. |
| — | Volatility risk premium (VRP) | Index options | FAIL | PF 1.034, Sharpe 0.092. Closed 2026-07-23. |
| — | PEAD (post-earnings announcement drift) | Equities | SHELVED, inconclusive | No new data available to test properly; not a clean fail, not adoptable either. |
| — | Index reconstitution effect | Equities | CLOSED | The required short leg has zero F&O (derivatives) coverage — mechanically untradeable as designed. |
| — | Five separate volatility-regime-conditioning attempts (term structure, event proximity, VIX-based filters, etc.) | Mixed | 5-for-5 FAIL | Every attempt at conditioning a signal on volatility/regime state failed; this line of research was explicitly closed for good on the fifth failure. |
| — | S1 — regime-filtered dual momentum | Equities | Mixed / not adopted | Pooled per-trade Sharpe clears the bar comfortably (0.51–0.82 across variants) but the SEPARATE daily-equity-curve Sharpe (a different calculation, see section 4) fails its own 0.5 bar in the most realistic sub-period (0.45). Not adopted; regime filter itself is informational-only per an earlier 0-for-2 regime-conditioning record. |
| — | Darvas box-width variations | Equities | FAIL | All width buckets, all cost splits fail. |
| — | Darvas trailing-stop variant | Equities | FAIL | Improves every cell vs. the static-stop baseline but still fails the pre-registered bar — closest miss in this line. |
| — | Darvas ATR-scaled stop variant | Equities | PASS (2026-09-24, "SETTLED") | The second candidate (after 18) to clear the PF/Sharpe bar. Explicitly logged internally as "panel-ready, not capital-ready" — no real-capital equity-curve or position-sizing work has been done on it as of this document (see section 5, this is the next thing being built). |
| — | ORB arm-threshold sensitivity sweep | Index options | CLOSED | Every tested multiplier below the live default performed worse; replicated twice. |
| — | ORB condition-mining (which entry conditions add value) | Index options | Partial | Found a small number of informative conditions (feeding into candidate 18b above); most tested conditions were not informative once checked against a holdout window. |

**Total: roughly 20-22 distinct strategy candidates tested over ~11
weeks. Two cleared the statistical screen outright (18, Darvas ATR-stop).
One (11) cleared an earlier version of the screen and is in a
multi-year-long out-of-sample validation with no near-term verdict.
Everything else failed or was shelved. Zero have ever traded real
capital.**

## 3. What was actually done for candidate 18 (the most-developed case)

This is the candidate used to discover the process gap described in
section 4, so its full history matters:

1. Backtested NIFTY + BankNifty 5-minute opening-range-breakout options
   signals over ~4-5 years of real historical data (Fyers broker API).
2. Costed SIX progressively more realistic ways (Clean → Stressed →
   Harsh → Real-spread-single-snapshot → Sampled-spread → Stratified),
   each round of cost-modeling found and fixed a methodology problem in
   the previous round (a contaminated sample, a wrong-contract quote,
   etc.) — an external adversarial reviewer ("Fable," a review persona
   used throughout this project) flagged each one before it was trusted.
3. Cleared the PF>1/Sharpe>0.5 bar on the final "Stratified" cost variant
   for both indices.
4. A live, paper-only ("dry_run") execution path exists and is deployed
   (systemd timers on the VM), fixed at 1 lot per trade, gated by config
   flags that default to `enabled: false, dry_run: true`.
5. THIS WEEK (2026-09-24/25), for the first time, a real-capital
   equity-curve simulator was built (a generic cash+positions ledger,
   NOT the pooled per-trade stats) and run against real data. Result:
   **a ₹50,000 starting account is wiped to ~₹2,000 (97.7% max
   drawdown)**, while ₹55,000 — 10% more — compounds to over ₹500,000
   over the same window. The failure is a hard cliff, not a gradual
   slope: a single lot costs ₹7,000–25,000 depending on the index and
   premium level, and once an early loss drops the account below that
   floor, it is permanently locked out of the trades that would let it
   recover.
6. Also this week: a Kelly-criterion position-sizing analysis was built,
   with the fraction derived on a time-based 80% "mining" window and
   VALIDATED on the untouched 20% "holdout" window (not just fit and
   reported on the same data). Full Kelly (31% of equity per trade) has
   a positive holdout Sharpe but 74-93% drawdowns even out of sample —
   impractical. Quarter-to-half Kelly (roughly 8-16% of equity/trade) is
   the most defensible policy found, with ₹100,000-500,000 as a
   practical starting capital range. ₹50,000 has no viable policy among
   any of the four sizing rules tested.
7. **Two separate live-data pre-registered gates still block any real
   capital decision** regardless of the above: a stop-out cost probe
   (needs ≥20 real exit samples AND ≥4 weeks of live data collection,
   earliest possible check 2026-10-01) and, for the entry-filtered
   variant (18b), a completely separate 8-week/20-trade prospective
   gate not due until 2026-11-17.

## 4. The process gap, stated plainly

The PF>1/Sharpe>0.5 screen was computed on **pooled, unweighted
per-trade returns** — literally summing/averaging each trade's own
percentage return, with no capital compounding, no position sizing
model, and (until 2026-09-24) a hardcoded, wrong annualization constant.
This is fine as a CHEAP FIRST FILTER — most of the ~20 candidates in
section 2 failed it immediately and correctly, saving further build cost
on things with no real signal at all.

**The gap: nothing in this project's process required building the
real-capital equity-curve/position-sizing validation (section 3, step 5)
as soon as a candidate first passed the cheap screen.** Candidate 11
passed in July. The real-capital validation approach used for candidate
18 was not invented until late September, and even then it was triggered
by an UNRELATED bug investigation (the Sharpe annualization fix), not by
a standing rule that says "any candidate that passes gets this treatment
immediately." The Darvas ATR-stop candidate passed its own screen on
2026-09-24 and, as of this document, still has NOT had this treatment
applied — it is the immediate next candidate that needs it.

**Concretely, what pooled PF/Sharpe cannot tell you, that this week's
work exposed for real**: whether a real starting capital survives at
all (the ₹50k cliff), what position-sizing policy is actually safe to
use, what the realistic drawdown in currency terms is, and what capital
efficiency looks like (every capital tier above the cliff earned the
IDENTICAL absolute profit under fixed-lot sizing, because surplus
capital sat completely idle — a fact invisible in any pooled percentage
statistic).

## 5. Current state / what's in flight

- Candidate 18: capital-readiness analysis DONE (this week). Real
  deployment blocked by the stop-out probe gate (~2026-10-01 earliest)
  and by the fact the live executor code still hardcodes fixed 1-lot
  sizing, not the validated Kelly-fraction sizing.
- Candidate 18b: no capital-readiness work started; own statistical
  verdict not due until 2026-11-17 regardless.
- Darvas ATR-stop: passed its screen 2026-09-24, capital-readiness work
  NOT YET DONE — this is the next scoped piece of work.
- Candidate 11 (momentum turnover): live paper-only, no verdict possible
  before ~2027 Q3 under its own pre-registered walk-forward rule.
- Every other candidate in section 2 is closed/failed/shelved.
- No strategy has ever traded real money.

## 6. What we're asking for

An outside, independent read on:
1. Whether the overall two-stage structure (cheap PF/Sharpe screen, then
   a real-capital equity-curve/position-sizing/drawdown validation
   before any capital decision) is the right shape for this kind of
   project, or whether it's over-engineered relative to the goal of
   actually deploying a working strategy.
2. What the RIGHT standard metric set is for the second stage (this
   project is currently considering adding Sharpe-on-real-NAV, Sortino,
   Calmar/MAR, max-drawdown-duration, and Ulcer Index to the equity-curve
   output — is that the right set, over-built, or missing something
   institutions actually use).
3. Given ~11 weeks and ~20+ candidates producing exactly ZERO deployed
   capital, whether the process itself (heavy use of mining/holdout
   splits, an adversarial reviewer role, pre-registered stopping rules,
   "do not peek" gates on live data collection) is appropriately
   rigorous for a single-operator retail-scale project, or whether it is
   mismatched to the actual goal and stakes involved, and what a better-
   calibrated process looks like.
4. Concrete next steps to get candidate 18 (the most validated candidate)
   to an actual real-capital decision as fast as is responsible, given
   its two remaining gates and the sizing-policy implementation gap in
   its live executor.
