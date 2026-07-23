"""
QuantOS — VRP Phase 2: Entry-Cycle + Strike Reconstruction
─────────────────────────────────────────────────────────────
Implements docs/VRP_METHODOLOGY.md's entry/strike rules against the cached
bhavcopy data from Phase 1 (core/options/vrp/bhavcopy.py), with no
lookahead: every decision made "as of" an entry date uses only that date's
own bhavcopy rows.

Spot/forward estimate: neither bhavcopy schema reliably carries a clean
spot price across the whole window (new-format's UndrlygPric is present
from 2024-01-01 onward; the legacy schema, used through 2023-12-29, has no
spot column at all). Rather than switch estimation METHOD at the format
cutover -- which would silently change the strategy's own strike-selection
logic partway through the backtest -- this module derives a synthetic
forward price via put-call parity from that day's own option prices,
uniformly across the whole window. This is the same principle CBOE's VIX
methodology uses to locate its at-the-money anchor strike, not a bespoke
approximation invented for this project.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from typing import Optional

from core.options.greeks import compute_greeks, implied_volatility
from core.options.models import OptionType
from core.options.vrp.bhavcopy import BhavcopyOptionRow

# Pre-committed in docs/VRP_METHODOLOGY.md -- do not tune after seeing results.
TARGET_DELTA = 0.20
DELTA_TOLERANCE = 0.10    # accept a delta-selected strike only if |delta - 0.20| <= this
FALLBACK_OTM_PCT = 0.02   # fixed 2% OTM, used when delta selection is unreliable that day


def synthetic_forward(rows: list[BhavcopyOptionRow]) -> Optional[float]:
    """Put-call-parity forward estimate for one expiry on one day: for every
    strike with both a call and a put priced, C - P ~= F - K, so
    F ~= K + (C - P). Median across strikes damps illiquid-strike noise.
    Returns None if fewer than two strikes have both legs priced (too
    illiquid to trust)."""
    by_strike: dict[float, dict[OptionType, BhavcopyOptionRow]] = {}
    for r in rows:
        by_strike.setdefault(r.strike, {})[r.option_type] = r

    estimates = []
    for k, legs in by_strike.items():
        ce, pe = legs.get(OptionType.CALL), legs.get(OptionType.PUT)
        if ce and pe and ce.close > 0 and pe.close > 0:
            estimates.append(k + (ce.close - pe.close))

    if len(estimates) < 2:
        return None
    return statistics.median(estimates)


# ─── Entry cycles ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EntryCycle:
    entry_date:  date
    expiry_date: date
    dte:         int   # calendar days, entry_date -> expiry_date


def build_entry_cycles(expiries_by_date: dict[date, set]) -> list[EntryCycle]:
    """Immediate-roll entry rule from docs/VRP_METHODOLOGY.md: enter the
    trading day immediately after the prior cycle's expiry, into whichever
    unexpired expiry is nearest that day. `expiries_by_date` maps every
    cached trading day to the set of expiry dates present in that day's
    bhavcopy -- pure function, no I/O, so it's independently testable
    against a hand-built date map."""
    ordered = sorted(expiries_by_date)
    if not ordered:
        return []

    cycles: list[EntryCycle] = []
    entry_date = ordered[0]

    while entry_date <= ordered[-1]:
        unexpired = sorted(e for e in expiries_by_date.get(entry_date, ()) if e > entry_date)
        if not unexpired:
            later = [d for d in ordered if d > entry_date]
            if not later:
                break
            entry_date = later[0]
            continue

        expiry = unexpired[0]
        cycles.append(EntryCycle(
            entry_date=entry_date, expiry_date=expiry, dte=(expiry - entry_date).days,
        ))
        later = [d for d in ordered if d > expiry]
        if not later:
            break
        entry_date = later[0]

    return cycles


# ─── Strike selection ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StrikeSelection:
    strike: float
    row:    BhavcopyOptionRow
    iv:     float
    delta:  float
    method: str   # "delta" | "fallback_pct_otm"


def _select_leg(
    rows_by_strike: dict[float, BhavcopyOptionRow], spot: float, dte: int, option_type: OptionType,
) -> Optional[StrikeSelection]:
    is_call = option_type == OptionType.CALL
    target_delta = TARGET_DELTA if is_call else -TARGET_DELTA

    candidates = []
    for strike, row in rows_by_strike.items():
        is_otm = (strike > spot) if is_call else (strike < spot)
        if not is_otm or row.close <= 0:
            continue
        iv = implied_volatility(row.close, spot, strike, dte, option_type)
        delta = compute_greeks(spot, strike, dte, iv, option_type).delta
        candidates.append((abs(delta - target_delta), strike, row, iv, delta))

    if candidates:
        candidates.sort(key=lambda c: c[0])
        gap, strike, row, iv, delta = candidates[0]
        if gap <= DELTA_TOLERANCE:
            return StrikeSelection(strike=strike, row=row, iv=iv, delta=delta, method="delta")

    # Fallback: nearest listed, priced strike to the fixed %-OTM target.
    target_price = spot * (1 + FALLBACK_OTM_PCT) if is_call else spot * (1 - FALLBACK_OTM_PCT)
    otm_strikes = {
        k: r for k, r in rows_by_strike.items()
        if ((k > spot) if is_call else (k < spot)) and r.close > 0
    }
    if not otm_strikes:
        return None
    strike = min(otm_strikes, key=lambda k: abs(k - target_price))
    row = otm_strikes[strike]
    iv = implied_volatility(row.close, spot, strike, dte, option_type)
    delta = compute_greeks(spot, strike, dte, iv, option_type).delta
    return StrikeSelection(strike=strike, row=row, iv=iv, delta=delta, method="fallback_pct_otm")


@dataclass(frozen=True)
class StrangleSelection:
    entry_date:    date
    expiry_date:   date
    dte:           int
    spot_estimate: float
    call:          StrikeSelection
    put:           StrikeSelection


def select_strangle(
    rows: list[BhavcopyOptionRow], entry_date: date, expiry_date: date, dte: int,
) -> Optional[StrangleSelection]:
    """Reconstruct one cycle's short strangle from that entry date's own
    bhavcopy rows only. Returns None if the expiry isn't present that day,
    the forward can't be estimated, or either leg has no valid OTM strike
    to select (all real "this cycle can't be traded" conditions, not bugs)."""
    expiry_rows = [r for r in rows if r.expiry == expiry_date]
    if not expiry_rows:
        return None

    spot = synthetic_forward(expiry_rows)
    if spot is None:
        return None

    calls_by_strike = {r.strike: r for r in expiry_rows if r.option_type == OptionType.CALL}
    puts_by_strike = {r.strike: r for r in expiry_rows if r.option_type == OptionType.PUT}

    call_sel = _select_leg(calls_by_strike, spot, dte, OptionType.CALL)
    put_sel = _select_leg(puts_by_strike, spot, dte, OptionType.PUT)
    if call_sel is None or put_sel is None:
        return None

    return StrangleSelection(
        entry_date=entry_date, expiry_date=expiry_date, dte=dte,
        spot_estimate=spot, call=call_sel, put=put_sel,
    )
