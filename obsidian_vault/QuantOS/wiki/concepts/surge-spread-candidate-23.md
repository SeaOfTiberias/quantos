---
title: Surge Option Spreads (Candidate 23)
compiled: 2026-10-15
tags:
  - wiki/concept
  - wiki/strategy
  - strategy/failed
strategy_id: surge-spread-candidate-23
candidate: "23"
family: momentum
instrument: stock-options
status: closed
verdict: FAIL
first_tested: 2026-10-15
verdict_date: 2026-10-15
profit_factor: 0.92
sharpe: -0.10
trades: 1748
bar: "Stage 2: strike pair picked on mining (highest Stressed Sharpe, ≥ 100 trades, PF > 1), then holdout Stressed PF > 1 and Sharpe > 0.5 on ≥ 30 trades. Numbers: best mining structure L0W2 under Stressed costs"
headline: "Stage 1 found real continuation after +5% surges below the 52-week high, but bull call spreads on closing option prices lost it to bid-ask: no strike pair cleared PF 1 in 2020–24 at a realistic spread cost."
next_gate_date:
quantos:
  layer: wiki
  generated: true
  compiled_from: 2026-10-15-quantos-strategy-specification-single-day-stock-surge-bear-c, 2026-10-15-candidate-23-stage-1-does-a-5-stock-surge-continue-or-fade-m, 2026-10-15-candidate-23-stage-1-5-surge-direction-results, 2026-10-15-candidate-23-stage-2-bull-call-spreads-on-non-52-week-high-s, 2026-10-15-candidate-23-stage-2-bull-call-spreads-on-non-52-week-high-s-2
---

# Surge Option Spreads (Candidate 23)

> [!abstract] Compiled page
> Written from `[[2026-10-15-quantos-strategy-specification-single-day-stock-surge-bear-c]]`, `[[2026-10-15-candidate-23-stage-1-does-a-5-stock-surge-continue-or-fade-m]]` and `[[2026-10-15-candidate-23-stage-1-5-surge-direction-results]]` on 2026-10-15. Context and retrieval only — rules in this layer never execute.

## Definition

The user's draft proposes fading +5% one-day surges in F&O stocks with a bear call spread (sell an OTM call around 20–30 delta, buy a higher one around 10–15 delta). It adds resistance, IV-rank and F&O-ban gates `[[2026-10-15-quantos-strategy-specification-single-day-stock-surge-bear-c]]`. Reviewing it against a real trade (Persistent, 2026-10-15, a 6100/6300 bull call spread) showed one trigger hiding **two strategies**: continuation (bull call spread) and reversal (bear call spread). Stage 1 asks which way the stock goes next, before any option pricing `[[2026-10-15-candidate-23-stage-1-does-a-5-stock-surge-continue-or-fade-m]]`.

## Stage 1 mechanics

- **Data**: roll-adjusted near-month stock futures for all 347 F&O symbols, 2019–2026, so the universe is point-in-time.
- **Trigger and entry**: a +5% close-to-close day, entered at that day's close. A 10-day cooldown per symbol.
- **Outcome**: X(5), the 5-day return minus the equal-weighted F&O universe, with t-stats clustered by event date.
- **Conditions** (each binary, fixed in advance): results day, fresh 52-week closing high, surge ≥ 3σ of the prior 20 days, broad market rally (≥ +1%), and an already-extended stock (+10% over the prior 20 days).
- **Split**: 80/20 by time. A subset becomes a branch only if mining |t| ≥ 2 and the holdout confirms with the same sign at t ≥ 1.5.

`[[2026-10-15-candidate-23-stage-1-does-a-5-stock-surge-continue-or-fade-m]]`

## Stage 1 result: PASS (one branch)

From 3,206 events (cutoff 2025-01-07) `[[2026-10-15-candidate-23-stage-1-5-surge-direction-results]]`:

| Subset | Mining X(5), t | Holdout X(5), t | Result |
|---|---|---|---|
| All surges | +0.34%, 1.77 | +0.84%, 2.83 | not a branch (mining t < 2) |
| **Not a fresh 52-week high** | **+0.49%, 2.20** | **+0.98%, 3.02** | **branch: continuation** |
| Fresh 52-week high | −0.10%, −0.41 | +0.26%, 0.54 | no drift either way |
| Results day | +0.33%, 1.04 | +0.46%, 1.36 | not a branch |

- **No subset showed reversal.** The bear-call fade the draft was written for has no support in this data.
- **The continuation is skewed.** In the passing branch, the median X(5) is −0.13% while the mean is +0.6%. The average comes from a minority of strong follow-throughs, and a capped spread only partly collects that tail.
- **Payoff-relevant probabilities** (raw 8-day return, passing branch): P(≥ +4%) 32.2%, P(≥ +7%) 18.8%, against 22.8% and 11.1% for an ordinary stock-day. The option market also prices a surge day's higher volatility, so beating the ordinary-day baseline is not yet an edge over option prices.
- **Weak years**: mean X(5) was negative in 2022 (−0.18%) and 2024 (−0.11%).
- **Multiple testing**: 10 subsets were tested, so about one false mining pass is expected by chance. The passing branch only just cleared mining (t 2.20); the holdout confirmation (t 3.02) is what carries it.

## Stage 2 result: FAIL (2026-10-15)

Bull call spreads on the 2,571 branch events, from bhavcopy closing option prices `[[2026-10-15-candidate-23-stage-2-bull-call-spreads-on-non-52-week-high-s]]`:

- **Mechanics**: entry at the surge-day close; exit at the close of min(t+8, the day before expiry); the nearest expiry with ≥ 5 trading days left.
- **Strike grid**: 16 structures (long leg ATM to 3 strikes OTM, width 1–4 strikes); both legs had to trade on the entry day.
- **Costs**: statutory costs throughout, plus bid-ask at 1% (Base) or 2% (Stressed) of each leg price per side.
- **Picker**: the strike pair was to be picked on mining only.

**No structure had Stressed PF > 1 on the 2020–24 mining set, so nothing was picked.** The best was L0W2 (ATM long, 2 strikes wide): 1,748 trades, PF 0.92, Sharpe −0.10. Before bid-ask, every structure was positive in mining, at PF 1.02–1.89 `[[2026-10-15-candidate-23-stage-2-bull-call-spreads-on-non-52-week-high-s-2]]`.

Post-run checks (not part of the verdict) `[[2026-10-15-candidate-23-stage-2-bull-call-spreads-on-non-52-week-high-s-2]]`:

- **Cost level**: the measured ATM stock-option spreads are about 1.7–3.1% round trip, so Base (2% round trip) is the realistic level. At Base, no structure reached a mining Sharpe of 0.5.
- **Data errors**: stale prints produced impossible exits (a spread worth more than its width) and tiny stale entry debits. Removing them (2,029 of 34,263 structure-trades) leaves no structure above PF 1 at Base in mining. The median return before bid-ask was negative for every structure checked.
- **Mechanism**: a spread pays bid-ask on the gross premium of both legs, four times, while risking only the net debit. Bid-ask alone was a median 6–12% of the debit per trade, more than the 5-day drift being captured.
- **2025–26 looked better** (wide structures PF 1.14–1.18 at Base), matching Stage 1's stronger holdout. Picking from the holdout is forbidden. Only new data could test it.

## What is still open

That prospective test is [[surge-spread-forward-23b]]: one structure (L2W4) fixed in advance, filled at live bid/ask on new surges only. The per-event expected-value strike picker (Stage 2b) was never reached, because no fixed structure survived costs. The draft's own design problems are listed in its review (a resistance gate that passes almost every surge, a sizing formula that risks 25% of NAV, a stop next to the max loss, and an entry window that conflicts with the time exit).

## Relation to other concepts

- Consistent with [[darvas-atr-stop-bucket-b]] (breakouts continue) and with the residual-momentum lean noted in [[statarb-residual-mean-reversion]]. The difference: here, *fresh* 52-week highs did not continue, while surges below a prior high did.
- Its option leg faces the same stock-option spread risk that sank [[goodnight-scalper-candidate-20]].
- The payoff shape of the bear call variant (frequent small wins, rare large losses) is the one that left [[vrp-short-strangle]] at Sharpe 0.09.
