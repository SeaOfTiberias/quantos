"""
QuantOS — 10:10 Breakout Signal (candidate 15)
────────────────────────────────────────────────
Pure (I/O-free) reference-candle breakout detection and single-day index-
level trade simulation per docs/BREAKOUT_1010_METHODOLOGY.md, fixed BEFORE
this module's result was ever run. All prices here are BankNifty INDEX
points — option premium reconstruction happens one layer up
(core/breakout1010/premium.py), never in this module.

Same-candle stop/target ambiguity: if a single candle's range would satisfy
both the stop and the target, the stop is assumed to have been hit first
(conservative — we only have OHLC, not intrabar sequencing), same
convention as core/trend/dow_structure.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from core.brokers.base import OHLCV

REFERENCE_CANDLE_INDEX = 11    # 0-indexed: the 12th candle of the day (opens 10:10 IST)
MAX_STOP_POINTS = 40.0
TARGET_POINTS = 200.0
SESSION_FLATTEN_UTC = time(9, 50)    # 15:20 IST


@dataclass(frozen=True)
class IndexTrade:
    direction:      str     # "CALL" or "PUT"
    entry_index:    int     # position within the day's candle list
    entry_price:    float   # BankNifty index level at entry
    exit_index:     int
    exit_price:     float   # BankNifty index level at exit
    stop_level:     float
    target_level:   float
    exit_reason:    str     # "stop" | "target" | "session_flatten"


def simulate_day(day_candles: list[OHLCV],
                  flatten_time: time = SESSION_FLATTEN_UTC) -> Optional[IndexTrade]:
    """Simulate one trading day's 10:10 breakout per
    docs/BREAKOUT_1010_METHODOLOGY.md. No cross-day state — caller passes
    exactly one day's candles, already sorted ascending by timestamp.
    Returns None if the day has fewer than REFERENCE_CANDLE_INDEX + 1
    candles (a shortened session — skipped, not approximated) or if no
    breakout occurs by session flatten. One trade per day, first breakout
    only, execution at the next candle's open after the signal candle's
    close (no same-bar execution)."""
    n = len(day_candles)
    if n <= REFERENCE_CANDLE_INDEX:
        return None

    reference = day_candles[REFERENCE_CANDLE_INDEX]
    ref_high, ref_low = reference.high, reference.low

    pending_direction: Optional[str] = None

    for t in range(REFERENCE_CANDLE_INDEX + 1, n):
        candle = day_candles[t]
        flatten_now = candle.timestamp.time() >= flatten_time

        # 1) Execute a pending entry queued from the previous candle's signal.
        if pending_direction is not None:
            direction = pending_direction
            entry_price = candle.open
            stop_distance = min(MAX_STOP_POINTS, ref_high - ref_low)
            if direction == "CALL":
                stop_level = entry_price - stop_distance
                target_level = entry_price + TARGET_POINTS
            else:  # PUT
                stop_level = entry_price + stop_distance
                target_level = entry_price - TARGET_POINTS
            return _manage_position(
                day_candles, entry_index=t, entry_price=entry_price,
                direction=direction, stop_level=stop_level, target_level=target_level,
                flatten_time=flatten_time,
            )

        # 2) Look for the day's first breakout, on candle close.
        if not flatten_now:
            if candle.close > ref_high:
                pending_direction = "CALL"
            elif candle.close < ref_low:
                pending_direction = "PUT"

    return None


def _manage_position(
    day_candles: list[OHLCV], entry_index: int, entry_price: float,
    direction: str, stop_level: float, target_level: float, flatten_time: time,
) -> IndexTrade:
    """Walk forward from the entry candle, checking each subsequent candle's
    range against stop/target, flattening at session close if neither hits."""
    n = len(day_candles)
    for t in range(entry_index + 1, n):
        candle = day_candles[t]
        if direction == "CALL":
            hit_stop = candle.low <= stop_level
            hit_target = candle.high >= target_level
        else:  # PUT
            hit_stop = candle.high >= stop_level
            hit_target = candle.low <= target_level

        if hit_stop:
            return IndexTrade(direction=direction, entry_index=entry_index, entry_price=entry_price,
                               exit_index=t, exit_price=stop_level, stop_level=stop_level,
                               target_level=target_level, exit_reason="stop")
        if hit_target:
            return IndexTrade(direction=direction, entry_index=entry_index, entry_price=entry_price,
                               exit_index=t, exit_price=target_level, stop_level=stop_level,
                               target_level=target_level, exit_reason="target")
        if candle.timestamp.time() >= flatten_time:
            return IndexTrade(direction=direction, entry_index=entry_index, entry_price=entry_price,
                               exit_index=t, exit_price=candle.close, stop_level=stop_level,
                               target_level=target_level, exit_reason="session_flatten")

    # Safety net: data ends before any candle reached flatten_time (a
    # truncated/short data day) — force-close at the last available close
    # rather than silently dropping an open position.
    last = day_candles[-1]
    return IndexTrade(direction=direction, entry_index=entry_index, entry_price=entry_price,
                       exit_index=n - 1, exit_price=last.close, stop_level=stop_level,
                       target_level=target_level, exit_reason="session_flatten")
