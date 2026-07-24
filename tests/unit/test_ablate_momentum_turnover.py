"""
scripts/ablate_momentum_turnover.py — quarterly_rebalance_dates() unit tests.
The only new logic in the momentum turnover ablation; everything else it
calls (rank_universe, simulate_portfolio, nifty500_reconstitution) is
reused unchanged from S8-3's own tested modules.
"""

from datetime import datetime, timedelta, timezone

from core.brokers.base import OHLCV
from scripts.ablate_momentum_turnover import quarterly_rebalance_dates


def _candle(dt: datetime) -> OHLCV:
    return OHLCV(timestamp=dt, open=100, high=101, low=99, close=100, volume=1000)


def _daily_range(start: datetime, n_days: int, skip_weekends: bool = True) -> list[OHLCV]:
    candles = []
    d = start
    while len(candles) < n_days:
        if not skip_weekends or d.weekday() < 5:
            candles.append(_candle(d))
        d = d + timedelta(days=1)
    return candles


class TestQuarterlyRebalanceDates:

    def test_empty_before_warmup(self):
        candles = [_candle(datetime(2024, 1, 2, tzinfo=timezone.utc))]
        assert quarterly_rebalance_dates(candles, warmup_days=252) == []

    def test_picks_last_trading_day_of_each_quarter(self):
        # Q1 2024: Jan-Mar. Q2: Apr-Jun. Build a small set of candles
        # spanning a quarter boundary with obvious "last day" markers.
        candles = [
            _candle(datetime(2024, 3, 27, tzinfo=timezone.utc)),
            _candle(datetime(2024, 3, 28, tzinfo=timezone.utc)),  # last trading day of Q1
            _candle(datetime(2024, 4, 1, tzinfo=timezone.utc)),
            _candle(datetime(2024, 4, 2, tzinfo=timezone.utc)),   # last day in this sample (Q2)
        ]
        dates = quarterly_rebalance_dates(candles, warmup_days=0)
        assert datetime(2024, 3, 28, tzinfo=timezone.utc) in dates
        assert datetime(2024, 4, 2, tzinfo=timezone.utc) in dates
        assert len(dates) == 2

    def test_last_candle_always_included(self):
        """The final candle in the series is always a rebalance date, even
        mid-quarter — same convention as the weekly rebalance_dates()."""
        candles = [
            _candle(datetime(2024, 5, 10, tzinfo=timezone.utc)),
            _candle(datetime(2024, 5, 13, tzinfo=timezone.utc)),  # mid-quarter, last in series
        ]
        dates = quarterly_rebalance_dates(candles, warmup_days=0)
        assert dates[-1] == datetime(2024, 5, 13, tzinfo=timezone.utc)

    def test_respects_warmup_days(self):
        candles = [_candle(datetime(2024, 1, 2 + i, tzinfo=timezone.utc)) for i in range(10)]
        dates = quarterly_rebalance_dates(candles, warmup_days=5)
        # Only candles[5:] are eligible -- the last of those is a rebalance date.
        assert dates[-1] == candles[-1].timestamp
        assert all(d >= candles[5].timestamp for d in dates)

    def test_far_fewer_dates_than_weekly_over_a_year(self):
        """Sanity check on the whole point of this ablation: quarterly
        cadence produces roughly 4/year, not ~52/year like weekly."""
        candles = _daily_range(datetime(2023, 1, 2, tzinfo=timezone.utc), 260)
        dates = quarterly_rebalance_dates(candles, warmup_days=0)
        assert 3 <= len(dates) <= 5
