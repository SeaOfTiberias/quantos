"""
core/rotation/executor.py — S8-3 live rebalance orchestration: sizing,
target-basket diff execution, dry-run mode, and kill-switch integration.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from agent import risk_guard
from agent import rotation_positions as rp
from core.brokers.base import OHLCV, OrderResult, OrderStatus, OrderDirection
from core.rotation import executor
from core.rotation.ranker import SymbolSeries


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "ROTATION_POSITIONS_PATH", tmp_path / "rotation_positions.json")
    monkeypatch.setattr(risk_guard, "HALT_FLAG_PATH", tmp_path / "halt")


def _order_result(order_id="ORD1", price=None):
    return OrderResult(
        order_id=order_id, status=OrderStatus.PENDING, symbol="X",
        direction=OrderDirection.BUY, quantity=1, filled_quantity=0,
        average_price=price, timestamp=datetime.now(timezone.utc),
    )


class TestSizeNewEntrants:

    def test_full_capital_sizes_at_flat_position_size(self):
        sized, skipped = executor._size_new_entrants(
            ["A", "B"], {"A": 100.0, "B": 50.0},
            available_capital=1_000_000.0, position_size=100_000.0,
        )
        assert sized == {"A": 1000, "B": 2000}
        assert skipped == []

    def test_constrained_capital_scales_down_proportionally(self):
        # Needs 200,000 total for 2 entrants at 100,000 each; only 100,000 available -> 50%.
        sized, skipped = executor._size_new_entrants(
            ["A", "B"], {"A": 100.0, "B": 100.0},
            available_capital=100_000.0, position_size=100_000.0,
        )
        assert sized == {"A": 500, "B": 500}
        assert skipped == []

    def test_zero_capital_skips_all_with_reason(self):
        sized, skipped = executor._size_new_entrants(
            ["A", "B"], {"A": 100.0, "B": 100.0},
            available_capital=0.0, position_size=100_000.0,
        )
        assert sized == {}
        assert {s["symbol"] for s in skipped} == {"A", "B"}
        assert all("insufficient" in s["reason"] for s in skipped)

    def test_missing_price_is_skipped_not_sized(self):
        sized, skipped = executor._size_new_entrants(
            ["A", "B"], {"A": 100.0},   # B has no price
            available_capital=1_000_000.0, position_size=100_000.0,
        )
        assert sized == {"A": 1000}
        assert skipped == [{"symbol": "B", "reason": "no live price available"}]

    def test_no_buys_returns_empty(self):
        sized, skipped = executor._size_new_entrants([], {}, 1_000_000.0, 100_000.0)
        assert sized == {}
        assert skipped == []


class TestLatestPrice:

    def test_returns_close_price_when_available(self):
        as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = {"A": SymbolSeries(dates=[as_of], closes=[123.0], highs=[150.0])}
        assert executor._latest_price(series, "A", as_of) == 123.0

    def test_returns_none_for_unknown_symbol(self):
        assert executor._latest_price({}, "A", datetime.now(timezone.utc)) is None


def _mock_broker(funds_available=1_000_000.0):
    broker = MagicMock()
    broker.get_funds.return_value = {"available": funds_available}
    broker.place_order.side_effect = lambda order: _order_result(
        order_id=f"ORD-{order.symbol}", price=100.0)
    return broker


def _patch_fetch(monkeypatch, candles_by_symbol: dict):
    """Patch scripts.validate_regime_classifier.fetch_chunked_daily — the
    module executor._fetch_universe_series imports it FROM at call time
    (a deliberately deferred import, to avoid a circular import with
    agent.main), so patching the source module's attribute is what actually
    takes effect."""
    import scripts.validate_regime_classifier as vrc

    async def _fake_fetch(broker, symbol, from_date, to_date, sem):
        return candles_by_symbol.get(symbol, [])

    monkeypatch.setattr(vrc, "fetch_chunked_daily", _fake_fetch)


def _warmed_up_candles(close: float, high: float = None, n: int = 260) -> list[OHLCV]:
    """n-1 bars at `high` (establishing the rolling 52-week high), then a
    final bar at `close` — so nearness-to-high (close/high) actually
    discriminates between symbols instead of every flat-price series
    scoring a tautological 1.0."""
    high = high if high is not None else close
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = [
        OHLCV(timestamp=start + timedelta(days=i), open=high,
              high=high, low=high, close=high, volume=1000)
        for i in range(n - 1)
    ]
    candles.append(OHLCV(timestamp=start + timedelta(days=n - 1), open=close,
                          high=high, low=close, close=close, volume=1000))
    return candles


class TestRunWeeklyRebalanceDryRun:

    def test_dry_run_places_no_real_orders(self, monkeypatch):
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0), "B": _warmed_up_candles(90.0)})

        result = asyncio.run(executor.run_weekly_rebalance(
            broker, ["A", "B"], top_n=2, position_size=100_000.0, dry_run=True))

        broker.place_order.assert_not_called()
        assert result.dry_run is True
        assert {b["symbol"] for b in result.buys} == {"A", "B"}
        assert all(b["order_id"] is None for b in result.buys)
        # Dry run must not persist positions either.
        assert rp.load_rotation_positions() == {}


class TestRunWeeklyRebalanceLive:

    def test_live_buys_new_entrants_and_persists_positions(self, monkeypatch):
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})

        result = asyncio.run(executor.run_weekly_rebalance(
            broker, ["A"], top_n=1, position_size=100_000.0, dry_run=False))

        broker.place_order.assert_called_once()
        sent_order = broker.place_order.call_args.args[0]
        assert sent_order.symbol == "A"
        assert sent_order.direction == OrderDirection.BUY
        from core.brokers.base import ProductType
        assert sent_order.product_type == ProductType.CNC

        assert result.buys[0]["symbol"] == "A"
        positions = rp.load_rotation_positions()
        assert "A" in positions
        assert positions["A"].quantity == 1000  # 100,000 / 100.0

    def test_sells_dropped_symbol_and_removes_from_positions(self, monkeypatch):
        # A is currently held but won't rank in the new top-1 basket.
        positions = rp.load_rotation_positions()
        rp.add_position(positions, rp.RotationPosition(
            symbol="A", quantity=500, entry_price=80.0,
            entry_date="2026-07-01T00:00:00+00:00",
        ))
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {
            "A": _warmed_up_candles(close=50.0, high=100.0),   # far from its own high, ranks low
            "B": _warmed_up_candles(close=100.0, high=100.0),  # at its high, ranks top
        })

        result = asyncio.run(executor.run_weekly_rebalance(
            broker, ["A", "B"], top_n=1, position_size=100_000.0, dry_run=False))

        sell_calls = [c.args[0] for c in broker.place_order.call_args_list
                      if c.args[0].direction == OrderDirection.SELL]
        assert len(sell_calls) == 1
        assert sell_calls[0].symbol == "A"
        assert sell_calls[0].quantity == 500

        assert "A" not in rp.load_rotation_positions()
        assert any(s["symbol"] == "A" for s in result.sells)

    def test_halted_skips_all_buys_but_still_sells(self, monkeypatch):
        positions = rp.load_rotation_positions()
        rp.add_position(positions, rp.RotationPosition(
            symbol="A", quantity=500, entry_price=80.0,
            entry_date="2026-07-01T00:00:00+00:00",
        ))
        risk_guard.set_halt("test halt")
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {
            "A": _warmed_up_candles(close=50.0, high=100.0),
            "B": _warmed_up_candles(close=100.0, high=100.0),
        })

        result = asyncio.run(executor.run_weekly_rebalance(
            broker, ["A", "B"], top_n=1, position_size=100_000.0, dry_run=False))

        buy_calls = [c.args[0] for c in broker.place_order.call_args_list
                     if c.args[0].direction == OrderDirection.BUY]
        assert buy_calls == []
        assert result.buys == []
        assert any(s["symbol"] == "B" and "halted" in s["reason"] for s in result.skipped_buys)
        # Sells are unaffected by the halt.
        assert any(s["symbol"] == "A" for s in result.sells)

    def test_insufficient_capital_skips_buys_with_reason(self, monkeypatch):
        broker = _mock_broker(funds_available=0.0)
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})

        result = asyncio.run(executor.run_weekly_rebalance(
            broker, ["A"], top_n=1, position_size=100_000.0, dry_run=False))

        broker.place_order.assert_not_called()
        assert result.buys == []
        assert result.skipped_buys[0]["symbol"] == "A"
        assert "insufficient" in result.skipped_buys[0]["reason"]
