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
    # Diagnostic only (added 2026-09-21) -- neither field feeds a trading
    # decision anywhere; they exist so a post-hoc analysis can ask "how much
    # of a trade's best-ever paper profit survived to the exit" without
    # re-deriving the whole candle walk. armed=False + a session_flatten exit
    # means the trade never moved a full range-width in its favor, so nothing
    # ever protected whatever intraday gain it built and gave back.
    armed:                    bool = False
    max_favorable_points:     float = 0.0   # best paper move in direction's favor, entry to exit


def simulate_day(day_candles: list[OHLCV],
                  flatten_time: time = SESSION_FLATTEN_UTC,
                  arm_multiplier: float = 1.0) -> Optional[IndexTrade]:
    """Simulate one trading day's ORB per
    docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md. No cross-day state — caller
    passes exactly one day's 5-minute candles, already sorted ascending by
    timestamp. Returns None if the day has fewer than OPENING_RANGE_CANDLES
    + 1 candles (a shortened session — skipped, not approximated) or if no
    breakout occurs by session flatten. One trade per day, first breakout
    only, execution at the next candle's open after the signal candle's
    close (no same-bar execution).

    `arm_multiplier` (default 1.0, the locked-final methodology's own value
    — every existing caller is byte-for-byte unchanged unless it passes a
    different value) scales how many range-widths of favorable move are
    needed to arm the trailing stop. See
    docs/ORB_ARM_THRESHOLD_METHODOLOGY.md — the only sanctioned use of a
    non-default value is that pre-registered grid backtest; nothing live
    passes anything but the default."""
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
                arm_multiplier=arm_multiplier,
            )

        # 2) Look for the day's first breakout, on candle close.
        if not flatten_now:
            if candle.close > range_high:
                pending_direction = "CALL"
            elif candle.close < range_low:
                pending_direction = "PUT"

    return None


def trail_arm_level(direction: str, entry_price: float, range_width: float,
                    multiplier: float = 1.0) -> float:
    """Public (not module-private): core.orb_scalping.live_state reuses this
    exact arithmetic for the live-monitor's arm check, single source of
    truth for the formula shared by both the backtest and the live probe.
    `multiplier` — see simulate_day's docstring; default reproduces the
    original 1-range-width rule exactly."""
    move = range_width * multiplier
    return entry_price + move if direction == "CALL" else entry_price - move


def _manage_position(
    day_candles: list[OHLCV], entry_index: int, entry_price: float,
    direction: str, initial_stop: float, range_width: float, flatten_time: time,
    arm_multiplier: float = 1.0,
) -> IndexTrade:
    """Walk forward from the entry candle: check the current stop, arm
    trailing once price has moved `arm_multiplier` range-widths in favor,
    then recompute the trailing stop from the prior TRAIL_LOOKBACK_CANDLES
    candles (never loosening it), flattening at session close if nothing
    else has triggered."""
    n = len(day_candles)
    stop = initial_stop
    armed = False
    arm_level = trail_arm_level(direction, entry_price, range_width, multiplier=arm_multiplier)
    # Diagnostic only -- see IndexTrade.max_favorable_points. mfe is seeded
    # here (not just inside the loop) so the entry_index == n - 1 edge case
    # below (entry executes on the day's last available candle, nothing left
    # to walk) still returns a defined value instead of an unbound name.
    best_favorable = entry_price
    mfe = 0.0

    for t in range(entry_index + 1, n):
        candle = day_candles[t]
        best_favorable = (max(best_favorable, candle.high) if direction == "CALL"
                          else min(best_favorable, candle.low))
        mfe = (best_favorable - entry_price if direction == "CALL"
              else entry_price - best_favorable)

        hit_stop = candle.low <= stop if direction == "CALL" else candle.high >= stop
        if hit_stop:
            return IndexTrade(
                direction=direction, entry_index=entry_index, entry_price=entry_price,
                exit_index=t, exit_price=stop, initial_stop=initial_stop,
                exit_reason="trailing_stop" if armed else "stop",
                armed=armed, max_favorable_points=mfe,
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
                armed=armed, max_favorable_points=mfe,
            )

    # Safety net: data ends before any candle reached flatten_time (a
    # truncated/short data day) — force-close at the last available close
    # rather than silently dropping an open position. best_favorable/mfe
    # already reflect every candle through day_candles[-1] from the loop
    # above (its last iteration was t == n - 1).
    last = day_candles[-1]
    return IndexTrade(
        direction=direction, entry_index=entry_index, entry_price=entry_price,
        exit_index=n - 1, exit_price=last.close, initial_stop=initial_stop,
        exit_reason="session_flatten",
        armed=armed, max_favorable_points=mfe,
    )
