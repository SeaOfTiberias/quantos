# NIFTY Option Skew — BankNifty Addendum, Pre-Committed 2026-07-25

Addendum to `docs/VOL_SKEW_METHODOLOGY.md`, not a revision of it — same pattern
as `docs/MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_METHODOLOGY.md`'s relationship
to its own original doc. The original NIFTY-only construction stands as
pre-registered; this doc extends it to a second underlying, BankNifty, before
either has been run.

## Why this is feasible without a new data pull — verified, not assumed

Checked the already-cached raw bhavcopy zip directly (`data_cache/nse_bhavcopy/raw/20260722.zip`)
before writing this: it contains **1044 BANKNIFTY index-option rows** for
that single day, alongside NIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50 — the
raw cache is whole-market F&O data, unfiltered (per
`core/options/vrp/bhavcopy.py`'s own docstring, "raw/{date}.zip — the
untouched bhavcopy zip, ALL underlyings"). `core/options/vrp/bhavcopy.py`'s
*parser* filters this down to NIFTY only when writing the parsed cache —
that filter is specific to that module's VRP scope and is not touched here.
Also confirmed: `UndrlygPric` (spot) is populated for BankNifty rows the
same way as NIFTY's, and the earliest already-cached raw zip checked
(2024-01-02) has BankNifty rows too, so the same 2024-01-01+ window applies.

**No new download is required** — all 737 already-cached raw zips have
BankNifty rows sitting in them unparsed. This addendum's harness reads the
raw cache directly with its own underlying-filtered parse (reusing
`fetch_raw()` for the cache/download step, not `core/options/vrp/bhavcopy.py`'s
NIFTY-only `_parse_new_format`), so `core/options/vrp/bhavcopy.py` and VRP's
own parsed NIFTY cache are both left untouched.

## What stays identical to the NIFTY construction

Every design choice in `docs/VOL_SKEW_METHODOLOGY.md` — 5% OTM target
strikes with 2pp tolerance, nearest expiry with DTE>=3, plain-difference
skew (put IV − call IV), the fallback-contamination guard, 20-day
trailing/forward realized vol, quintile bucketing, the monotonic Q1→Q5
pass bar, the 2024-01-01+ window, the mandatory VRP/straddle-CSV sequencing
ban. Applying the same fixed construction to a second underlying is a
generalization check, not a parameter change — nothing here is tuned
per-underlying.

## The one thing disclosed up front, not discovered after a result

**BankNifty currently trades monthly expiries only** (NSE discontinued its
weekly cycle — already known from `quantos_regime_signal_redesign_plan`'s
VRP-widening assessment, re-confirmed directly here: the nearest-expiry
list checked for 2026-07-22 was `2026-07-28, 2026-08-25, 2026-09-29, ...`,
roughly monthly spacing). So "nearest expiry with DTE>=3" will typically
resolve to an expiry several weeks out for BankNifty, versus NIFTY's
typical same-week or next-week resolution. This means BankNifty's skew
reading reflects a structurally longer-dated option chain than NIFTY's on
most days — a real difference between the two runs, reported as such, not
smoothed over by forcing a matched DTE band.

## Reporting — two separate verdicts, never pooled

NIFTY and BankNifty are run through the identical harness independently
and reported as **two separate quintile tables with two separate
pass/fail verdicts**. They are never pooled into one sample, and the
headline is never "whichever one separated better" — both get reported,
regardless of outcome, same discipline as reporting all five buckets even
when only the endpoints look interesting.

## What would make this untrustworthy after the fact

- Loosening the moneyness tolerance or DTE minimum specifically for
  BankNifty to force more days into the sample after seeing a thin count.
- Reporting only whichever of NIFTY/BankNifty shows cleaner separation.
- Widening to FINNIFTY, MIDCPNIFTY, or NIFTYNXT50 in the same pass "since
  the raw data's already there" — those are out of scope here; if wanted,
  they need their own explicitly-flagged addendum, not a silent scope
  creep on this one.
