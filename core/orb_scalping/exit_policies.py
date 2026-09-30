"""
QuantOS — ORB exit policies (research, 2026-09-30)
───────────────────────────────────────────────────
Same entry as core/orb_scalping/signal.py (5-min opening range, breakout on a
candle CLOSE, entry at the next candle's OPEN, initial stop at the opposite side
of the range), with the EXIT made configurable. Why now: the 2026-09-21
arm-threshold study that kept "hold to 15:20 unless the trail arms" ran on the
old pricing, which had ZERO intraday time decay -- holding an option all day
was free. Under the calibrated convention (docs/ORB_TIME_CONVENTION_*.md)
every minute held costs premium, so exits need re-testing. The user pointed
out every trailing-stop exit on paper made money while waiting for the 15:20
flatten was the lazy default.

ExitPolicy() with defaults reproduces signal.simulate_day exactly (asserted
on the real candles by scripts/backtest_orb_exits.py before it reports).
Decisions use candle closes only (no intrabar lookahead), same discipline as
signal.py; stops are checked against each candle's high/low.
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
    IndexTrade,
    trail_arm_level,
)

CANDLE_MINUTES = 5


@dataclass(frozen=True)
class ExitPolicy:
    name: str = "V0 current"
    arm_multiplier: float = 1.0                # arm the swing trail after this many range-widths
    breakeven_at: Optional[float] = None       # move the stop to entry once a close is this many RW in favor
    time_stop_minutes: Optional[int] = None    # exit at the close if NOT armed this long after entry
    trail_from_entry: Optional[float] = None   # from entry: stop trails the best close by this many RW


def simulate_day_with_policy(day_candles: list[OHLCV], policy: ExitPolicy,
                             flatten_time: time = SESSION_FLATTEN_UTC) -> Optional[IndexTrade]:
    n = len(day_candles)
    if n <= OPENING_RANGE_CANDLES:
        return None
    rng = day_candles[:OPENING_RANGE_CANDLES]
    range_high, range_low = max(c.high for c in rng), min(c.low for c in rng)
    rw = range_high - range_low
    pending = None
    for t in range(OPENING_RANGE_CANDLES, n):
        c = day_candles[t]
        if pending is not None:
            stop = range_low if pending == "CALL" else range_high
            return _manage(day_candles, t, c.open, pending, stop, rw, flatten_time, policy)
        if c.timestamp.time() < flatten_time:
            if c.close > range_high:
                pending = "CALL"
            elif c.close < range_low:
                pending = "PUT"
    return None


def _manage(day, entry_index, entry, direction, initial_stop, rw, flatten_time, p: ExitPolicy) -> IndexTrade:
    call = direction == "CALL"
    sign = 1 if call else -1
    stop, armed, be_done = initial_stop, False, False
    arm_level = trail_arm_level(direction, entry, rw, multiplier=p.arm_multiplier)
    best_close = entry
    best_fav = entry
    n = len(day)

    def out(t, price, reason):
        mfe = (best_fav - entry) * sign
        return IndexTrade(direction=direction, entry_index=entry_index, entry_price=entry,
                          exit_index=t, exit_price=price, initial_stop=initial_stop,
                          exit_reason=reason, armed=armed, max_favorable_points=mfe)

    for t in range(entry_index + 1, n):
        c = day[t]
        best_fav = max(best_fav, c.high) if call else min(best_fav, c.low)
        if (c.low <= stop) if call else (c.high >= stop):
            reason = ("trailing_stop" if armed or p.trail_from_entry is not None
                      else "breakeven_stop" if be_done else "stop")
            return out(t, stop, reason)

        best_close = max(best_close, c.close) if call else min(best_close, c.close)
        minutes = (t - entry_index) * CANDLE_MINUTES
        if p.time_stop_minutes is not None and not armed and minutes >= p.time_stop_minutes:
            return out(t, c.close, "time_stop")

        if p.breakeven_at is not None and not be_done and (c.close - entry) * sign >= p.breakeven_at * rw:
            stop = max(stop, entry) if call else min(stop, entry)
            be_done = True
        if not armed and ((c.close >= arm_level) if call else (c.close <= arm_level)):
            armed = True
        if armed:
            lb = day[max(entry_index + 1, t - TRAIL_LOOKBACK_CANDLES + 1):t + 1]
            stop = max(stop, min(x.low for x in lb)) if call else min(stop, max(x.high for x in lb))
        if p.trail_from_entry is not None:
            level = best_close - sign * p.trail_from_entry * rw
            stop = max(stop, level) if call else min(stop, level)
        if c.timestamp.time() >= flatten_time:
            return out(t, c.close, "session_flatten")
    return out(n - 1, day[-1].close, "session_flatten")


# The pre-registered set (2026-09-30, docs in scripts/backtest_orb_exits.py).
POLICIES = (
    ExitPolicy(),
    ExitPolicy(name="V1 arm at 0.5 RW", arm_multiplier=0.5),
    ExitPolicy(name="V2 breakeven at 0.5 RW", breakeven_at=0.5),
    ExitPolicy(name="V3 time stop 60 min (if not armed)", time_stop_minutes=60),
    ExitPolicy(name="V4 trail 1 RW from entry", trail_from_entry=1.0),
)
