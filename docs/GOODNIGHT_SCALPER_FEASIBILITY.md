# "Good Night" Open-Price Stock-Options Scalper (candidate 20) — Feasibility Probe, 2026-09-03

Pre-methodology feasibility check for a proposed candidate: an
Open==Low / Open==High / cross-back-through-open signal on individual
Nifty200 Momentum 30 stock options, entered 09:15:30-09:18:00 IST,
exited at +10%/-15% premium or 09:30:00 IST flatten, per-symbol
"Good Night" lock after any exit. Extracted from an externally-sourced
strategy prompt (attributed to "Rajesh Jain", unverifiable — evaluated on
substance, not authority, same standing practice as every other
externally-sourced idea this project has taken in). Universe: NSE's
published NIFTY200 Momentum 30 index, current constituents
(`agent/universe_nifty200momentum30.txt`) used as a fixed backtest
universe — accepted survivorship-bias caveat, same class of limitation
the closed index-reconstitution candidate ran into.

Probe script: `scripts/probe_goodnight_scalper_feasibility.py`. First run
hit Fyers' rate limit almost immediately with zero throttling between
~30 symbols' worth of sequential calls — fixed with the same
throttle+retry-with-backoff discipline `fetch_chunked_intraday` already
uses elsewhere in this codebase, tuned slower after seeing how tight the
real limit is. All numbers below are from the corrected run.

## 1. 1-minute historical depth — BETTER than expected

All 30 symbols returned real 1-minute candles at every probed anchor up
to **70 days back** (the ceiling of the probed ladder, which was
deliberately tightened around candidate 18's own ~28-29 day index wall —
that assumption was wrong for individual stocks). The true wall is
**unconfirmed beyond 70 days** — worth a follow-up probe with a wider
ladder before locking the backtest window, but this is unambiguously
better news than the index-level precedent suggested, and removes what
looked like the single biggest a priori risk.

## 2. Open==Low / Open==High real hit-rate — encouraging

Across 30 symbols × 8 trading days each (240 symbol-days, last 10
calendar days): **24 exact Open==Low matches, 56 exact Open==High
matches** — a combined ~33% of symbol-days produce at least one exact
tick-level match on Setup A/B alone, before even considering Setup C
(the cross-back-through-open pattern). "Near-miss" (within 0.05% of open)
counts were mostly 0-1 per symbol, meaning the exact match isn't a
narrow miss away from being far more common — it's genuinely this
common on its own. At a ~33% daily rate across 30 stocks, that implies
roughly 10 qualifying setups/day across the universe, which — combined
with the per-symbol lock (each stock can trade at most once/day,
independently) — gives a plausible **~700+ trade-opportunity sample**
just within the confirmed 70-day window. Better statistical power at the
outset than most candidates in this project's history started with.

## 3. Stock-option expiry structure — monthly-only, floor rarely binds

All 30 symbols: 3 expiries listed, ~27-28 day gaps, monthly cadence
(unlike NIFTY's weekly cadence). The spec's own "reject if DTE<2" floor
would only ever bind ~1-2 days per month per stock — a materially
different dynamic than NIFTY's ~40% weekly-roll rate in candidate 18,
worth stating plainly in any methodology doc rather than assuming it
transfers.

## 4. Live ATM spread sample — the real concern

Mid-session read (NOT the 09:15-09:18 IST entry window — market was
already ~2 hours into the session when this ran; disclosed the same way
every prior single-snapshot spread read in this project has been), 6
symbols:

| Symbol | CE spread_pct_of_mid | PE spread_pct_of_mid |
|---|---|---|
| ABB | 1.05% | 1.48% |
| ADANIENSOL | 0.83% | 1.38% |
| ADANIGREEN | 1.14% | 1.22% |
| ADANIPOWER | 0.73% | 0.92% |
| ABCAPITAL | 1.84% | 2.06% |
| BSE | 0.75% | 0.75% |

**0.73%-2.06% round-trip spread, mid-session, on liquid Nifty200
Momentum 30 names.** For comparison, candidate 18's locked-final
Stratified cost model uses ~11-18bps (0.11%-0.18%) round-trip for
NIFTY/BankNifty index options — these individual stock options show
**5-15x wider spreads**, mid-day, before even considering the thinner
liquidity typical of the first few minutes after open (the strategy's
actual entry window). A strategy targeting +10%/stop -15% on premium
could see spread alone consume a meaningful fraction of its entire
theoretical edge per trade — the same failure mode that killed candidate
15 and nearly killed candidate 18 (a real signal that dies to real
option-market friction). This is not disqualifying on its own (a
proper at-open reading could differ either direction), but it is the
single most decision-relevant number this probe produced, and it wasn't
even measured at the moment that matters most.

## Bottom line

Two of four checks (depth, hit-rate) came back better than the working
assumption; one (expiry structure) is just a disclosed structural
difference from NIFTY; one (liquidity) is a real yellow flag that needs
a measurement taken AT the actual 09:15-09:18 IST entry window — not
mid-session — before any pre-registered methodology doc should lock a
backtest design around this strategy being viable. Next trading day's
market open is the earliest that specific reading can be taken.
