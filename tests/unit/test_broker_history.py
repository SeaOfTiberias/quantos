"""
core/brokers/history.py — chunked daily history.

Exists because a single 600-day daily request is rejected by Fyers outright
('Date range cannot exceed 366 days'), and two callers shipped doing exactly
that on 2026-08-14. The tests that matter here are the ones asserting no
individual request exceeds the cap — that is the whole point of the module.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from core.brokers.base import OHLCV
from core.brokers.history import MAX_CHUNK_DAYS, fetch_daily

_END = datetime(2026, 8, 14, tzinfo=timezone.utc)

# Fyers' real cap. MAX_CHUNK_DAYS sits just under it deliberately; asserting
# against the documented limit rather than our own constant means shrinking
# ours stays legal while widening it past the broker's does not.
FYERS_CAP_DAYS = 366


def _broker(bars_per_day=1):
    """A broker that enforces Fyers' range cap, like the real one."""
    broker = MagicMock()

    def _history(symbol, timeframe, from_date, to_date):
        if (to_date - from_date).days > FYERS_CAP_DAYS:
            raise RuntimeError("Date range cannot exceed 366 days for 1D")
        out, day = [], from_date
        while day <= to_date:
            out.append(OHLCV(timestamp=day, open=1.0, high=1.0,
                             low=1.0, close=1.0, volume=1))
            day += timedelta(days=1 // bars_per_day or 1)
        return out

    broker.get_historical_data.side_effect = _history
    return broker


class TestChunking:

    def test_a_600_day_range_is_split_rather_than_rejected(self):
        candles = fetch_daily(_broker(), "TEST", _END - timedelta(days=600), _END)
        assert candles                      # the original bug: this raised

    def test_no_single_request_exceeds_the_brokers_cap(self):
        broker = _broker()
        fetch_daily(broker, "TEST", _END - timedelta(days=900), _END)
        for call in broker.get_historical_data.call_args_list:
            _symbol, _tf, start, end = call[0]
            assert (end - start).days <= FYERS_CAP_DAYS

    def test_a_short_range_stays_one_request(self):
        broker = _broker()
        fetch_daily(broker, "TEST", _END - timedelta(days=30), _END)
        assert broker.get_historical_data.call_count == 1

    def test_requests_the_daily_timeframe_the_adapters_accept(self):
        from core.brokers.fyers import _TF_MAP

        broker = _broker()
        fetch_daily(broker, "TEST", _END - timedelta(days=30), _END)
        assert broker.get_historical_data.call_args[0][1] in _TF_MAP

    def test_chunk_size_is_under_the_cap(self):
        assert MAX_CHUNK_DAYS < FYERS_CAP_DAYS


class TestSplicing:

    def test_candles_come_back_oldest_first(self):
        candles = fetch_daily(_broker(), "TEST", _END - timedelta(days=800), _END)
        stamps = [c.timestamp for c in candles]
        assert stamps == sorted(stamps)

    def test_overlapping_chunks_do_not_double_count_a_bar(self):
        """Chunk boundaries can return the same session twice; a duplicated
        bar would quietly corrupt every moving average computed on top."""
        broker = MagicMock()

        def _history(symbol, timeframe, from_date, to_date):
            # Deliberately ignores the window and always returns the same
            # three bars, the pathological version of an overlap.
            return [OHLCV(timestamp=_END - timedelta(days=i), open=1.0, high=1.0,
                          low=1.0, close=1.0, volume=1) for i in range(3)]

        broker.get_historical_data.side_effect = _history
        candles = fetch_daily(broker, "TEST", _END - timedelta(days=800), _END)
        assert len(candles) == 3

    def test_an_empty_range_asks_the_broker_nothing(self):
        broker = _broker()
        assert fetch_daily(broker, "TEST", _END, _END) == []
        broker.get_historical_data.assert_not_called()


class TestErrorsSurface:

    def test_a_broker_error_propagates(self):
        """Callers on money paths fail closed, so swallowing an error here
        would turn a broken feed into a silent veto."""
        import pytest

        broker = MagicMock()
        broker.get_historical_data.side_effect = RuntimeError("token expired")
        with pytest.raises(RuntimeError, match="token expired"):
            fetch_daily(broker, "TEST", _END - timedelta(days=30), _END)
