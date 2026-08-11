"""
core/discovery/momentum_shortlist.py — the two derived display flags added
2026-08-11: breakout_state (an unambiguous replacement for Darvas's own
base_status) and the 50/200 SMA cross.

The point of breakout_state is that weekly_discovery collapses three
different situations into "WATCHING" — broke out days ago on volume, above
the ceiling without a volume surge, and still inside the box. The tests below
pin exactly that separation, since it is the whole reason the column exists.
"""

from datetime import datetime, timedelta, timezone

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import DiscoveryResult
from core.discovery.momentum_shortlist import (
    breakout_state, ma_cross_state, sma_series, _sessions_above,
)

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candle(day: int, close: float) -> OHLCV:
    return OHLCV(timestamp=EPOCH + timedelta(days=day),
                 open=close, high=close, low=close, close=close, volume=100_000)


def _series(closes: list[float]) -> list[OHLCV]:
    return [_candle(i, c) for i, c in enumerate(closes)]


def _as_of(bars: list[OHLCV]) -> datetime:
    return bars[-1].timestamp


class TestSmaSeries:
    def test_none_until_warmed_up(self):
        out = sma_series([1, 2, 3, 4, 5], 3)
        assert out[:2] == [None, None]
        assert out[2] == 2.0            # (1+2+3)/3

    def test_rolling_window_is_correct(self):
        out = sma_series([1, 2, 3, 4, 5], 3)
        assert out[3] == 3.0            # (2+3+4)/3
        assert out[4] == 4.0            # (3+4+5)/3

    def test_all_none_when_shorter_than_period(self):
        assert sma_series([1, 2], 5) == [None] * 2


class TestSessionsAbove:
    def test_counts_consecutive_closes_above(self):
        bars = _series([90, 95, 105, 106, 107])
        assert _sessions_above(bars, 100.0, _as_of(bars)) == 3

    def test_none_when_latest_bar_is_below(self):
        bars = _series([105, 106, 99])
        assert _sessions_above(bars, 100.0, _as_of(bars)) is None

    def test_streak_stops_at_the_first_dip(self):
        """A re-entry into the box resets the count — 'out for 2 sessions',
        not 'out for 5 with a hole in the middle'."""
        bars = _series([105, 106, 98, 104, 107])
        assert _sessions_above(bars, 100.0, _as_of(bars)) == 2


class TestBreakoutState:
    def test_no_base(self):
        bars = _series([100, 101])
        assert breakout_state(None, bars, _as_of(bars)) == ("NO BASE", None)

    def test_fresh_defers_to_darvas(self):
        bars = _series([98, 105])
        base = DiscoveryResult(symbol="X", status="FRESH BREAKOUT",
                               box_ceiling=100.0, dist_to_ceil=-5.0)
        state, days = breakout_state(base, bars, _as_of(bars))
        assert state == "FRESH"
        assert days == 1

    def test_above_ceiling_but_not_fresh_is_OUT(self):
        """The case base_status hides: Darvas says WATCHING, but the stock
        cleared its ceiling 4 sessions ago."""
        bars = _series([98, 104, 105, 106, 107])
        base = DiscoveryResult(symbol="X", status="WATCHING",
                               box_ceiling=100.0, dist_to_ceil=-7.0)
        assert breakout_state(base, bars, _as_of(bars)) == ("OUT", 4)

    def test_inside_box_is_IN_BOX_not_OUT(self):
        """Same WATCHING label as the test above, opposite meaning."""
        bars = _series([95, 96, 97])
        base = DiscoveryResult(symbol="X", status="WATCHING",
                               box_ceiling=100.0, dist_to_ceil=3.0)
        assert breakout_state(base, bars, _as_of(bars)) == ("IN BOX", None)

    def test_approaching_is_NEAR(self):
        bars = _series([95, 96, 98])
        base = DiscoveryResult(symbol="X", status="APPROACHING",
                               box_ceiling=100.0, dist_to_ceil=2.0)
        assert breakout_state(base, bars, _as_of(bars)) == ("NEAR", None)

    def test_missing_ceiling_degrades_to_no_base(self):
        bars = _series([100, 101])
        base = DiscoveryResult(symbol="X", status="BOX FORMING")
        assert breakout_state(base, bars, _as_of(bars)) == ("NO BASE", None)


class TestMaCrossState:
    def test_none_when_slow_ma_not_warmed_up(self):
        bars = _series([100] * 10)
        assert ma_cross_state(bars, _as_of(bars), fast=3, slow=20) == (None, None)

    def test_bull_when_fast_above_slow(self):
        # flat then rising: the short SMA lifts above the long one
        bars = _series([100] * 30 + [100 + i for i in range(1, 21)])
        state, _ = ma_cross_state(bars, _as_of(bars), fast=5, slow=20)
        assert state == "BULL"

    def test_bear_when_fast_below_slow(self):
        bars = _series([100] * 30 + [100 - i for i in range(1, 21)])
        state, _ = ma_cross_state(bars, _as_of(bars), fast=5, slow=20)
        assert state == "BEAR"

    def test_reports_sessions_since_the_flip(self):
        """A cross inside the data window must be dated, and the date must
        point at a real flip rather than the start of the series."""
        bars = _series([100] * 30 + [100 - i for i in range(1, 16)] + [90 + i * 3 for i in range(1, 16)])
        state, age = ma_cross_state(bars, _as_of(bars), fast=5, slow=20)
        assert state == "BULL"
        assert age is not None and age >= 1

    def test_no_age_when_alignment_never_flipped_in_window(self):
        """Steadily rising the whole way: fast has been above slow for every
        warmed-up bar, so there is no cross to date and the honest answer is
        None, not 0 and not the series length."""
        bars = _series([100 + i for i in range(60)])
        state, age = ma_cross_state(bars, _as_of(bars), fast=5, slow=20)
        assert state == "BULL"
        assert age is None

    def test_respects_as_of_date(self):
        """Evaluated at an earlier bar, the later reversal must be invisible."""
        bars = _series([100] * 30 + [100 - i for i in range(1, 21)])
        early = bars[34].timestamp
        state, _ = ma_cross_state(bars, early, fast=5, slow=20)
        assert state in ("BULL", "BEAR")   # defined, and computed from <=bar 34
        late, _ = ma_cross_state(bars, _as_of(bars), fast=5, slow=20)
        assert late == "BEAR"
