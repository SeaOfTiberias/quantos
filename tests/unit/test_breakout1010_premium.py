"""
10:10 Breakout — Premium Reconstruction Unit Tests

Covers core/breakout1010/premium.py per docs/BREAKOUT_1010_METHODOLOGY.md's
"Premium reconstruction" section: ATM-at-entry strike selection and
Black-Scholes premium reconstruction off real index levels + contemporaneous
India VIX, reusing core/options/greeks.py's compute_greeks() unchanged.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.breakout1010.premium import atm_strike, reconstruct_premium  # noqa: E402
from core.breakout1010.signal import IndexTrade  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.options.greeks import compute_greeks  # noqa: E402
from core.options.models import OptionType  # noqa: E402

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i: int, price: float, v: int = 1000) -> OHLCV:
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=price, high=price,
                 low=price, close=price, volume=v)


# ─── atm_strike ───────────────────────────────────────────────────────────

def test_atm_strike_rounds_to_nearest_100():
    assert atm_strike(50042.0) == 50000.0
    assert atm_strike(50051.0) == 50100.0


# ─── reconstruct_premium ──────────────────────────────────────────────────

def test_reconstruct_premium_matches_direct_compute_greeks_call():
    day_candles = [bar(i, 50000.0 + i) for i in range(20)]
    vix_candles = [bar(i, 15.0) for i in range(20)]  # flat 15% VIX
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=50005.0,
        exit_index=10, exit_price=50205.0,
        stop_level=49965.0, target_level=50205.0, exit_reason="target",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry)

    strike = atm_strike(50005.0)
    assert result.strike == strike
    expected_entry = compute_greeks(
        spot=50005.0, strike=strike, days_to_expiry=10,
        implied_vol=0.15, option_type=OptionType.CALL,
    ).theoretical_price
    assert result.entry_premium == expected_entry
    expected_exit = compute_greeks(
        spot=50205.0, strike=strike, days_to_expiry=10,
        implied_vol=0.15, option_type=OptionType.CALL,
    ).theoretical_price
    assert result.exit_premium == expected_exit


def test_reconstruct_premium_uses_put_for_put_direction():
    day_candles = [bar(i, 50000.0 - i) for i in range(20)]
    vix_candles = [bar(i, 20.0) for i in range(20)]
    index_trade = IndexTrade(
        direction="PUT", entry_index=5, entry_price=49995.0,
        exit_index=10, exit_price=49795.0,
        stop_level=50035.0, target_level=49795.0, exit_reason="target",
    )
    expiry = date(2024, 1, 2) + timedelta(days=15)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry)

    expected_entry = compute_greeks(
        spot=49995.0, strike=result.strike, days_to_expiry=15,
        implied_vol=0.20, option_type=OptionType.PUT,
    ).theoretical_price
    assert result.entry_premium == expected_entry


def test_reconstruct_premium_uses_contemporaneous_vix_not_a_frozen_entry_snapshot():
    day_candles = [bar(i, 50000.0) for i in range(20)]  # flat index -- isolates the VIX effect
    vix_candles = [bar(i, 10.0 + i) for i in range(20)]  # rising VIX path
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=50000.0,
        exit_index=10, exit_price=50000.0,
        stop_level=49960.0, target_level=50200.0, exit_reason="session_flatten",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry)

    # same spot/strike/dte at entry and exit, but VIX differs (15% vs 20%) --
    # a flat-IV design would give identical entry/exit premiums here, this
    # design must not.
    assert result.entry_premium != result.exit_premium
    higher_vol_premium = compute_greeks(
        spot=50000.0, strike=result.strike, days_to_expiry=10,
        implied_vol=0.20, option_type=OptionType.CALL,
    ).theoretical_price
    assert result.exit_premium == higher_vol_premium
