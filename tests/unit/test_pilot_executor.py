"""
core/rotation/pilot_executor.py — momentum turnover REAL-capital pilot:
quarter-boundary gate reuse, real order placement, pilot-scoped stop-loss,
and feeding real closed trades into TradeHistoryService (Kelly sizing).
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from agent import risk_guard
from agent import rotation_pilot_positions as rpp
from core.brokers.base import OHLCV, OrderDirection, OrderResult, OrderStatus, ProductType
from core.risk.trade_history import TradeHistoryService
from core.rotation import pilot_executor as pex


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(rpp, "PILOT_STATE_PATH", tmp_path / "rotation_pilot_state.json")
    monkeypatch.setattr(risk_guard, "HALT_FLAG_PATH", tmp_path / "halt")


@pytest.fixture
def trade_history_path(tmp_path):
    return tmp_path / "trade_history.json"


def _order_result(order_id="ORD1", price=None):
    return OrderResult(
        order_id=order_id, status=OrderStatus.PENDING, symbol="X",
        direction=OrderDirection.BUY, quantity=1, filled_quantity=0,
        average_price=price, timestamp=datetime.now(timezone.utc),
    )


def _mock_broker(funds_available=53_000.0):
    broker = MagicMock()
    broker.get_funds.return_value = {"available": funds_available}
    broker.place_order.side_effect = lambda order: _order_result(
        order_id=f"ORD-{order.symbol}", price=100.0)
    return broker


def _patch_fetch(monkeypatch, candles_by_symbol: dict):
    import scripts.validate_regime_classifier as vrc

    async def _fake_fetch(broker, symbol, from_date, to_date, sem):
        return candles_by_symbol.get(symbol, [])

    monkeypatch.setattr(vrc, "fetch_chunked_daily", _fake_fetch)


def _warmed_up_candles(close: float, high: float = None, n: int = 260) -> list[OHLCV]:
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


class TestPilotHaltReason:

    def test_no_loss_does_not_halt(self):
        assert pex.pilot_halt_reason(realized_pnl=0.0, capital_reference=53000, max_loss_pct=0.25) is None

    def test_loss_under_threshold_does_not_halt(self):
        assert pex.pilot_halt_reason(realized_pnl=-10000, capital_reference=53000, max_loss_pct=0.25) is None

    def test_loss_at_threshold_halts(self):
        reason = pex.pilot_halt_reason(realized_pnl=-13250, capital_reference=53000, max_loss_pct=0.25)
        assert reason is not None
        assert "13,250" in reason or "13250" in reason

    def test_loss_beyond_threshold_halts(self):
        assert pex.pilot_halt_reason(realized_pnl=-20000, capital_reference=53000, max_loss_pct=0.25) is not None

    def test_zero_capital_reference_never_halts(self):
        assert pex.pilot_halt_reason(realized_pnl=-999999, capital_reference=0, max_loss_pct=0.25) is None


class TestRunQuarterlyPilotRebalanceGate:

    def test_not_yet_due_returns_none_and_places_no_orders(self, monkeypatch, trade_history_path):
        state = rpp.load_state()
        state.last_rebalanced_quarter_end = "2026-06-30"
        rpp.save_state(state)

        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 8, 15, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=True, now=as_of))

        assert result is None
        broker.place_order.assert_not_called()

    def test_second_call_same_quarter_is_a_noop(self, monkeypatch, trade_history_path):
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of_1 = datetime(2026, 9, 30, tzinfo=timezone.utc)
        as_of_2 = datetime(2026, 10, 5, tzinfo=timezone.utc)

        first = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=True, now=as_of_1))
        second = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=True, now=as_of_2))

        assert first is not None
        assert second is None


class TestRunQuarterlyPilotRebalanceDryRun:

    def test_dry_run_places_no_real_orders(self, monkeypatch, trade_history_path):
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=True, now=as_of))

        broker.place_order.assert_not_called()
        assert result.dry_run is True
        assert result.buys[0]["symbol"] == "A"
        assert result.buys[0]["order_id"] is None
        # Dry run must not persist positions.
        assert rpp.load_state().positions == {}


class TestRunQuarterlyPilotRebalanceLive:

    def test_live_buys_new_entrant_and_persists_position(self, monkeypatch, trade_history_path):
        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=False, now=as_of))

        broker.place_order.assert_called_once()
        sent_order = broker.place_order.call_args.args[0]
        assert sent_order.symbol == "A"
        assert sent_order.direction == OrderDirection.BUY
        assert sent_order.product_type == ProductType.CNC

        assert result.buys[0]["symbol"] == "A"
        state = rpp.load_state()
        assert "A" in state.positions
        assert state.positions["A"].quantity == 25  # 2500 / 100.0

    def test_live_sell_records_closed_trade_and_feeds_kelly(self, monkeypatch, trade_history_path):
        state = rpp.load_state()
        state.positions["A"] = rpp.PilotPosition(
            symbol="A", quantity=25, entry_price=80.0,
            entry_date="2026-07-01T00:00:00+00:00")
        rpp.save_state(state)

        broker = _mock_broker()
        _patch_fetch(monkeypatch, {
            "A": _warmed_up_candles(close=50.0, high=100.0),   # far from high, ranks low -> dropped
            "B": _warmed_up_candles(close=100.0, high=100.0),  # at high, ranks top
        })
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A", "B"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=False, now=as_of))

        sell_calls = [c.args[0] for c in broker.place_order.call_args_list
                      if c.args[0].direction == OrderDirection.SELL]
        assert len(sell_calls) == 1
        assert sell_calls[0].symbol == "A"
        assert sell_calls[0].quantity == 25

        assert "A" not in rpp.load_state().positions
        assert any(s["symbol"] == "A" for s in result.sells)

        # Real net P&L (loss, entry 80 -> exit ~100 fill from the mock broker
        # is actually a gain here — quantity*price move) flowed into the
        # pilot's own realized_pnl AND into the shared Kelly trade history.
        state = rpp.load_state()
        assert state.realized_pnl == pytest.approx(result.realized_pnl)
        assert state.realized_pnl != 0.0

        sizer = TradeHistoryService(persist_path=trade_history_path)
        history = sizer.get_trade_history("A")
        assert len(history) == 1
        assert history[0].strategy == "rotation_pilot"

    def test_global_halt_skips_buys_but_still_sells(self, monkeypatch, trade_history_path):
        state = rpp.load_state()
        state.positions["A"] = rpp.PilotPosition(
            symbol="A", quantity=25, entry_price=80.0,
            entry_date="2026-07-01T00:00:00+00:00")
        rpp.save_state(state)
        risk_guard.set_halt("test halt")

        broker = _mock_broker()
        _patch_fetch(monkeypatch, {
            "A": _warmed_up_candles(close=50.0, high=100.0),
            "B": _warmed_up_candles(close=100.0, high=100.0),
        })
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A", "B"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=False, now=as_of))

        buy_calls = [c.args[0] for c in broker.place_order.call_args_list
                     if c.args[0].direction == OrderDirection.BUY]
        assert buy_calls == []
        assert any(s["symbol"] == "B" and "halted" in s["reason"] for s in result.skipped_buys)
        assert any(s["symbol"] == "A" for s in result.sells)   # sells unaffected

    def test_pilot_loss_halt_skips_buys_and_persists_across_quarters(self, monkeypatch, trade_history_path):
        # Cumulative realized loss already past the pilot's own threshold —
        # no separate flag file needed, the state itself carries the halt.
        state = rpp.load_state()
        state.realized_pnl = -20000.0
        rpp.save_state(state)

        broker = _mock_broker()
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=False, now=as_of))

        broker.place_order.assert_not_called()
        assert result.buys == []
        assert any("halted" in s["reason"] for s in result.skipped_buys)
        # Realized pnl is unchanged (no sells happened) -- still tripped next quarter.
        assert rpp.load_state().realized_pnl == -20000.0

    def test_insufficient_capital_skips_buys_with_reason(self, monkeypatch, trade_history_path):
        broker = _mock_broker(funds_available=0.0)
        _patch_fetch(monkeypatch, {"A": _warmed_up_candles(100.0)})
        as_of = datetime(2026, 9, 30, tzinfo=timezone.utc)

        result = asyncio.run(pex.run_quarterly_pilot_rebalance(
            broker, ["A"], top_n=1, position_size=2500, max_loss_pct=0.25,
            capital_reference=53000, trade_history_path=trade_history_path,
            dry_run=False, now=as_of))

        broker.place_order.assert_not_called()
        assert result.buys == []
        assert result.skipped_buys[0]["symbol"] == "A"
        assert "insufficient" in result.skipped_buys[0]["reason"]
