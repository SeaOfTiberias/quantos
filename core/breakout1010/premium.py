"""
QuantOS — 10:10 Breakout Option-Premium Reconstruction (candidate 15)
──────────────────────────────────────────────────────────────────────
Turns one core.breakout1010.signal.IndexTrade (BankNifty INDEX points) into
real entry/exit option premiums, per docs/BREAKOUT_1010_METHODOLOGY.md's
"Premium reconstruction" section. Reuses core/options/greeks.py's
compute_greeks() unchanged — no new Black-Scholes pricer is written here.

Every premium value this module produces is a Black-Scholes THEORETICAL
price, not a real traded price — see the methodology doc's "central
limitation" section for why (real historical option intraday data is
confirmed unfetchable from Fyers for any expired contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.breakout1010.signal import IndexTrade
from core.brokers.base import OHLCV
from core.options.greeks import compute_greeks
from core.options.models import OptionType

STRIKE_INTERVAL = 100.0    # confirmed live 2026-07-27 against the real BANKNIFTY symbol master


def atm_strike(index_level: float, interval: float = STRIKE_INTERVAL) -> float:
    """Nearest strike to `index_level`, at BankNifty's confirmed 100-point
    near-the-money interval. ATM is fixed at entry, never re-struck."""
    return round(index_level / interval) * interval


def _option_type(direction: str) -> OptionType:
    return OptionType.CALL if direction == "CALL" else OptionType.PUT


def _vix_at(vix_day_candles: list[OHLCV], index: int) -> float:
    """The India VIX 5m candle CLOSE at the same candle position as a
    BankNifty candle — both series are fetched over the identical UTC
    window, so a matching index is the contemporaneous VIX reading. Falls
    back to the last available VIX candle if the two series have drifted
    out of alignment (a missing print on one side) rather than raising —
    a disclosed approximation, not a silent one."""
    if not vix_day_candles:
        raise ValueError("no VIX candles available for this day")
    idx = min(index, len(vix_day_candles) - 1)
    return vix_day_candles[idx].close


@dataclass(frozen=True)
class PremiumTrade:
    """core.breakout1010.signal.IndexTrade, with entry/exit reconstructed
    as real option premiums (points) rather than index levels."""
    direction:        str     # "CALL" or "PUT"
    entry_timestamp:  object  # datetime
    entry_index_level: float
    entry_premium:    float
    exit_timestamp:   object  # datetime
    exit_index_level: float
    exit_premium:     float
    strike:           float
    expiry:           date
    exit_reason:      str


def reconstruct_premium(
    index_trade: IndexTrade,
    day_candles: list[OHLCV],
    vix_day_candles: list[OHLCV],
    expiry: date,
) -> PremiumTrade:
    """Reconstruct entry/exit premiums for one IndexTrade. `expiry` is the
    already-resolved nearest monthly BankNifty contract for this trading
    day (see core/breakout1010/backtest.py's expiry-calendar resolution) —
    this function does no expiry-date logic of its own."""
    option_type = _option_type(index_trade.direction)
    strike = atm_strike(index_trade.entry_price)

    entry_dt = day_candles[index_trade.entry_index].timestamp
    exit_dt = day_candles[index_trade.exit_index].timestamp

    entry_vix = _vix_at(vix_day_candles, index_trade.entry_index)
    exit_vix = _vix_at(vix_day_candles, index_trade.exit_index)

    entry_dte = max(1, (expiry - entry_dt.date()).days)
    exit_dte = max(1, (expiry - exit_dt.date()).days)

    entry_premium = compute_greeks(
        spot=index_trade.entry_price, strike=strike, days_to_expiry=entry_dte,
        implied_vol=entry_vix / 100.0, option_type=option_type,
    ).theoretical_price
    exit_premium = compute_greeks(
        spot=index_trade.exit_price, strike=strike, days_to_expiry=exit_dte,
        implied_vol=exit_vix / 100.0, option_type=option_type,
    ).theoretical_price

    return PremiumTrade(
        direction=index_trade.direction,
        entry_timestamp=entry_dt, entry_index_level=index_trade.entry_price,
        entry_premium=entry_premium,
        exit_timestamp=exit_dt, exit_index_level=index_trade.exit_price,
        exit_premium=exit_premium,
        strike=strike, expiry=expiry, exit_reason=index_trade.exit_reason,
    )
