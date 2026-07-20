"""
FyersBroker — regression test for the get_historical_data date_format bug.

Found via agent/debug_discovery_scan.py during the two-stage Darvas
pipeline's first live run: date_format was "1" (meaning range_from/
range_to should be "yyyy-mm-dd" strings) while the payload actually sent
epoch integers — Fyers rejected every single history call with error
code -50. This was a pre-existing bug never exercised live before,
since the only prior callers of get_historical_data("1d", ...) were
never actually wired into production.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.brokers.base import Order, OrderDirection, OrderType, ProductType
from core.brokers.fyers import FyersBroker


def _connected_broker() -> FyersBroker:
    """A FyersBroker with a mock Fyers SDK client, bypassing the real
    connect() OAuth flow — same pattern as any other broker-adapter unit
    test that only needs to inspect the outgoing request payload."""
    broker = FyersBroker(config={})
    broker._client = MagicMock()
    broker._client.history.return_value = {"code": 200, "candles": []}
    broker._connected = True
    return broker


class TestGetHistoricalDataPayload:

    def test_date_format_matches_epoch_range_values(self):
        """range_from/range_to are sent as Unix epoch seconds, so
        date_format must be "0" — not "1" (yyyy-mm-dd strings)."""
        broker = _connected_broker()
        from_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_date = datetime(2026, 7, 1, tzinfo=timezone.utc)

        broker.get_historical_data("RELIANCE", "1d", from_date, to_date)

        sent = broker._client.history.call_args.kwargs["data"]
        assert sent["date_format"] == "0"
        assert sent["range_from"] == str(int(from_date.timestamp()))
        assert sent["range_to"] == str(int(to_date.timestamp()))

    def test_symbol_and_resolution_formatted_for_fyers(self):
        broker = _connected_broker()
        from_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        to_date = datetime(2026, 1, 8, tzinfo=timezone.utc)

        broker.get_historical_data("TCS", "1d", from_date, to_date)

        sent = broker._client.history.call_args.kwargs["data"]
        assert sent["symbol"] == "NSE:TCS-EQ"
        assert sent["resolution"] == "D"

    def test_returned_candle_timestamps_are_tz_aware(self):
        """Regression: candles came back as naive datetimes, which broke
        the discovery scanner's `datetime.now(timezone.utc) - candle.timestamp`
        with "can't subtract offset-naive and offset-aware datetimes" —
        found live once Bugs 1-3 (date_format, event loop, history_days)
        were fixed and candles actually started coming back."""
        broker = _connected_broker()
        broker._client.history.return_value = {
            "code": 200,
            "candles": [[1735689600, 100, 105, 99, 102, 50000]],
        }

        candles = broker.get_historical_data(
            "RELIANCE", "1d",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 8, tzinfo=timezone.utc),
        )

        assert candles[0].timestamp.tzinfo is not None


class TestIndexSymbolFormatting:
    """
    Regression coverage found while wiring core/regime/fetcher.py (the real
    regime engine) up to a live broker call for the first time: it requests
    "NIFTY 50" / "INDIA VIX" as symbols, but get_historical_data blindly
    formatted every symbol as an equity ("NSE:{symbol}-EQ") — Fyers indices
    use "-INDEX" with no spaces in the name instead
    ("NSE:NIFTY50-INDEX" / "NSE:INDIAVIX-INDEX"). Every prior caller
    (core/darvas/*.py) only ever dealt in equities, so this never surfaced.
    """

    def test_nifty_50_formatted_as_index_not_equity(self):
        broker = _connected_broker()
        broker.get_historical_data(
            "NIFTY 50", "1d",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 8, tzinfo=timezone.utc),
        )
        sent = broker._client.history.call_args.kwargs["data"]
        assert sent["symbol"] == "NSE:NIFTY50-INDEX"

    def test_india_vix_formatted_as_index_not_equity(self):
        broker = _connected_broker()
        broker.get_historical_data(
            "INDIA VIX", "1d",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 8, tzinfo=timezone.utc),
        )
        sent = broker._client.history.call_args.kwargs["data"]
        assert sent["symbol"] == "NSE:INDIAVIX-INDEX"

    def test_regular_equity_unaffected(self):
        broker = _connected_broker()
        broker.get_historical_data(
            "RELIANCE", "1d",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 8, tzinfo=timezone.utc),
        )
        sent = broker._client.history.call_args.kwargs["data"]
        assert sent["symbol"] == "NSE:RELIANCE-EQ"


class TestOrderAndQuoteSymbolFormatting:
    """
    place_order/get_ltp/get_quotes used to build "NSE:{symbol}-EQ" inline
    instead of going through _fyers_symbol() (unlike get_historical_data,
    which already used the shared helper) — 3 independently-hardcoded call
    sites, no index-symbol safety, found while scoping S8-3 live execution.
    Fixed to call the shared helper; these lock in equity behaviour is
    unchanged and index symbols are now handled correctly too.
    """

    def test_place_order_formats_equity_symbol(self):
        broker = _connected_broker()
        broker._client.place_order.return_value = {
            "code": 200, "id": "ORD1", "message": "ok",
        }
        order = Order(
            symbol="RELIANCE", direction=OrderDirection.BUY, quantity=1,
            order_type=OrderType.MARKET, product_type=ProductType.CNC,
        )

        broker.place_order(order)

        sent = broker._client.place_order.call_args.kwargs["data"]
        assert sent["symbol"] == "NSE:RELIANCE-EQ"

    def test_get_ltp_formats_equity_symbols(self):
        broker = _connected_broker()
        broker._client.quotes.return_value = {"code": 200, "d": []}

        broker.get_ltp(["RELIANCE", "TCS"])

        sent = broker._client.quotes.call_args.kwargs["data"]
        assert sent["symbols"] == "NSE:RELIANCE-EQ,NSE:TCS-EQ"

    def test_get_ltp_formats_index_symbol(self):
        broker = _connected_broker()
        broker._client.quotes.return_value = {"code": 200, "d": []}

        broker.get_ltp(["NIFTY 50"])

        sent = broker._client.quotes.call_args.kwargs["data"]
        assert sent["symbols"] == "NSE:NIFTY50-INDEX"

    def test_get_quotes_formats_equity_symbols(self):
        broker = _connected_broker()
        broker._client.quotes.return_value = {"code": 200, "d": []}

        broker.get_quotes(["RELIANCE", "TCS"])

        sent = broker._client.quotes.call_args.kwargs["data"]
        assert sent["symbols"] == "NSE:RELIANCE-EQ,NSE:TCS-EQ"

    def test_get_quotes_formats_index_symbol(self):
        broker = _connected_broker()
        broker._client.quotes.return_value = {"code": 200, "d": []}

        broker.get_quotes(["INDIA VIX"])

        sent = broker._client.quotes.call_args.kwargs["data"]
        assert sent["symbols"] == "NSE:INDIAVIX-INDEX"
