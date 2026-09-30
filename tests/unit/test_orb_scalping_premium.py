"""
ORB Options Scalping — Premium Reconstruction Unit Tests

Covers core/orb_scalping/premium.py per
docs/ORB_OPTIONS_SCALPING_METHODOLOGY.md's "Premium reconstruction" and
"Secondary hard premium stop" sections: ATM-at-entry strike selection,
Black-Scholes premium reconstruction off real index levels + contemporaneous
India VIX (candidate 15's approach, reused), plus this candidate's own
25%-of-entry-premium secondary stop walked candle-by-candle.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.options.greeks import compute_greeks  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.orb_scalping.premium import PREMIUM_STOP_PCT, atm_strike, reconstruct_premium  # noqa: E402
from core.orb_scalping.signal import IndexTrade  # noqa: E402

SESSION_START = datetime(2024, 1, 2, 3, 45, tzinfo=timezone.utc)  # 09:15 IST


def bar(i: int, price: float, v: int = 1000) -> OHLCV:
    return OHLCV(timestamp=SESSION_START + timedelta(minutes=5 * i), open=price, high=price,
                 low=price, close=price, volume=v)


# ─── atm_strike ───────────────────────────────────────────────────────────

def test_atm_strike_rounds_to_nearest_interval():
    assert atm_strike(24042.0, interval=50.0) == 24050.0
    assert atm_strike(56742.0, interval=100.0) == 56700.0


# ─── reconstruct_premium: basic entry/exit, no secondary stop hit ────────

def test_reconstruct_premium_matches_direct_compute_greeks_call():
    day_candles = [bar(i, 24000.0 + i) for i in range(20)]
    vix_candles = [bar(i, 15.0) for i in range(20)]  # flat 15% VIX
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=24005.0,
        exit_index=10, exit_price=24010.0,
        initial_stop=23990.0, exit_reason="session_flatten",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry, strike_interval=50.0)

    strike = atm_strike(24005.0, 50.0)
    assert result.strike == strike
    expected_entry = compute_greeks(
        spot=24005.0, strike=strike, days_to_expiry=10,
        implied_vol=0.15, option_type=OptionType.CALL,
    ).theoretical_price
    assert result.entry_premium == expected_entry
    expected_exit = compute_greeks(
        spot=24010.0, strike=strike, days_to_expiry=10,
        implied_vol=0.15, option_type=OptionType.CALL,
    ).theoretical_price
    assert result.exit_premium == expected_exit
    assert result.exit_reason == "session_flatten"


def test_reconstruct_premium_uses_put_for_put_direction():
    day_candles = [bar(i, 24000.0 - i) for i in range(20)]
    vix_candles = [bar(i, 20.0) for i in range(20)]
    index_trade = IndexTrade(
        direction="PUT", entry_index=5, entry_price=23995.0,
        exit_index=10, exit_price=23990.0,
        initial_stop=24035.0, exit_reason="stop",
    )
    expiry = date(2024, 1, 2) + timedelta(days=15)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry, strike_interval=50.0)

    expected_entry = compute_greeks(
        spot=23995.0, strike=result.strike, days_to_expiry=15,
        implied_vol=0.20, option_type=OptionType.PUT,
    ).theoretical_price
    assert result.entry_premium == expected_entry
    assert result.exit_reason == "stop"


def test_reconstruct_premium_uses_contemporaneous_vix_not_a_frozen_entry_snapshot():
    day_candles = [bar(i, 24000.0) for i in range(20)]  # flat index -- isolates the VIX effect
    vix_candles = [bar(i, 10.0 + i * 0.2) for i in range(20)]  # rising VIX path
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=24000.0,
        exit_index=10, exit_price=24000.0,
        initial_stop=23980.0, exit_reason="session_flatten",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry, strike_interval=50.0)

    # same spot/strike/dte at entry and exit, but VIX differs -- a flat-IV
    # design would give identical entry/exit premiums here, this design
    # must not.
    assert result.entry_premium != result.exit_premium
    higher_vol_premium = compute_greeks(
        spot=24000.0, strike=result.strike, days_to_expiry=10,
        implied_vol=(10.0 + 10 * 0.2) / 100.0, option_type=OptionType.CALL,
    ).theoretical_price
    assert result.exit_premium == higher_vol_premium


# ─── Secondary 25% premium stop ───────────────────────────────────────────

def test_premium_stop_triggers_on_iv_crush_even_with_flat_index():
    # Index never moves (would never hit any index-level stop/target), but
    # VIX craters between entry and an intermediate candle -- this must
    # still cut the trade short, since the premium stop is an independent
    # OR condition the index-level signal can't see.
    day_candles = [bar(i, 24000.0) for i in range(20)]
    vix_by_index = {5: 30.0, 6: 30.0, 7: 30.0, 8: 10.0}  # craters at candle 8
    vix_candles = [bar(i, vix_by_index.get(i, 30.0)) for i in range(20)]
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=24000.0,
        exit_index=15, exit_price=24000.0,   # would otherwise flatten much later
        initial_stop=23980.0, exit_reason="session_flatten",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    entry_premium = compute_greeks(
        spot=24000.0, strike=24000.0, days_to_expiry=10,
        implied_vol=0.30, option_type=OptionType.CALL,
    ).theoretical_price
    premium_at_crush = compute_greeks(
        spot=24000.0, strike=24000.0, days_to_expiry=10,
        implied_vol=0.10, option_type=OptionType.CALL,
    ).theoretical_price
    assert premium_at_crush <= entry_premium * (1 - PREMIUM_STOP_PCT), \
        "test fixture must actually breach the 25% threshold"

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry, strike_interval=50.0)

    assert result.exit_reason == "premium_stop"
    assert result.exit_timestamp == day_candles[8].timestamp
    assert result.exit_premium == entry_premium * (1 - PREMIUM_STOP_PCT)


def test_premium_stop_does_not_trigger_when_premium_stays_healthy():
    day_candles = [bar(i, 24000.0 + i) for i in range(20)]  # drifts gently in favor
    vix_candles = [bar(i, 15.0) for i in range(20)]  # flat VIX -- no IV crush
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=24005.0,
        exit_index=12, exit_price=24012.0,
        initial_stop=23985.0, exit_reason="trailing_stop",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry, strike_interval=50.0)

    assert result.exit_reason == "trailing_stop"  # index-level exit reason preserved
    assert result.exit_index_level == 24012.0


def test_premium_stop_takes_precedence_on_the_same_candle_as_index_exit():
    # Both the index-level exit and the premium stop would fire on the same
    # candle -- per premium.py's module docstring, the premium stop takes
    # precedence (a disclosed, conservative tie-break).
    day_candles = [bar(i, 24000.0) for i in range(20)]
    vix_by_index = {5: 30.0, 6: 30.0, 7: 30.0, 8: 10.0}
    vix_candles = [bar(i, vix_by_index.get(i, 30.0)) for i in range(20)]
    index_trade = IndexTrade(
        direction="CALL", entry_index=5, entry_price=24000.0,
        exit_index=8, exit_price=23980.0,   # index-level stop hit on candle 8 too
        initial_stop=23980.0, exit_reason="stop",
    )
    expiry = date(2024, 1, 2) + timedelta(days=10)

    result = reconstruct_premium(index_trade, day_candles, vix_candles, expiry, strike_interval=50.0)

    assert result.exit_reason == "premium_stop"



# ─── 2026-09-30: intraday time-to-expiry (fix 2) ────────────────────────

def test_days_to_expiry_close_is_fractional_and_hits_zero_at_1530_ist():
    from core.orb_scalping.premium import days_to_expiry_close
    d = date(2026, 9, 29)
    assert days_to_expiry_close(d, datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)) == 0.25   # 6h left
    assert days_to_expiry_close(d, datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)) == 0.0
    assert days_to_expiry_close(d, datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)) == 1.0


def test_zero_dte_option_decays_toward_intrinsic_only_with_intraday_dte():
    """The 2026-09-29 shape: a PUT bought on its own expiry day while the
    index drifts up but never hits the index stop. The old max(1, days)
    clamp keeps a full day of time value all session; intraday pricing lets
    it collapse, which is what the real option did (220.35 -> 2.95)."""
    from core.orb_scalping.signal import IndexTrade
    day = date(2026, 9, 29)
    start = datetime(2026, 9, 29, 3, 45, tzinfo=timezone.utc)
    candles = [OHLCV(timestamp=start + timedelta(minutes=5 * i), open=54000 + 3 * i,
                     high=54001 + 3 * i, low=53999 + 3 * i, close=54000 + 3 * i, volume=1)
               for i in range(72)]                                  # to 09:45 UTC, drifting up
    vix = [OHLCV(timestamp=c.timestamp, open=13, high=13, low=13, close=13, volume=1) for c in candles]
    trade = IndexTrade(direction="PUT", entry_index=5, entry_price=candles[5].open,
                       exit_index=71, exit_price=candles[71].close, initial_stop=54500.0,
                       exit_reason="session_flatten")
    old = reconstruct_premium(trade, candles, vix, day, 100.0)
    new = reconstruct_premium(trade, candles, vix, day, 100.0, intraday_dte=True)
    assert new.entry_premium < old.entry_premium          # ~6h of time value, not a full day
    assert new.exit_premium < old.exit_premium            # decayed toward intrinsic by the close
    assert new.exit_reason == "premium_stop"              # and the 25% stop now fires, as it would live


# ─── 2026-09-30: TimeWeights (trading-time decay, post-Fable) ────────────

def test_calendar_weights_reproduce_calendar_days_everywhere():
    from core.orb_scalping.premium import TimeWeights, days_to_expiry_close, effective_days_to_expiry
    expiry = date(2026, 10, 6)                                            # a Tuesday
    for at in (datetime(2026, 9, 30, 4, 10, tzinfo=timezone.utc),        # Wed, in session
               datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),        # Wed night
               datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),        # Fri evening (weekend gap)
               datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc),         # Sunday
               datetime(2026, 10, 6, 9, 55, tzinfo=timezone.utc)):       # expiry, 5 min before close
        assert abs(effective_days_to_expiry(expiry, at, TimeWeights.calendar())
                   - days_to_expiry_close(expiry, at)) < 1e-9, at


def test_trading_252_charges_only_sessions():
    from core.orb_scalping.premium import TimeWeights, effective_days_to_expiry
    w = TimeWeights.trading_252()
    expiry = date(2026, 10, 6)                                            # Tue
    fri_close = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    mon_open = datetime(2026, 10, 5, 3, 45, tzinfo=timezone.utc)
    assert abs(effective_days_to_expiry(expiry, fri_close, w)
               - effective_days_to_expiry(expiry, mon_open, w)) < 1e-9    # weekend costs nothing
    # from Monday's open: two full sessions left (Mon, Tue)
    assert abs(effective_days_to_expiry(expiry, mon_open, w) - 2 * 365 / 252) < 1e-9


def test_heavier_session_weight_decays_a_held_option_faster():
    from core.orb_scalping.premium import TimeWeights, effective_days_to_expiry
    expiry, entry, exit_ = (date(2026, 10, 6), datetime(2026, 10, 1, 4, 10, tzinfo=timezone.utc),
                            datetime(2026, 10, 1, 9, 50, tzinfo=timezone.utc))
    def burned(w):
        return effective_days_to_expiry(expiry, entry, w) - effective_days_to_expiry(expiry, exit_, w)
    assert burned(TimeWeights(0.8, 0.29, 0.6)) > 3 * burned(TimeWeights.calendar())
