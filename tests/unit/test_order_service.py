"""
Tests for core/execution/order_service.py (layer 1) against a fake
broker -- no network, no Fyers. Mirrors the fake-broker style already
used by tests/unit/test_probe_orb_scalping_stopout_spreads.py.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brokers.base import (  # noqa: E402
    Order,
    OrderDirection,
    OrderResult,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
)
from core.execution.order_service import (  # noqa: E402
    enter_position,
    flatten_position,
    reconcile_position,
    update_stop,
)


class _FakeBroker:
    def __init__(self):
        self.placed_orders: list[Order] = []
        self.cancelled_order_ids: list[str] = []
        self.modify_calls: list[tuple] = []
        self._order_status: dict[str, OrderResult] = {}
        self._positions: list[Position] = []
        self._order_history: list[OrderResult] = []
        self._next_order_id = 1

    def _new_order_id(self) -> str:
        oid = f"ORD-{self._next_order_id}"
        self._next_order_id += 1
        return oid

    def place_order(self, order: Order) -> OrderResult:
        self.placed_orders.append(order)
        order_id = self._new_order_id()
        result = OrderResult(
            order_id=order_id, status=OrderStatus.EXECUTED, symbol=order.symbol,
            direction=order.direction, quantity=order.quantity,
            filled_quantity=order.quantity, average_price=100.0,
            timestamp=datetime.now(timezone.utc),
        )
        self._order_status[order_id] = result
        return result

    def get_order_status(self, order_id: str) -> OrderResult:
        return self._order_status[order_id]

    def cancel_order(self, order_id: str) -> bool:
        self.cancelled_order_ids.append(order_id)
        return True

    def modify_stop_loss(self, order_id: str, new_trigger_price: float) -> bool:
        self.modify_calls.append((order_id, new_trigger_price))
        return True

    def get_positions(self) -> list[Position]:
        return self._positions

    def get_order_history(self) -> list[OrderResult]:
        return self._order_history


# ─── enter_position ──────────────────────────────────────────────────────

def test_enter_position_dry_run_places_no_orders():
    broker = _FakeBroker()
    result = enter_position(
        broker, symbol="NSE:NIFTY26SEP24000CE", direction=OrderDirection.BUY,
        quantity=65, product_type=ProductType.INTRADAY,
        protective_stop_trigger=37.5, tag="orb-nifty", dry_run=True,
    )
    assert result.dry_run is True
    assert result.entry_order_id is None
    assert result.stop_order_id is None
    assert broker.placed_orders == []


def test_enter_position_live_places_entry_then_opposite_direction_stop():
    broker = _FakeBroker()
    result = enter_position(
        broker, symbol="NSE:NIFTY26SEP24000CE", direction=OrderDirection.BUY,
        quantity=65, product_type=ProductType.INTRADAY,
        protective_stop_trigger=37.5, tag="orb-nifty", dry_run=False,
    )
    assert len(broker.placed_orders) == 2
    entry_order, stop_order = broker.placed_orders
    assert entry_order.order_type == OrderType.MARKET
    assert entry_order.direction == OrderDirection.BUY
    assert stop_order.order_type == OrderType.SL_M
    assert stop_order.direction == OrderDirection.SELL
    assert stop_order.trigger_price == 37.5
    assert result.dry_run is False
    assert result.entry_order_id is not None
    assert result.fill_price == 100.0
    assert result.stop_order_id is not None


def test_enter_position_sell_direction_gets_buy_side_stop():
    broker = _FakeBroker()
    enter_position(
        broker, symbol="NSE:NIFTY26SEP24000PE", direction=OrderDirection.SELL,
        quantity=65, product_type=ProductType.INTRADAY,
        protective_stop_trigger=60.0, tag="orb-nifty", dry_run=False,
    )
    _, stop_order = broker.placed_orders
    assert stop_order.direction == OrderDirection.BUY


# ─── update_stop ─────────────────────────────────────────────────────────

def test_update_stop_dry_run_does_not_call_broker():
    broker = _FakeBroker()
    ok = update_stop(broker, stop_order_id="SL-1", new_trigger_price=40.0, dry_run=True)
    assert ok is True
    assert broker.modify_calls == []


def test_update_stop_live_calls_modify_stop_loss():
    broker = _FakeBroker()
    ok = update_stop(broker, stop_order_id="SL-1", new_trigger_price=40.0, dry_run=False)
    assert ok is True
    assert broker.modify_calls == [("SL-1", 40.0)]


# ─── reconcile_position ──────────────────────────────────────────────────

def test_reconcile_still_open_when_broker_shows_nonzero_quantity():
    broker = _FakeBroker()
    broker._positions = [Position(
        symbol="NSE:NIFTY26SEP24000CE", quantity=65, average_price=100.0,
        current_price=110.0, pnl=650.0, pnl_percent=10.0, product_type=ProductType.INTRADAY,
    )]
    result = reconcile_position(broker, symbol="NSE:NIFTY26SEP24000CE", stop_order_id="SL-1")
    assert result.still_open is True
    assert result.exit_reason is None


def test_reconcile_finds_sl_fill_when_stop_order_executed():
    broker = _FakeBroker()
    broker._positions = []  # closed
    broker._order_history = [OrderResult(
        order_id="SL-1", status=OrderStatus.EXECUTED, symbol="NSE:NIFTY26SEP24000CE",
        direction=OrderDirection.SELL, quantity=65, filled_quantity=65,
        average_price=37.5, timestamp=datetime.now(timezone.utc),
    )]
    result = reconcile_position(broker, symbol="NSE:NIFTY26SEP24000CE", stop_order_id="SL-1")
    assert result.still_open is False
    assert result.exit_reason == "sl_fill"
    assert result.exit_price == 37.5
    assert broker.cancelled_order_ids == []  # the SL order itself filled -- nothing orphaned


def test_reconcile_falls_back_to_manual_close_and_cancels_orphaned_stop():
    broker = _FakeBroker()
    broker._positions = []
    broker._order_history = [OrderResult(
        order_id="MANUAL-1", status=OrderStatus.EXECUTED, symbol="NSE:NIFTY26SEP24000CE",
        direction=OrderDirection.SELL, quantity=65, filled_quantity=65,
        average_price=95.0, timestamp=datetime.now(timezone.utc),
    )]
    result = reconcile_position(broker, symbol="NSE:NIFTY26SEP24000CE", stop_order_id="SL-1")
    assert result.still_open is False
    assert result.exit_reason == "manual"
    assert result.exit_price == 95.0
    assert broker.cancelled_order_ids == ["SL-1"]


def test_reconcile_reports_closed_with_no_reason_when_history_unavailable():
    broker = _FakeBroker()
    broker._positions = []
    broker._order_history = []
    result = reconcile_position(broker, symbol="NSE:NIFTY26SEP24000CE", stop_order_id="SL-1")
    assert result.still_open is False
    # No executed history at all -- nothing to attribute the exit to.
    assert result.exit_reason is None
    assert result.exit_price is None


# ─── flatten_position ────────────────────────────────────────────────────

def test_flatten_dry_run_places_no_orders_and_cancels_nothing():
    broker = _FakeBroker()
    result = flatten_position(
        broker, symbol="NSE:NIFTY26SEP24000CE", direction=OrderDirection.BUY,
        quantity=65, product_type=ProductType.INTRADAY, stop_order_id="SL-1",
        tag="orb-nifty-flatten", dry_run=True,
    )
    assert result.dry_run is True
    assert broker.placed_orders == []
    assert broker.cancelled_order_ids == []


def test_flatten_live_cancels_stop_then_closes_opposite_direction():
    broker = _FakeBroker()
    result = flatten_position(
        broker, symbol="NSE:NIFTY26SEP24000CE", direction=OrderDirection.BUY,
        quantity=65, product_type=ProductType.INTRADAY, stop_order_id="SL-1",
        tag="orb-nifty-flatten", dry_run=False,
    )
    assert broker.cancelled_order_ids == ["SL-1"]
    assert len(broker.placed_orders) == 1
    assert broker.placed_orders[0].direction == OrderDirection.SELL
    assert result.dry_run is False
    assert result.fill_price == 100.0


def test_flatten_without_a_stop_order_id_still_closes():
    broker = _FakeBroker()
    flatten_position(
        broker, symbol="NSE:NIFTY26SEP24000CE", direction=OrderDirection.SELL,
        quantity=65, product_type=ProductType.INTRADAY, stop_order_id=None,
        tag="orb-nifty-flatten", dry_run=False,
    )
    assert broker.cancelled_order_ids == []
    assert broker.placed_orders[0].direction == OrderDirection.BUY
