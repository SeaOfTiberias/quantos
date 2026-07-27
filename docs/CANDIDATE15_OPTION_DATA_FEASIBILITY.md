# Candidate 15 (10:10 breakout) — Option Intraday Data Feasibility

**Verdict (2026-07-27): real historical intraday option premium data is NOT
fetchable from Fyers for any expired contract.** This blocks the "fetch real
option candles" data-sourcing path outright — candidate 15 must reconstruct
option premium via Black-Scholes from the index series + an IV proxy instead.

## Context

Candidate 15's design (see memory `quantos_1010_breakout_status`) needs two
series per trading day: the BankNifty index 5m series (signal + stop/target
trigger levels, already confirmed available back to 2021-05) and the specific
option contract's own intraday premium series (to mark realized P&L). This
probe answers whether the second series is obtainable from Fyers at all.

A prior attempt at this probe (2026-07-26) hit a real bug instead of getting
an answer: `core/brokers/fyers.py`'s `_fyers_symbol()` unconditionally
appended `"-EQ"` to any symbol not in its hardcoded index map, mangling an
already-fully-qualified Fyers option symbol (e.g. `"NSE:BANKNIFTY26JUL56700PE"`)
into garbage before it ever reached the API. That bug is now fixed (any
symbol already starting with `"NSE:"` passes through unchanged) — see
`core/brokers/fyers.py:73` and `tests/unit/test_fyers_broker.py`'s
`TestAlreadyQualifiedSymbolPassthrough`. Full test suite: 1176/1177 passing
(the 1 failure, `test_lists_only_future_or_today_expiries`, is a pre-existing
date-fixture rollover unrelated to this change — confirmed by reproducing it
identically on the pre-fix commit).

## Method

`scripts/probe_option_intraday_depth.py`. For each probe vintage, ground
truth (real expiry date, ATM strike, and the exact Fyers symbol string) comes
from NSE's own F&O bhavcopy (`core/options/vrp/bhavcopy.py`, the same
pipeline the VRP candidate used) — not hand-guessed expiry-day math. The
bhavcopy's `FinInstrmNm` column *is* the Fyers symbol format minus the
`"NSE:"` prefix, confirmed directly against a live download. This sidesteps
any ambiguity from the Thursday->Tuesday monthly-expiry-day rule change
(SEBI circular, see `docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md`) or
historical weekly-vs-monthly symbol formatting differences.

For each vintage, picked the nearest-expiry, ATM, actually-traded
(`TtlTradgVol > 0`) CE contract, then requested that exact contract's 5m
candles from Fyers across its own lifetime.

## Results

BankNifty monthly contracts, 1-30 months expired — **all 7 failed**,
Fyers error `-300 "Invalid symbol provided"`:

| months ago | ground-truth trade date | symbol | status |
|---|---|---|---|
| 1 | 2026-06-25 | NSE:BANKNIFTY26JUN58200CE | invalid symbol |
| 3 | 2026-04-28 | NSE:BANKNIFTY26APR55400CE | invalid symbol |
| 6 | 2026-01-28 | NSE:BANKNIFTY26FEB59600CE | invalid symbol |
| 12 | 2025-08-01 | NSE:BANKNIFTY25AUG55600CE | invalid symbol |
| 18 | 2025-02-01 | NSE:BANKNIFTY25FEB49500CE | invalid symbol |
| 24 | 2024-08-06 | NSE:BANKNIFTY2480749700CE | invalid symbol |
| 30 | 2024-02-08 | NSE:BANKNIFTY2421445000CE | invalid symbol |

Sanity checks to rule out a symbol-format or endpoint bug rather than a real
depth limit:

- **Still-live contract, same endpoint, same symbol convention**:
  `NSE:BANKNIFTY26JUL57100CE` (current ATM, expires 2026-07-28, i.e.
  tomorrow) — **succeeded**, 225 real 5m candles over the last 5 trading
  days. Confirms the fixed `_fyers_symbol()` path and the endpoint itself
  work correctly; the failures above are specific to expiry having already
  passed, not a formatting bug.
- **Most-recently-expired, most-liquid contract available**: real,
  bhavcopy-verified `NSE:NIFTY2672124200CE` (NIFTY weekly ATM, 48.8M volume
  traded, expired **6 days before this probe ran**, 2026-07-21) —
  **also failed**, same `-300 "Invalid symbol provided"`. This rules out
  "maybe there's a short data-retention grace period" — Fyers appears to
  drop an expired contract's symbol (and its history) from serviceability
  essentially immediately, not just for older/illiquid names.

## Conclusion

Fyers does not serve historical intraday candles for expired option
contracts, index or stock, regardless of recency (as little as 6 days) or
liquidity (as much as 48.8M contracts traded). This is a hard data-source
blocker for candidate 15's original design (mark realized P&L off the real
option's own intraday premium path).

**Path forward**: reconstruct the option premium path via Black-Scholes from
the BankNifty index 5m series (already confirmed available) + an implied-vol
proxy, rather than fetching real historical option candles — the fallback
already anticipated in the pre-probe design note (memory
`quantos_1010_breakout_status`). This needs its own IV-source decision before
methodology pre-registration proceeds (e.g. a fixed/regime-conditioned IV
level vs. a real historical India VIX-derived proxy) — not yet decided, next
step.
