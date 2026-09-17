"""
QuantOS — "Good Night" Scalper Premium Reconstruction + Exit Management (candidate 20)
──────────────────────────────────────────────────────────────────────
Owns BOTH premium reconstruction AND exit management for this candidate —
unlike core/orb_scalping/{signal,premium}.py's split, where signal.py decides
exits on the INDEX level and premium.py only re-walks for a secondary premium
stop. Here, the target (+10%)/stop(-15%)/flatten(09:30 IST) bracket is native
to the premium itself from the start, so there is no index-level exit
decision to defer to — this module IS the exit-decision loop. See
core/goodnight_scalper/signal.py's module docstring for the same note from
the other side.

Reuses core/options/greeks.py's compute_greeks() unchanged (same
Black-Scholes approach as candidates 15/18) and core/orb_scalping/premium.py's
atm_strike() unchanged (single source of truth for "nearest strike at a given
interval" — no index/stock-specific logic in it worth a second copy).

IV proxy: trailing realized volatility of the stock's own daily closes, NOT
India VIX (see docs/GOODNIGHT_SCALPER_METHODOLOGY.md's "Premium
reconstruction" section for why a shared index-wide vol proxy doesn't fit 30
individually-different stocks). realized_volatility() is pure and does no
date filtering of its own — the caller must already have sliced the input to
strictly precede the trade date, so there is no lookahead risk hidden inside
this module.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, time

from core.brokers.base import OHLCV
from core.goodnight_scalper.signal import EntrySignal
from core.options.greeks import compute_greeks
from core.options.models import OptionType
from core.orb_scalping.premium import atm_strike

TARGET_PCT = 0.10                # methodology doc: +10% premium target
STOP_PCT = 0.15                  # methodology doc: -15% premium stop
FLATTEN_TIME_UTC = time(4, 0)    # 09:30 IST
REALIZED_VOL_LOOKBACK_DAYS = 20  # methodology doc: trailing 20-trading-day window
TRADING_DAYS_PER_YEAR = 252


def realized_volatility(daily_closes: list[float]) -> float:
    """Annualized realized volatility (stdev of daily log returns *
    sqrt(252)) from `daily_closes`, oldest-to-newest. The caller is
    responsible for the window (methodology doc: trailing
    REALIZED_VOL_LOOKBACK_DAYS closes strictly BEFORE the trade date) --
    this function does no date filtering, kept pure so there is no
    lookahead risk hidden inside it."""
    if len(daily_closes) < 2:
        raise ValueError("need at least 2 daily closes to compute a return")
    log_returns = [
        math.log(daily_closes[i] / daily_closes[i - 1])
        for i in range(1, len(daily_closes))
        if daily_closes[i - 1] > 0 and daily_closes[i] > 0
    ]
    if len(log_returns) < 2:
        raise ValueError("not enough valid daily closes to compute a volatility")
    return statistics.stdev(log_returns) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _option_type(direction: str) -> OptionType:
    return OptionType.CALL if direction == "CALL" else OptionType.PUT


@dataclass(frozen=True)
class StockPremiumTrade:
    symbol:            str
    setup:              str     # "A" | "B"
    direction:          str     # "CALL" | "PUT"
    entry_timestamp:    object  # datetime
    entry_index_level:  float
    entry_premium:      float
    exit_timestamp:     object  # datetime
    exit_index_level:   float
    exit_premium:       float
    strike:             float
    expiry:             date
    exit_reason:        str     # "target" | "stop" | "session_flatten"


def reconstruct_trade(
    symbol: str,
    entry_signal: EntrySignal,
    day_candles: list[OHLCV],
    strike_interval: float,
    expiry: date,
    implied_vol: float,
) -> StockPremiumTrade:
    """Walk every 1-minute candle from the execution candle's own close
    through the earlier of target/stop/09:30 IST flatten, pricing the
    premium via Black-Scholes at each step. `implied_vol` is the caller's
    already-computed realized-vol proxy, held fixed for the whole trade (no
    intraday recompute -- the simplest defensible choice absent a real
    per-minute IV series).

    Unlike candidates 15/18, there is no same-candle target-vs-stop
    ambiguity to tie-break here: this walk only ever checks ONE premium
    value per candle (computed from `candle.close`, no intrabar high/low),
    and target_level (entry * 1.10) is always strictly above stop_level
    (entry * 0.85) for any positive entry_premium -- so a single close value
    can satisfy at most one of the two conditions, never both. Stop is
    still checked first in the code below purely for readability, not
    because it resolves a real conflict.

    The loop starts AT the execution candle (entry_signal.entry_index), not
    after it: entry happens at that candle's OPEN, so by the time it
    CLOSES a full minute has already passed and the position's fate may
    already be partly determined -- a deliberate choice for this
    candidate's very short (≈14-minute) holding window, disclosed here
    since core/orb_scalping/premium.py's semantically different
    entry_index (there, signal.py has already decided exits at the index
    level) starts its own walk one candle later."""
    option_type = _option_type(entry_signal.direction)
    strike = atm_strike(entry_signal.entry_price, strike_interval)

    entry_dt = entry_signal.entry_timestamp
    entry_dte = max(1, (expiry - entry_dt.date()).days)
    entry_premium = compute_greeks(
        spot=entry_signal.entry_price, strike=strike, days_to_expiry=entry_dte,
        implied_vol=implied_vol, option_type=option_type,
    ).theoretical_price
    target_level = entry_premium * (1 + TARGET_PCT)
    stop_level = entry_premium * (1 - STOP_PCT)

    last_timestamp, last_spot, last_premium = entry_dt, entry_signal.entry_price, entry_premium

    for i in range(entry_signal.entry_index, len(day_candles)):
        candle = day_candles[i]
        spot = candle.close
        dte = max(1, (expiry - candle.timestamp.date()).days)
        premium = compute_greeks(
            spot=spot, strike=strike, days_to_expiry=dte,
            implied_vol=implied_vol, option_type=option_type,
        ).theoretical_price
        last_timestamp, last_spot, last_premium = candle.timestamp, spot, premium

        common = dict(
            symbol=symbol, setup=entry_signal.setup, direction=entry_signal.direction,
            entry_timestamp=entry_dt, entry_index_level=entry_signal.entry_price,
            entry_premium=entry_premium, exit_timestamp=candle.timestamp,
            exit_index_level=spot, strike=strike, expiry=expiry,
        )
        if premium <= stop_level:
            return StockPremiumTrade(**common, exit_premium=stop_level, exit_reason="stop")
        if premium >= target_level:
            return StockPremiumTrade(**common, exit_premium=target_level, exit_reason="target")
        if candle.timestamp.time() >= FLATTEN_TIME_UTC:
            return StockPremiumTrade(**common, exit_premium=premium, exit_reason="session_flatten")

    # Ran out of candles before any exit condition fired (a data gap, not
    # expected on a normal day) -- flatten at the last available reading
    # rather than leaving the trade artificially open.
    return StockPremiumTrade(
        symbol=symbol, setup=entry_signal.setup, direction=entry_signal.direction,
        entry_timestamp=entry_dt, entry_index_level=entry_signal.entry_price,
        entry_premium=entry_premium, exit_timestamp=last_timestamp,
        exit_index_level=last_spot, exit_premium=last_premium,
        strike=strike, expiry=expiry, exit_reason="session_flatten",
    )
