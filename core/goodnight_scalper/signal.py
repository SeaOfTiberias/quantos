"""
QuantOS — "Good Night" Scalper Entry Signal (candidate 20)
──────────────────────────────────────────────────────────────────────
docs/GOODNIGHT_SCALPER_METHODOLOGY.md's entry rule, Setups A and B only
(Setup C excluded — see the methodology doc's "The source strategy" section
for why). Pure, no I/O: one symbol's one day of already-fetched 1-minute
candles in, an entry signal (or None) out.

Deliberately a SMALLER split than core/orb_scalping/{signal,premium}.py's
division of labour: this module owns ONLY entry detection. Exit management
(target/stop/flatten) lives in core/goodnight_scalper/premium.py instead of
here, because — unlike candidate 18, where the stop is native to the INDEX
level and only secondarily translated into a premium check — this
candidate's target/stop are native to the PREMIUM itself from the start.
Splitting exit logic into this module would mean it doing Black-Scholes
premium walking on every candle just to know when to stop, which is exactly
premium.py's job; keeping it there means one place owns "what is the premium
right now", not two. A disclosed structural deviation from candidate 18's
split, not an inconsistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import OHLCV


@dataclass(frozen=True)
class EntrySignal:
    direction:       str    # "CALL" | "PUT"
    setup:           str    # "A" | "B"
    entry_index:     int    # index into day_candles of the EXECUTION candle
    entry_timestamp: datetime
    entry_price:     float  # underlying open at entry_index (next candle's open)


def detect_entry(day_candles: list[OHLCV]) -> Optional[EntrySignal]:
    """`day_candles`: TODAY's 1-minute candles from session open (09:15 IST),
    ascending, already validated by the caller. Needs at least 2 candles (the
    09:15 candle to read the open/setup from, and the next candle to execute
    on) — fewer than that (a shortened session) means no signal is possible,
    same "skipped, not approximated" convention as every prior candidate.

    Setup A: the 09:15 candle's low == the day's open -> CALL.
    Setup B: the 09:15 candle's high == the day's open -> PUT.
    Both firing on the same candle (open == high == low, a degenerate
    zero-range candle) is ambiguous -> no trade, a new disclosed tie-break
    the original spec never addressed.

    Execution is the NEXT candle's open (no same-bar execution, same
    close-only/no-lookahead discipline as every prior candidate) — a
    disclosed simplification of the spec's literal 09:15:30-09:18:00 IST
    entry window, forced by Fyers' history endpoint having no access to a
    still-forming candle."""
    if len(day_candles) < 2:
        return None

    opening_candle = day_candles[0]
    day_open = opening_candle.open
    setup_a = opening_candle.low == day_open
    setup_b = opening_candle.high == day_open

    if setup_a and setup_b:
        return None
    if setup_a:
        direction, setup = "CALL", "A"
    elif setup_b:
        direction, setup = "PUT", "B"
    else:
        return None

    execution_candle = day_candles[1]
    return EntrySignal(
        direction=direction, setup=setup, entry_index=1,
        entry_timestamp=execution_candle.timestamp,
        entry_price=execution_candle.open,
    )
