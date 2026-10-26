---
title: Put Retest Context Review (Blind LLM Skip Rules)
compiled: 2026-10-26
tags:
  - wiki/concept
  - wiki/strategy
strategy_id: put-retest-context-review
candidate: "context review 2026-10-26"
family: event-drift
instrument: stock-futures
status: open
verdict: MIXED
first_tested: 2026-10-26
verdict_date: 2026-10-26
profit_factor: 1.39
sharpe:
trades: 552
bar: "held-out half: skips >= 30, keeps >= half, kept mean > unfiltered, Welch t (kept - skipped) >= 2.0"
headline: "A blind Claude review proposed two skip rules for the put retest; 'skip if more than 45 trading days since the last results' held up on unseen trades (kept +0.38% vs +0.25%, PF 1.39 vs 1.24, t 2.1); 'skip low VIX' did not."
next_gate: "User go-ahead to show the flag on screener put picks; live outcome log judges it before it may drop picks"
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-26-put-retest-h1-can-context-remove-the-losing-trades-pre-regis, 2026-10-26-put-retest-context-review-claude-opus-5-5-2026-10-26, 2026-10-26-put-retest-context-review-results-2026-10-26
---

# Put Retest Context Review (Blind LLM Skip Rules)

> [!abstract] Compiled page
> Written from `[[2026-10-26-put-retest-h1-can-context-remove-the-losing-trades-pre-regis]]`, `[[2026-10-26-put-retest-context-review-claude-opus-5-5-2026-10-26]]` and `[[2026-10-26-put-retest-context-review-results-2026-10-26]]` on 2026-10-26. Context and retrieval only — rules in this layer never execute.

## Definition

The user asked whether context, as in the HDFC Bank, NHPC and LICI discussions (results dates, market, sector), could remove the losing 30% of the best tested strategy. The register held only one clean edge: the [[fno-screener]] put H1 retest (69% win, +0.34% per trade, 1,672 trades). Claude Opus 5.5 reviewed its first half blind and proposed skip rules, which were then judged on the second half.

## Mechanics

- **Context:** 27 features known at entry: days to and since the stock's results (NSE board meetings), NIFTY trend, India VIX, NSE sector and sector trend, the stock's recent returns and distance from its 52-week low, breakdown depth, OI label, option IV, fill timing, weekday and expiry distance.
- **Blind review:** the model saw the first half (900 trades, signals before 2026-03-27) with symbols and dates removed, plus win-rate tables by feature. It returned at most 3 rules.
- **Test:** the rules were fixed, then tested on the 772 held-out trades. The bar was set before the call.

## Verdict

**MIXED: one rule passes, one fails** `[[2026-10-26-put-retest-context-review-results-2026-10-26]]`.

| Held-out half | Kept | Kept win / mean / PF | Skipped | Skipped win / mean / PF | t | |
|---|---|---|---|---|---|---|
| Unfiltered | 772 | 70% / +0.25% / 1.24 | | | | |
| Skip if > 45 trading days since last results | 552 | 72% / +0.38% / 1.39 | 220 | 63% / −0.07% / 0.94 | +2.11 | **PASS** |
| Skip if India VIX < 11 | 755 | 69% / +0.23% / 1.22 | 17 | 88% / +1.13% / 4.67 | −2.41 | FAIL |
| Both | 536 | 72% / +0.36% / 1.36 | 236 | 65% / +0.01% / 1.00 | +1.72 | FAIL |

- **Stale results:** it worked the same way in both halves (skipped trades −0.03% in the first, −0.07% in the second). 188 of the 220 skipped held-out trades also had results due within 15 trading days, so in practice the rule reads: don't take the retest short in the weeks before results. Its t of 2.1 only just clears the bar, from a single test.
- **Low VIX:** this was the strongest pattern in the first half, but it was specific to that period. VIX was rarely under 11 in the second half, and those 17 trades won.
- **Ideas the model rejected from its half, before testing:** "results coming up" in the narrow sense, "a market rally fighting the short", "already far below its range" (the reverse held: trades near the 52-week low did best), and "a crowded short".

## Relation to other concepts

The screener already shows a results-date warning on put picks when results fall within 10 sessions (fa75c56). This finding argues for a wider window, shown as a flag first. Compare [[fno-screener-cci-sma-filters]], where trend indicators added nothing.
