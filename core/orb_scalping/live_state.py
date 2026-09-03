"""
QuantOS — ORB Options Scalping Live State (candidate 18, zero-capital spread probe)
─────────────────────────────────────────────────────────────────────────
Read-only. Reconstructs "where would today's ORB trade be right now" from
TODAY's already-closed 5-minute candles, for
scripts/probe_orb_scalping_stopout_spreads.py — the event-triggered
spread probe named in the 2026-09-03 handoff
([[quantos_orb_options_scalping_status]]). No orders, no capital.

core.orb_scalping.signal.simulate_day() is a pure function built for a
COMPLETE day's candles known in advance. Fed a partial, still-growing
day, its "no more candles left" fallback reports exit_reason=
"session_flatten" even though the real session hasn't reached
flatten_time yet — it would misreport an OPEN position as a closed
trade. This module is a live-shaped SIBLING, not a duplicate: it reuses
signal.py's constants and its trail_arm_level() arithmetic directly
(single source of truth for the trailing-stop formula) and replays the
exact same opening-range/breakout/arm/trail rules in the exact same
order, but stops "as of now" instead of assuming the day is over.
tests/unit/test_orb_live_state.py proves this by replaying real
historical days incrementally through here and checking the final state
agrees with simulate_day()'s own verdict on the same day.

Deliberately excluded and NOT reimplemented here: reconstruct_premium()'s
Black-Scholes premium path (core/orb_scalping/premium.py). This module's
caller has REAL live option quotes available (the same
broker.get_option_chain() call scripts/probe_orb_scalping_real_spreads.py
already uses) — it captures the real premium at entry rather than a
theoretical one. More accurate than BS reconstruction, and it's the whole
reason a live probe is worth building over another backtest cost variant.

Close-only discipline (unchanged from signal.py): the opening range, the
breakout, the arm check, and the trailing-stop recompute are all decided
on a candle's CLOSE, never on an in-progress bar — callers must pass only
already-closed candles. Checking a resting stop level against live LTP
BETWEEN candle closes is the live probe's job (in the calling script),
not this module's — this module only ever reports the stop level as of
the last closed candle, exactly like the backtest's own "no intrabar
lookahead" convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from core.brokers.base import OHLCV
from core.orb_scalping.signal import (
    OPENING_RANGE_CANDLES,
    SESSION_FLATTEN_UTC,
    TRAIL_LOOKBACK_CANDLES,
    trail_arm_level,
)


@dataclass(frozen=True)
class LiveState:
    # "forming_range"   -- fewer than OPENING_RANGE_CANDLES+1 candles closed yet
    # "no_breakout_yet" -- range known, no breakout close seen so far today
    # "pending_entry"   -- breakout closed; backtest semantics enter at the
    #                      NEXT candle's open, which hasn't printed yet
    # "in_position"     -- entered, no stop hit by any closed candle so far
    # "flattened"       -- a closed candle already crossed current_stop, or
    #                      flatten_time has been reached with the position
    #                      still open (index-level exit only -- premium
    #                      stop is not this module's concern, see docstring)
    status: str
    direction: Optional[str] = None        # "CALL" | "PUT"
    entry_price: Optional[float] = None    # index level
    entry_index: Optional[int] = None      # position within day_candles_so_far
    current_stop: Optional[float] = None   # index points, as of the last closed candle
    armed: bool = False
    range_high: Optional[float] = None
    range_low: Optional[float] = None
    # Only set when status=="flattened" -- "stop" | "trailing_stop" | the
    # index-level "session_flatten" (signal.py's own vocabulary). Callers
    # MUST check this before logging a stop-out spread sample: a plain
    # session_flatten with no stop ever touched is an ordinary end-of-day
    # close, not a stop-out -- logging it would contaminate the exact
    # measurement this probe exists to make with the same "calm moment,
    # not a stop-out moment" contamination the fixed-clock probe already
    # has.
    exit_reason: Optional[str] = None


def compute_live_state(day_candles_so_far: list[OHLCV],
                        flatten_time: time = SESSION_FLATTEN_UTC) -> LiveState:
    """`day_candles_so_far`: TODAY's 5-minute candles from session open
    through the most recently CLOSED candle, ascending, already validated
    by the caller — never include a still-forming candle."""
    n = len(day_candles_so_far)
    if n <= OPENING_RANGE_CANDLES:
        return LiveState(status="forming_range")

    range_candles = day_candles_so_far[:OPENING_RANGE_CANDLES]
    range_high = max(c.high for c in range_candles)
    range_low = min(c.low for c in range_candles)
    range_width = range_high - range_low

    pending_direction: Optional[str] = None
    direction: Optional[str] = None
    entry_index = entry_price = stop = None
    armed = False

    for t in range(OPENING_RANGE_CANDLES, n):
        candle = day_candles_so_far[t]
        flatten_now = candle.timestamp.time() >= flatten_time

        if direction is not None:
            hit_stop = (candle.low <= stop if direction == "CALL"
                        else candle.high >= stop)
            if hit_stop:
                return LiveState(
                    status="flattened", direction=direction,
                    entry_price=entry_price, entry_index=entry_index,
                    current_stop=stop, armed=armed,
                    range_high=range_high, range_low=range_low,
                    exit_reason="trailing_stop" if armed else "stop",
                )
            if not armed:
                arm_level = trail_arm_level(direction, entry_price, range_width)
                favorable = (candle.close >= arm_level if direction == "CALL"
                             else candle.close <= arm_level)
                if favorable:
                    armed = True
            if armed:
                lookback_start = max(entry_index + 1, t - TRAIL_LOOKBACK_CANDLES + 1)
                lookback = day_candles_so_far[lookback_start:t + 1]
                if direction == "CALL":
                    stop = max(stop, min(c.low for c in lookback))
                else:
                    stop = min(stop, max(c.high for c in lookback))
            if flatten_now:
                return LiveState(
                    status="flattened", direction=direction,
                    entry_price=entry_price, entry_index=entry_index,
                    current_stop=stop, armed=armed,
                    range_high=range_high, range_low=range_low,
                    exit_reason="session_flatten",
                )
            continue

        if pending_direction is not None:
            direction = pending_direction
            entry_index = t
            entry_price = candle.open
            stop = range_low if direction == "CALL" else range_high
            armed = False
            pending_direction = None
            continue

        if not flatten_now:
            if candle.close > range_high:
                pending_direction = "CALL"
            elif candle.close < range_low:
                pending_direction = "PUT"

    if direction is not None:
        return LiveState(
            status="in_position", direction=direction,
            entry_price=entry_price, entry_index=entry_index,
            current_stop=stop, armed=armed,
            range_high=range_high, range_low=range_low,
        )
    if pending_direction is not None:
        return LiveState(status="pending_entry", direction=pending_direction,
                          range_high=range_high, range_low=range_low)
    return LiveState(status="no_breakout_yet", range_high=range_high, range_low=range_low)
