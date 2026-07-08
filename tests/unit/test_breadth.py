"""
S5-4 — Real breadth data for regime classification.

Covers the broker `get_quotes` snapshot (LTP + previous close), the
advance/decline counting in core/regime/fetcher._fetch_breadth, and the
neutral-fallback guards (empty universe, unsupported broker, too-small
sample).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.brokers.base import Quote
from core.brokers.fyers import FyersBroker, _QUOTES_CHUNK
from core.regime.fetcher import (
    _fetch_breadth, fetch_regime_inputs, _neutral_breadth, MIN_BREADTH_SAMPLE,
)
from core.regime.models import BreadthData


# ─── Quote dataclass ──────────────────────────────────────────────────────────

class TestQuote:

    def test_advancing(self):
        q = Quote(symbol="X", ltp=105.0, prev_close=100.0)
        assert q.is_advancing is True
        assert q.is_declining is False

    def test_declining(self):
        q = Quote(symbol="X", ltp=95.0, prev_close=100.0)
        assert q.is_declining is True
        assert q.is_advancing is False

    def test_unchanged_is_neither(self):
        q = Quote(symbol="X", ltp=100.0, prev_close=100.0)
        assert q.is_advancing is False
        assert q.is_declining is False

    def test_zero_prev_close_is_neither(self):
        """Missing reference data must never be counted as advancing."""
        q = Quote(symbol="X", ltp=100.0, prev_close=0.0)
        assert q.is_advancing is False
        assert q.is_declining is False


# ─── Fyers get_quotes ─────────────────────────────────────────────────────────

def _make_fyers() -> FyersBroker:
    broker = FyersBroker({"credentials": {"api_key": "x"}})
    broker._connected = True
    broker._client = MagicMock()
    return broker


class TestFyersGetQuotes:

    def test_parses_lp_and_prev_close(self):
        broker = _make_fyers()
        broker._client.quotes.return_value = {
            "code": 200,
            "d": [
                {"n": "NSE:RELIANCE-EQ",
                 "v": {"lp": 105.0, "prev_close_price": 100.0, "ch": 5.0, "chp": 5.0}},
                {"n": "NSE:TCS-EQ",
                 "v": {"lp": 90.0, "prev_close_price": 100.0, "ch": -10.0, "chp": -10.0}},
            ],
        }
        quotes = broker.get_quotes(["RELIANCE", "TCS"])
        assert quotes["RELIANCE"].is_advancing
        assert quotes["TCS"].is_declining
        assert quotes["RELIANCE"].prev_close == 100.0
        assert quotes["TCS"].change_pct == -10.0

    def test_chunks_requests_over_50_symbols(self):
        broker = _make_fyers()
        broker._client.quotes.return_value = {"code": 200, "d": []}
        symbols = [f"SYM{i}" for i in range(_QUOTES_CHUNK * 2 + 5)]  # 105 symbols
        broker.get_quotes(symbols)
        # 105 symbols → ceil(105/50) = 3 batched calls
        assert broker._client.quotes.call_count == 3

    def test_raises_on_api_error(self):
        from core.brokers.base import BrokerError
        broker = _make_fyers()
        broker._client.quotes.return_value = {"code": -50, "message": "bad"}
        with pytest.raises(BrokerError):
            broker.get_quotes(["RELIANCE"])


# ─── _fetch_breadth counting + fallbacks ──────────────────────────────────────

class _QuoteBroker:
    """Duck-typed broker exposing only get_quotes — all _fetch_breadth needs."""

    def __init__(self, quotes: dict[str, Quote]):
        self._quotes = quotes

    def get_quotes(self, symbols):
        return {s: self._quotes[s] for s in symbols if s in self._quotes}


def _quotes_for(advancing: int, declining: int, unchanged: int = 0) -> dict[str, Quote]:
    q, i = {}, 0
    for _ in range(advancing):
        q[f"S{i}"] = Quote(f"S{i}", ltp=110.0, prev_close=100.0); i += 1
    for _ in range(declining):
        q[f"S{i}"] = Quote(f"S{i}", ltp=90.0, prev_close=100.0); i += 1
    for _ in range(unchanged):
        q[f"S{i}"] = Quote(f"S{i}", ltp=100.0, prev_close=100.0); i += 1
    return q


class TestFetchBreadth:

    def test_counts_advance_decline_unchanged(self):
        quotes = _quotes_for(advancing=30, declining=15, unchanged=5)
        broker = _QuoteBroker(quotes)
        result = asyncio.run(_fetch_breadth(broker, list(quotes.keys())))
        assert result.advance_count == 30
        assert result.decline_count == 15
        assert result.unchanged_count == 5
        assert result.ad_ratio == 2.0

    def test_drops_symbols_with_bad_reference_data(self):
        quotes = _quotes_for(advancing=25, declining=10)
        quotes["BAD1"] = Quote("BAD1", ltp=100.0, prev_close=0.0)     # no prev close
        quotes["BAD2"] = Quote("BAD2", ltp=0.0, prev_close=100.0)     # no ltp (suspended)
        broker = _QuoteBroker(quotes)
        result = asyncio.run(_fetch_breadth(broker, list(quotes.keys())))
        assert result.advance_count == 25
        assert result.decline_count == 10
        assert result.unchanged_count == 0

    def test_empty_universe_returns_neutral(self):
        broker = _QuoteBroker({})
        result = asyncio.run(_fetch_breadth(broker, []))
        assert result == _neutral_breadth()

    def test_too_small_sample_returns_neutral(self):
        quotes = _quotes_for(advancing=MIN_BREADTH_SAMPLE - 5, declining=2)
        broker = _QuoteBroker(quotes)
        result = asyncio.run(_fetch_breadth(broker, list(quotes.keys())))
        assert result == _neutral_breadth()


# ─── fetch_regime_inputs fallback when broker lacks get_quotes ─────────────────

class TestBreadthIntegrationFallback:

    def test_unsupported_broker_degrades_to_neutral(self):
        """A broker whose get_quotes raises NotImplementedError must not
        break regime classification — breadth falls back to neutral."""
        from core.regime.fetcher import _fetch_nifty, _fetch_vix
        from core.regime.models import NiftyData, VIXData

        broker = MagicMock()

        nifty = NiftyData(ltp=22000, ema_20=21800, ema_50=21500,
                          ema_200=20000, slope_5d=1.0, atr_14=200, atr_pct=0.9)
        vix = VIXData(current=13.0, ma_10=13.0, trend="FLAT", percentile_52w=30.0)

        # Broker doesn't override get_quotes → base raises NotImplementedError.
        broker.get_quotes.side_effect = NotImplementedError("no quotes")

        with patch("core.regime.fetcher._fetch_nifty",
                   new_callable=AsyncMock, return_value=nifty), \
             patch("core.regime.fetcher._fetch_vix",
                   new_callable=AsyncMock, return_value=vix):
            inputs = asyncio.run(
                fetch_regime_inputs(broker, breadth_universe=["A", "B", "C"])
            )

        assert inputs.breadth == _neutral_breadth()
        assert inputs.nifty is nifty


# ─── Classifier carries A/D counts through to the result ──────────────────────

class TestClassifierBreadthPassthrough:

    def test_result_exposes_advance_decline_counts(self):
        from core.regime.classifier import classify
        from core.regime.models import RegimeInputs, NiftyData, VIXData

        inputs = RegimeInputs(
            nifty=NiftyData(ltp=22000, ema_20=21800, ema_50=21500,
                            ema_200=20000, slope_5d=1.0, atr_14=200, atr_pct=0.9),
            vix=VIXData(current=13.0, ma_10=13.0, trend="FLAT", percentile_52w=30.0),
            breadth=BreadthData(advance_count=310, decline_count=170, unchanged_count=20),
        )
        result = classify(inputs)
        assert result.advance_count == 310
        assert result.decline_count == 170
        assert result.unchanged_count == 20
        assert result.ad_ratio == pytest.approx(310 / 170)
