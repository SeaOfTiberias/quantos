"""
Stage A — Weekly Darvas Discovery Scanner Unit Tests
──────────────────────────────────────────────────────
Ported methodology from the user's DarvasTrader project onto Fyers daily
candles. Mirrors the style of tests/unit/test_darvas.py.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from core.brokers.base import OHLCV
from core.darvas.weekly_discovery import (
    DEFAULT_CONFIG, WeeklyDiscoveryScanner, _to_weekly, _detect_box, analyse_symbol,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _business_days(start: datetime, n: int) -> list[datetime]:
    """n consecutive Mon-Fri dates starting at `start` (which must itself
    be a Monday) — keeps weekly resampling boundaries clean and
    predictable for these tests."""
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def make_daily(ts: datetime, close: float, high: float, low: float,
               volume: int = 100_000) -> OHLCV:
    return OHLCV(timestamp=ts, open=close, high=high, low=low, close=close, volume=volume)


MONDAY = datetime(2024, 1, 1, tzinfo=timezone.utc)  # a real Monday


def build_flat_box_series(final_week_days: list[dict]) -> list[OHLCV]:
    """
    12 perfectly flat weeks (high=101, low=99, close=100, vol=100k) —
    enough to confirm a weekly Darvas box at ceiling=101/floor=99 well
    before the end — followed by one final week whose 5 days are given
    explicitly by `final_week_days` (each a dict of close/high/low/volume).
    """
    dates = _business_days(MONDAY, 12 * 5 + 5)
    candles = []
    for i in range(12 * 5):
        candles.append(make_daily(dates[i], close=100.0, high=101.0, low=99.0))
    for i, day in enumerate(final_week_days):
        candles.append(make_daily(dates[12 * 5 + i], **day))
    return candles


def build_trending_series() -> list[OHLCV]:
    """13 weeks where each week's high/low strictly exceeds the last —
    ceiling/floor confirmation counts reset every week, so no box ever
    confirms (status stays BOX FORMING)."""
    dates = _business_days(MONDAY, 13 * 5)
    candles = []
    for week in range(13):
        high = 100.0 + week * 5
        low = 95.0 + week * 5
        close = 98.0 + week * 5
        for d in range(5):
            candles.append(make_daily(dates[week * 5 + d], close=close, high=high, low=low))
    return candles


# ─── Weekly resample ──────────────────────────────────────────────────────────

class TestWeeklyResample:

    def test_resamples_five_days_into_one_bar(self):
        dates = _business_days(MONDAY, 10)
        daily = [
            make_daily(dates[0], close=100, high=102, low=98, volume=10),
            make_daily(dates[1], close=101, high=103, low=99, volume=20),
            make_daily(dates[2], close=99,  high=104, low=97, volume=30),
            make_daily(dates[3], close=105, high=106, low=100, volume=40),
            make_daily(dates[4], close=103, high=105, low=101, volume=50),  # Friday — week 1 close
            make_daily(dates[5], close=110, high=112, low=109, volume=60),
            make_daily(dates[6], close=111, high=113, low=110, volume=70),
            make_daily(dates[7], close=109, high=114, low=108, volume=80),
            make_daily(dates[8], close=115, high=116, low=112, volume=90),
            make_daily(dates[9], close=120, high=121, low=118, volume=100),  # Friday — week 2 close
        ]
        weekly = _to_weekly(daily)
        assert len(weekly) == 2

        w1, w2 = weekly
        assert w1.high == 106
        assert w1.low == 97
        assert w1.close == 103          # last day (Friday) of week 1
        assert w1.volume == 150         # sum of week 1 volumes

        assert w2.high == 121
        assert w2.low == 108
        assert w2.close == 120
        assert w2.volume == 400

    def test_empty_input_returns_empty(self):
        assert _to_weekly([]) == []


# ─── Box state machine ─────────────────────────────────────────────────────────

class TestDetectBox:

    def test_confirms_box_after_ceil_and_floor_bars(self):
        # 5 identical weekly bars: high=101/low=99 confirms after 3
        # confirming weeks (index 4), per DEFAULT_CONFIG's ceil_bars/floor_bars=3.
        weekly = [
            OHLCV(timestamp=MONDAY + timedelta(weeks=i), open=100, high=101,
                  low=99, close=100, volume=500_000)
            for i in range(5)
        ]
        state = _detect_box(weekly, DEFAULT_CONFIG)
        assert state.box_ceiling == 101
        assert state.box_floor == 99

    def test_no_box_when_trending(self):
        # Every week sets a new high/low — confirmation never accumulates.
        weekly = [
            OHLCV(timestamp=MONDAY + timedelta(weeks=i), open=100 + i * 5,
                  high=101 + i * 5, low=99 + i * 5, close=100 + i * 5, volume=500_000)
            for i in range(8)
        ]
        state = _detect_box(weekly, DEFAULT_CONFIG)
        assert state.box_ceiling is None
        # Ceiling confirmation keeps resetting (every week sets a new high),
        # so it can never reach ceil_bars — that alone is enough to prevent
        # a box from ever confirming, regardless of how the floor behaves.
        assert state.ceil_conf == 0


# ─── Full per-symbol analysis ──────────────────────────────────────────────────

class TestAnalyseSymbol:

    def test_insufficient_history_returns_none(self):
        dates = _business_days(MONDAY, 30)
        daily = [make_daily(d, close=100, high=101, low=99) for d in dates]
        assert analyse_symbol("TEST", daily) is None

    def test_trending_series_is_box_forming(self):
        daily = build_trending_series()
        result = analyse_symbol("TEST", daily)
        assert result is not None
        assert result.status == "BOX FORMING"
        # No box has *confirmed* (ceil_conf never reaches ceil_bars since
        # every week sets a new high) — box_ceiling here reports the
        # still-pending ceiling being tracked, not a confirmed one.
        assert result.box_ceiling == 155.0
        assert result.ceil_conf == 0
        assert result.weeks_to_confirm == 3

    def test_fresh_breakout_detected(self):
        final_week = [
            {"close": 100, "high": 101, "low": 99},
            {"close": 100, "high": 101, "low": 99},
            {"close": 100, "high": 101, "low": 99},
            {"close": 100, "high": 101, "low": 99},
            {"close": 115, "high": 116, "low": 100, "volume": 300_000},  # Friday breakout
        ]
        daily = build_flat_box_series(final_week)
        result = analyse_symbol("TEST", daily)
        assert result is not None
        assert result.status == "FRESH BREAKOUT"
        assert result.box_ceiling == 101
        assert result.box_floor == 99
        assert result.rr_ratio is not None and result.rr_ratio > 0

    def test_approaching_hot_tier(self):
        final_week = [
            {"close": 100, "high": 101, "low": 99},
            {"close": 100, "high": 101, "low": 99},
            {"close": 100, "high": 101, "low": 99},
            {"close": 100, "high": 101, "low": 99},
            {"close": 99.5, "high": 100, "low": 99, "volume": 250_000},  # close to ceiling, high volume
        ]
        daily = build_flat_box_series(final_week)
        result = analyse_symbol("TEST", daily)
        assert result is not None
        assert result.status == "APPROACHING"
        assert result.alert_tier == "HOT"
        assert 0 < result.dist_to_ceil <= DEFAULT_CONFIG["hot_dist_pct"]

    def test_box_too_wide_is_rejected(self):
        cfg = {**DEFAULT_CONFIG, "max_box_width": 1.0}   # our flat box is ~2% wide
        final_week = [{"close": 100, "high": 101, "low": 99}] * 5
        daily = build_flat_box_series(final_week)
        assert analyse_symbol("TEST", daily, cfg) is None


# ─── Scanner — real asyncio.run() call pattern ────────────────────────────────

class TestWeeklyDiscoveryScanner:
    """
    Regression coverage for a live bug: agent/main.py constructs
    WeeklyDiscoveryScanner synchronously (no event loop running yet), then
    calls asyncio.run(scanner.scan_universe(...)), which spins up a brand
    new loop. Constructing the semaphore in __init__ bound it to whatever
    loop happened to be "current" at construction time, not the one
    scan_universe actually runs on — every _scan_one() call failed with
    "Future attached to a different loop" and scan_universe silently
    returned an empty list (the exception is caught by
    return_exceptions=True and just logged). These tests call
    asyncio.run() from a plain sync test function specifically to
    reproduce that construction pattern — an `async def` test would not
    have caught this, since pytest-asyncio already has a loop running by
    the time the scanner is constructed.
    """

    def _mock_broker(self):
        broker = MagicMock()
        final_week = [{"close": 100, "high": 101, "low": 99}] * 5
        broker.get_historical_data.return_value = build_flat_box_series(final_week)
        return broker

    def test_scan_universe_via_asyncio_run_from_sync_context(self):
        broker = self._mock_broker()
        scanner = WeeklyDiscoveryScanner(broker)   # constructed with no loop running

        results = asyncio.run(scanner.scan_universe(["RELIANCE", "TCS", "INFY"]))

        assert len(results) == 3
        assert broker.get_historical_data.call_count == 3

    def test_scan_universe_can_run_more_than_once(self):
        """Same scanner instance, two separate asyncio.run() calls — each
        must get its own correctly-bound semaphore."""
        broker = self._mock_broker()
        scanner = WeeklyDiscoveryScanner(broker)

        first = asyncio.run(scanner.scan_universe(["RELIANCE"]))
        second = asyncio.run(scanner.scan_universe(["TCS"]))

        assert len(first) == 1
        assert len(second) == 1
