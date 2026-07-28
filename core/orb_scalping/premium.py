"""
QuantOS — ORB Options Scalping Premium Reconstruction (candidate 18)
──────────────────────────────────────────────────────────────────────
Turns one core.orb_scalping.signal.IndexTrade (NIFTY or BankNifty INDEX
points) into real entry/exit option premiums, per
docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md's "Premium reconstruction" and
"Secondary hard premium stop" sections. Reuses core/options/greeks.py's
compute_greeks() unchanged — same Black-Scholes reconstruction approach as
candidate 15 (core/breakout1010/premium.py), extended here with a
per-candle premium walk between entry and the index-level exit, because
this candidate (unlike 15) has a SECOND, premium-based stop that the
index-level signal alone cannot see (IV crush / vega decay from a slow
reversal that never actually reaches the index-level stop).

If both the index-level exit and the 25% premium stop would trigger on
the SAME candle, the premium stop takes precedence (checked first in the
loop below) — a disclosed, conservative tie-break, same spirit as
candidate 15's "stop wins over target on the same candle" convention.

Every premium value this module produces is a Black-Scholes THEORETICAL
price, not a real traded price — same disclosed limitation as candidate
15 (docs/CANDIDATE15_OPTION_DATA_FEASIBILITY.md): real historical option
intraday data is confirmed unfetchable from Fyers for any expired
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.brokers.base import OHLCV
from core.options.greeks import compute_greeks
from core.options.models import OptionType
from core.orb_scalping.signal import IndexTrade

PREMIUM_STOP_PCT = 0.25   # methodology doc: 25% loss of entry premium, OR condition


def _option_type(direction: str) -> OptionType:
    return OptionType.CALL if direction == "CALL" else OptionType.PUT


def _vix_at(vix_day_candles: list[OHLCV], index: int) -> float:
    """The VIX 5m candle CLOSE at the same candle position as the index
    candle series — both series fetched over the identical UTC window, so
    a matching index is the contemporaneous VIX reading. Falls back to the
    last available VIX candle if the two series have drifted out of
    alignment (a missing print on one side), same disclosed approximation
    as candidate 15."""
    if not vix_day_candles:
        raise ValueError("no VIX candles available for this day")
    idx = min(index, len(vix_day_candles) - 1)
    return vix_day_candles[idx].close


def atm_strike(index_level: float, interval: float) -> float:
    """Nearest strike to `index_level` at the given near-the-money
    interval (50 for NIFTY, 100 for BankNifty — both confirmed live 2026-
    07-28/candidate 15). ATM is fixed at entry, never re-struck."""
    return round(index_level / interval) * interval


@dataclass(frozen=True)
class PremiumTrade:
    """core.orb_scalping.signal.IndexTrade, with entry/exit reconstructed
    as real option premiums (points) rather than index levels."""
    direction:         str     # "CALL" or "PUT"
    entry_timestamp:   object  # datetime
    entry_index_level: float
    entry_premium:     float
    exit_timestamp:    object  # datetime
    exit_index_level:  float
    exit_premium:      float
    strike:            float
    expiry:            date
    exit_reason:       str     # signal.py's reasons, or "premium_stop"


def reconstruct_premium(
    index_trade: IndexTrade,
    day_candles: list[OHLCV],
    vix_day_candles: list[OHLCV],
    expiry: date,
    strike_interval: float,
) -> PremiumTrade:
    """Reconstruct entry/exit premiums for one IndexTrade, walking every
    candle from entry to the index-determined exit to check the 25%
    secondary premium stop — whichever of the two stops (index-level,
    already applied by signal.py; or this premium-based one) triggers
    FIRST in time wins. `expiry` is the already-resolved contract for this
    trading day (including any DTE-floor roll — see
    core/orb_scalping/expiry.py) — this function does no expiry-date logic
    of its own."""
    option_type = _option_type(index_trade.direction)
    strike = atm_strike(index_trade.entry_price, strike_interval)

    entry_dt = day_candles[index_trade.entry_index].timestamp
    entry_vix = _vix_at(vix_day_candles, index_trade.entry_index)
    entry_dte = max(1, (expiry - entry_dt.date()).days)
    entry_premium = compute_greeks(
        spot=index_trade.entry_price, strike=strike, days_to_expiry=entry_dte,
        implied_vol=entry_vix / 100.0, option_type=option_type,
    ).theoretical_price
    premium_stop_level = entry_premium * (1 - PREMIUM_STOP_PCT)

    last_timestamp, last_spot, last_premium = entry_dt, index_trade.entry_price, entry_premium

    for i in range(index_trade.entry_index + 1, index_trade.exit_index + 1):
        candle = day_candles[i]
        # The final candle uses the exact index-level exit price signal.py
        # already determined (a stop/trailing-stop LEVEL, not necessarily
        # this candle's close); every earlier candle uses its own close —
        # same close-only discipline as the entry/breakout signal.
        spot = index_trade.exit_price if i == index_trade.exit_index else candle.close
        vix = _vix_at(vix_day_candles, i)
        dte = max(1, (expiry - candle.timestamp.date()).days)
        premium = compute_greeks(
            spot=spot, strike=strike, days_to_expiry=dte,
            implied_vol=vix / 100.0, option_type=option_type,
        ).theoretical_price

        last_timestamp, last_spot, last_premium = candle.timestamp, spot, premium

        if premium <= premium_stop_level:
            return PremiumTrade(
                direction=index_trade.direction,
                entry_timestamp=entry_dt, entry_index_level=index_trade.entry_price,
                entry_premium=entry_premium,
                exit_timestamp=candle.timestamp, exit_index_level=spot,
                exit_premium=premium_stop_level,
                strike=strike, expiry=expiry, exit_reason="premium_stop",
            )

    # Secondary stop never triggered before the index-level exit — use it
    # as-is. `last_*` already holds exactly this exit's own values from the
    # loop's final iteration (index_trade.exit_index), no recompute needed.
    return PremiumTrade(
        direction=index_trade.direction,
        entry_timestamp=entry_dt, entry_index_level=index_trade.entry_price,
        entry_premium=entry_premium,
        exit_timestamp=last_timestamp, exit_index_level=last_spot,
        exit_premium=last_premium,
        strike=strike, expiry=expiry, exit_reason=index_trade.exit_reason,
    )
