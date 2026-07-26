"""
QuantOS — Dow Theory / Market Structure Trend Following (candidate 14)
────────────────────────────────────────────────────────────────────────
Pure (I/O-free) swing-fractal detection and single-day trade simulation
per docs/DOW_THEORY_TREND_METHODOLOGY.md, fixed BEFORE this module's
result was ever run. NIFTY-index-as-futures-proxy, 5-bar Williams fractal
(K=2), mechanical stop/scale-out/trailing exits. No parameter sweep --
K=2, 5-minute bars, 1R scale-out are the one and only configuration
tested.

Same-bar stop/target ambiguity: if a single bar's range would satisfy both
the stop and the 1R target, the stop is assumed to have been hit first
(conservative -- we only have OHLC, not intrabar sequencing, and this
project prefers the pessimistic read where ambiguous).

Gap-through-stop at entry (the executing open already prices at/past where
the initial stop would sit, giving zero or negative risk) skips the trade
entirely rather than manufacturing a same-bar instant stop-out -- a
disclosed edge case, expected to be rare.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from core.brokers.base import OHLCV

FRACTAL_K = 2                        # bars each side, Williams fractal width
SCALE_OUT_R = 1.0                    # scale out at 1x initial risk
SCALE_OUT_FRACTION = 0.5
SESSION_FLATTEN_UTC = time(9, 50)    # 15:20 IST


@dataclass(frozen=True)
class SwingPoint:
    index: int    # position within the day's candle list
    price: float
    kind: str     # "high" or "low"


def find_confirmed_swings(day_candles: list[OHLCV], k: int = FRACTAL_K) -> list[SwingPoint]:
    """Every confirmed swing high/low in one day's candles (ascending by
    timestamp). Bar i confirms once bars i-k..i+k all exist AND it's the
    STRICT max/min (no ties) of that window -- confirmable only once bar
    i+k has closed, a real (k*bar_width)-lag before it's usable."""
    swings: list[SwingPoint] = []
    n = len(day_candles)
    for i in range(k, n - k):
        window = day_candles[i - k: i + k + 1]
        highs = [c.high for c in window]
        lows = [c.low for c in window]
        if day_candles[i].high == max(highs) and highs.count(day_candles[i].high) == 1:
            swings.append(SwingPoint(index=i, price=day_candles[i].high, kind="high"))
        if day_candles[i].low == min(lows) and lows.count(day_candles[i].low) == 1:
            swings.append(SwingPoint(index=i, price=day_candles[i].low, kind="low"))
    return swings


def _active_swing(swings: list[SwingPoint], as_of_index: int, kind: str, k: int) -> Optional[SwingPoint]:
    """The most recent swing of `kind` that is already CONFIRMED as of
    `as_of_index` -- i.e. its own confirmation bar (index + k) has closed
    at or before as_of_index. This is the anti-look-ahead gate: a swing
    point can't be referenced before the bars that confirm it exist."""
    candidates = [s for s in swings if s.kind == kind and s.index + k <= as_of_index]
    return candidates[-1] if candidates else None


@dataclass(frozen=True)
class Trade:
    direction: str            # "LONG" or "SHORT"
    entry_index: int
    entry_price: float
    exit_index: int
    exit_price: float
    quantity_fraction: float  # 1.0 full exit, 0.5 a scale-out leg
    exit_reason: str          # "stop" | "scale_out_1R" | "trail_stop" | "session_flatten"


def simulate_day(
    day_candles: list[OHLCV], k: int = FRACTAL_K,
    scale_out_r: float = SCALE_OUT_R, scale_out_fraction: float = SCALE_OUT_FRACTION,
    flatten_time: time = SESSION_FLATTEN_UTC,
) -> list[Trade]:
    """Simulate one trading day per docs/DOW_THEORY_TREND_METHODOLOGY.md.
    No cross-day state -- caller passes exactly one day's candles, already
    sorted ascending by timestamp. Entries execute at the NEXT bar's open
    after the signal bar's close (no same-bar execution)."""
    swings = find_confirmed_swings(day_candles, k)
    n = len(day_candles)
    trades: list[Trade] = []

    pos: Optional[dict] = None
    pending_entry: Optional[dict] = None

    for t in range(n):
        candle = day_candles[t]
        flatten_now = candle.timestamp.time() >= flatten_time

        # 1) Execute a pending entry queued from the previous bar's signal.
        if pending_entry is not None and pos is None:
            direction = pending_entry["direction"]
            stop = pending_entry["stop"]
            entry_price = candle.open
            risk = (entry_price - stop) if direction == "LONG" else (stop - entry_price)
            pending_entry = None
            if risk > 0:
                pos = dict(direction=direction, entry_index=t, entry_price=entry_price,
                           stop=stop, risk=risk, remaining=1.0, scaled=False)

        # 2) Manage an open position against this bar's range.
        if pos is not None:
            direction = pos["direction"]
            hit_stop = (candle.low <= pos["stop"]) if direction == "LONG" else (candle.high >= pos["stop"])
            target = (pos["entry_price"] + scale_out_r * pos["risk"] if direction == "LONG"
                      else pos["entry_price"] - scale_out_r * pos["risk"])
            hit_target = (candle.high >= target) if direction == "LONG" else (candle.low <= target)

            if hit_stop:
                trades.append(Trade(direction=direction, entry_index=pos["entry_index"],
                                     entry_price=pos["entry_price"], exit_index=t, exit_price=pos["stop"],
                                     quantity_fraction=pos["remaining"], exit_reason="stop"))
                pos = None
            elif not pos["scaled"] and hit_target:
                trades.append(Trade(direction=direction, entry_index=pos["entry_index"],
                                     entry_price=pos["entry_price"], exit_index=t, exit_price=target,
                                     quantity_fraction=scale_out_fraction, exit_reason="scale_out_1R"))
                pos["remaining"] -= scale_out_fraction
                pos["scaled"] = True
                pos["stop"] = pos["entry_price"]  # breakeven for the runner
            elif flatten_now:
                trades.append(Trade(direction=direction, entry_index=pos["entry_index"],
                                     entry_price=pos["entry_price"], exit_index=t, exit_price=candle.close,
                                     quantity_fraction=pos["remaining"],
                                     exit_reason="session_flatten"))
                pos = None
            elif pos["scaled"]:
                active = _active_swing(swings, t, "low" if direction == "LONG" else "high", k)
                if active is not None:
                    if direction == "LONG" and active.price > pos["stop"]:
                        pos["stop"] = active.price
                    elif direction == "SHORT" and active.price < pos["stop"]:
                        pos["stop"] = active.price

        # 3) Look for a new entry signal at this bar's close.
        if pos is None and pending_entry is None and not flatten_now:
            sh = _active_swing(swings, t, "high", k)
            sl = _active_swing(swings, t, "low", k)
            if sh and sl:
                if candle.close > sh.price:
                    pending_entry = dict(direction="LONG", stop=sl.price)
                elif candle.close < sl.price:
                    pending_entry = dict(direction="SHORT", stop=sh.price)

    # Safety net: a day whose data ends before any candle reached
    # flatten_time (a truncated/short data day) -- force-close at the last
    # available close rather than silently dropping an open position.
    if pos is not None:
        last = day_candles[-1]
        trades.append(Trade(direction=pos["direction"], entry_index=pos["entry_index"],
                             entry_price=pos["entry_price"], exit_index=n - 1, exit_price=last.close,
                             quantity_fraction=pos["remaining"], exit_reason="session_flatten"))

    return trades
