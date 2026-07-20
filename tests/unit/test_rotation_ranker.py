"""
core/rotation/ranker.py — pure ranking/diff logic shared between the S8-3
backtest (scripts/backtest_rs_momentum.py) and live execution
(core/rotation/executor.py, once built). Extracted from the backtest script
so live can never silently re-implement (and drift from) the tested rule.
"""

from datetime import datetime, timezone

from core.brokers.base import OHLCV
from core.rotation.ranker import (
    SymbolSeries, diff_target_basket, rank_universe,
    rolling_high_series, value_as_of,
)


def _build_series(daily: list[OHLCV], window: int) -> SymbolSeries:
    """Same shape as ranker.build_symbol_series, but with an explicit
    (smaller) window so short test fixtures can actually warm up instead of
    needing 252 bars like the real LOOKBACK_DAYS default."""
    return SymbolSeries(
        dates=[c.timestamp for c in daily],
        closes=[c.close for c in daily],
        highs=rolling_high_series(daily, window=window),
    )


def _candle(day: int, high: float, close: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 1, day, tzinfo=timezone.utc) if day <= 28
        else datetime(2026, 2, day - 28, tzinfo=timezone.utc),
        open=close, high=high, low=close, close=close, volume=1000,
    )


class TestRollingHighSeries:

    def test_none_until_warmed_up(self):
        candles = [_candle(d, 100.0, 100.0) for d in range(1, 4)]
        highs = rolling_high_series(candles, window=5)
        assert highs == [None, None, None]

    def test_rolling_max_once_warmed_up(self):
        closes_highs = [10, 20, 15, 30, 25]
        candles = [
            OHLCV(timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                  open=h, high=h, low=h, close=h, volume=1000)
            for i, h in enumerate(closes_highs)
        ]
        highs = rolling_high_series(candles, window=3)
        # First two None (not warmed up), then rolling max of the trailing 3.
        assert highs == [None, None, 20, 30, 30]


class TestValueAsOf:

    def test_returns_close_and_high_at_exact_date(self):
        candles = [_candle(d, 100.0 + d, 90.0 + d) for d in range(1, 10)]
        series = _build_series(candles, window=3)
        result = value_as_of(series, datetime(2026, 1, 5, tzinfo=timezone.utc))
        assert result is not None
        close, high = result
        assert close == 95.0

    def test_none_before_any_data(self):
        candles = [_candle(d, 100.0, 90.0) for d in range(5, 10)]
        series = _build_series(candles, window=3)
        result = value_as_of(series, datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert result is None

    def test_uses_last_available_bar_for_gaps(self):
        """A listing gap/halt shouldn't return None for dates after the gap
        — value_as_of should fall back to the most recent prior bar."""
        candles = [_candle(1, 100.0, 90.0), _candle(5, 110.0, 95.0)]
        series = _build_series(candles, window=1)
        result = value_as_of(series, datetime(2026, 1, 3, tzinfo=timezone.utc))
        assert result is not None
        close, _high = result
        assert close == 90.0


class TestRankUniverse:

    def test_ranks_by_nearness_to_high_highest_first(self):
        as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = {
            "AT_HIGH": _series_with_value(as_of, close=100.0, high=100.0),
            "FAR": _series_with_value(as_of, close=50.0, high=100.0),
            "NEAR": _series_with_value(as_of, close=90.0, high=100.0),
        }
        ranked = rank_universe(series, as_of, top_n=3)
        assert ranked == ["AT_HIGH", "NEAR", "FAR"]

    def test_top_n_truncates(self):
        as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = {
            f"S{i}": _series_with_value(as_of, close=float(i), high=100.0)
            for i in range(10)
        }
        ranked = rank_universe(series, as_of, top_n=3)
        assert len(ranked) == 3
        assert ranked == ["S9", "S8", "S7"]

    def test_excludes_unwarmed_symbols(self):
        as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = {
            "READY": _series_with_value(as_of, close=100.0, high=100.0),
            "NOT_READY": _build_series([_candle(1, 100.0, 90.0)], window=252),  # 1 bar, never warms up
        }
        ranked = rank_universe(series, as_of, top_n=5)
        assert ranked == ["READY"]


def _series_with_value(as_of: datetime, close: float, high: float):
    """A minimal warmed-up SymbolSeries with an exact (close, high) as of
    `as_of` — bypasses the 252-bar rolling-window warmup for ranking tests
    that only care about the scoring/ordering rule, not warmup mechanics."""
    from core.rotation.ranker import SymbolSeries
    return SymbolSeries(dates=[as_of], closes=[close], highs=[high])


class TestDiffTargetBasket:

    def test_buys_are_target_minus_current(self):
        plan = diff_target_basket(current_holdings={"A", "B"}, target_basket=["B", "C", "D"])
        assert set(plan.buys) == {"C", "D"}

    def test_sells_are_current_minus_target(self):
        plan = diff_target_basket(current_holdings={"A", "B"}, target_basket=["B", "C"])
        assert plan.sells == ["A"]

    def test_buys_preserve_target_basket_rank_order(self):
        """Rank order matters for a capital-constrained executor sizing the
        highest-conviction new entrants first."""
        plan = diff_target_basket(current_holdings=set(), target_basket=["BEST", "SECOND", "THIRD"])
        assert plan.buys == ["BEST", "SECOND", "THIRD"]

    def test_no_overlap_change_when_holdings_equal_target(self):
        plan = diff_target_basket(current_holdings={"A", "B"}, target_basket=["A", "B"])
        assert plan.buys == []
        assert plan.sells == []

    def test_accepts_list_for_current_holdings(self):
        plan = diff_target_basket(current_holdings=["A"], target_basket=["A", "B"])
        assert plan.buys == ["B"]
        assert plan.sells == []
