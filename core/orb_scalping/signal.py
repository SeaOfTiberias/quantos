"""
QuantOS — Opening-Range-Breakout Options Scalping Signal (candidate 18)
─────────────────────────────────────────────────────────────────────────
Pure (I/O-free) opening-range breakout detection + INDEX-level trailing-
stop trade simulation per docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md, fixed
BEFORE this module's result was ever run. All prices here are INDEX points
(NIFTY or BankNifty — identical logic, called independently per index) —
option premium reconstruction and the secondary 25%-premium stop happen
one layer up (core/orb_scalping/premium.py), never in this module, same
separation of concerns as candidate 15's core/breakout1010/signal.py +
premium.py split.

Same-candle stop/arm ambiguity: if a single candle's range would satisfy
both the (pre-update) stop and the trailing-arm trigger, the stop is
assumed to have been hit first (conservative, no intrabar sequencing
available) — same convention as candidate 15 and
core/trend/dow_structure.py. The trailing stop is only ever recomputed
from a candle's CLOSE, applied to candles strictly after it — never
checked retroactively against the same candle that computed it (no
lookahead).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from core.brokers.base import OHLCV

OPENING_RANGE_CANDLES = 3        # first three 5-minute candles: 09:15-09:30
TRAIL_LOOKBACK_CANDLES = 3        # prior-3-candle swing low/high once armed
SESSION_FLATTEN_UTC = time(9, 50)     # 15:20 IST


@dataclass(frozen=True)
class IndexTrade:
    direction:      str     # "CALL" or "PUT"
    entry_index:    int     # position within the day's candle list
    entry_price:    float   # index level at entry
    exit_index:     int
    exit_price:     float   # index level at exit
    initial_stop:   float   # opposite side of the opening range
    exit_reason:    str     # "stop" | "trailing_stop" | "session_flatten"


def simulate_day(day_candles: list[OHLCV],
                  flatten_time: time = SESSION_FLATTEN_UTC) -> Optional[IndexTrade]:
    """Simulate one trading day's ORB per
    docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. No cross-day state — caller
    passes exactly one day's 5-minute candles, already sorted ascending by
    timestamp. Returns None if the day has fewer than OPENING_RANGE_CANDLES
    + 1 candles (a shortened session — skipped, not approximated) or if no
    breakout occurs by session flatten. One trade per day, first breakout
    only, execution at the next candle's open after the signal candle's
    close (no same-bar execution)."""
    n = len(day_candles)
    if n <= OPENING_RANGE_CANDLES:
        return None

    range_candles = day_candles[:OPENING_RANGE_CANDLES]
    range_high = max(c.high for c in range_candles)
    range_low = min(c.low for c in range_candles)
    range_width = range_high - range_low

    pending_direction: Optional[str] = None

    for t in range(OPENING_RANGE_CANDLES, n):
        candle = day_candles[t]
        flatten_now = candle.timestamp.time() >= flatten_time

        # 1) Execute a pending entry queued from the previous candle's signal.
        if pending_direction is not None:
            direction = pending_direction
            entry_price = candle.open
            initial_stop = range_low if direction == "CALL" else range_high
            return _manage_position(
                day_candles, entry_index=t, entry_price=entry_price,
                direction=direction, initial_stop=initial_stop,
                range_width=range_width, flatten_time=flatten_time,
            )

        # 2) Look for the day's first breakout, on candle close.
        if not flatten_now:
            if candle.close > range_high:
                pending_direction = "CALL"
            elif candle.close < range_low:
                pending_direction = "PUT"

    return None


def _trail_arm_level(direction: str, entry_price: float, range_width: float) -> float:
    return entry_price + range_width if direction == "CALL" else entry_price - range_width


def _manage_position(
    day_candles: list[OHLCV], entry_index: int, entry_price: float,
    direction: str, initial_stop: float, range_width: float, flatten_time: time,
) -> IndexTrade:
    """Walk forward from the entry candle: check the current stop, arm
    trailing once price has moved one range-width in favor (on close), then
    recompute the trailing stop from the prior TRAIL_LOOKBACK_CANDLES
    candles (never loosening it), flattening at session close if nothing
    else has triggered."""
    n = len(day_candles)
    stop = initial_stop
    armed = False
    arm_level = _trail_arm_level(direction, entry_price, range_width)

    for t in range(entry_index + 1, n):
        candle = day_candles[t]

        hit_stop = candle.low <= stop if direction == "CALL" else candle.high >= stop
        if hit_stop:
            return IndexTrade(
                direction=direction, entry_index=entry_index, entry_price=entry_price,
                exit_index=t, exit_price=stop, initial_stop=initial_stop,
                exit_reason="trailing_stop" if armed else "stop",
            )

        if not armed:
            favorable = candle.close >= arm_level if direction == "CALL" else candle.close <= arm_level
            if favorable:
                armed = True

        if armed:
            lookback_start = max(entry_index + 1, t - TRAIL_LOOKBACK_CANDLES + 1)
            lookback = day_candles[lookback_start:t + 1]
            if direction == "CALL":
                stop = max(stop, min(c.low for c in lookback))
            else:
                stop = min(stop, max(c.high for c in lookback))

        if candle.timestamp.time() >= flatten_time:
            return IndexTrade(
                direction=direction, entry_index=entry_index, entry_price=entry_price,
                exit_index=t, exit_price=candle.close, initial_stop=initial_stop,
                exit_reason="session_flatten",
            )

    # Safety net: data ends before any candle reached flatten_time (a
    # truncated/short data day) — force-close at the last available close
    # rather than silently dropping an open position.
    last = day_candles[-1]
    return IndexTrade(
        direction=direction, entry_index=entry_index, entry_price=entry_price,
        exit_index=n - 1, exit_price=last.close, initial_stop=initial_stop,
        exit_reason="session_flatten",
    )
