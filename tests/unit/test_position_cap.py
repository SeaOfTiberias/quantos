"""
Trial-phase notional cap — Unit Tests

`_size_and_place_order` risk-sizes a position (fixed 2% fallback until 20+
closed trades) and then clamps its ₹ value to `risk.max_position_value` so a
tight stop can't blow the notional up on a small trial account. These tests pin
that clamp: it bounds quantity, applies to the SL_M leg too, and rejects a
signal whose price alone exceeds the cap.
"""

from datetime import datetime, timezone

import pytest

from agent.main import _size_and_place_order
from core.brokers.base import OrderResult, OrderStatus, OrderType, BrokerError
from core.risk.trade_history import TradeHistoryService

_ANY_STATUS = next(iter(OrderStatus))


class FakeBroker:
    """Minimal BrokerAdapter stand-in: 50K available, records placed orders,
    fills MARKET orders instantly at their notional price."""
    def __init__(self, available=50_000.0):
        self._available = available
        self.placed = []

    def get_funds(self):
        return {"available": self._available}

    def place_order(self, order):
        self.placed.append(order)
        # average_price truthy → the fill-poll loop breaks immediately (no sleep)
        return OrderResult(
            order_id=f"OID{len(self.placed)}",
            status=_ANY_STATUS, symbol=order.symbol, direction=order.direction,
            quantity=order.quantity, filled_quantity=order.quantity,
            average_price=order.price or 500.0, timestamp=datetime.now(timezone.utc),
        )

    def get_order_status(self, order_id):  # pragma: no cover - not reached (instant fill)
        raise AssertionError("should not poll — MARKET filled instantly")


def _sizer():
    # Empty history → FIXED_FALLBACK 2% of capital.
    return TradeHistoryService(persist_path=None)


def _signal(price=500.0, stop=490.0):
    return {"signal_id": "sig-1", "symbol": "ACME", "action": "BUY",
            "price": price, "stop_loss": stop}


def _config(max_position_value=10_000, auto_exit=False):
    return {"risk": {"product_type": "INTRADAY", "auto_exit": auto_exit,
                     "max_position_value": max_position_value}}


def _entry_order(broker):
    return next(o for o in broker.placed if o.order_type == OrderType.MARKET)


# ─── The cap ──────────────────────────────────────────────────────────────────

def test_uncapped_quantity_is_risk_based():
    # 2% of 50K = ₹1000 risk; stop ₹10 away → 100 shares (₹50,000 notional).
    broker = FakeBroker()
    _size_and_place_order(broker, _sizer(), _signal(), _config(max_position_value=0))
    assert _entry_order(broker).quantity == 100


def test_cap_bounds_quantity():
    # Same trade, ₹10,000 cap at ₹500/share → 20 shares, not 100.
    broker = FakeBroker()
    order_id, qty, *_ = _size_and_place_order(
        broker, _sizer(), _signal(), _config(max_position_value=10_000))
    assert qty == 20
    assert _entry_order(broker).quantity == 20
    assert 20 * 500.0 <= 10_000


def test_cap_does_not_raise_quantity():
    # If risk-based qty is already under the cap, leave it alone.
    # Stop ₹100 away → risk qty = 1000/100 = 10 (₹5,000) < ₹10,000 cap.
    broker = FakeBroker()
    _, qty, *_ = _size_and_place_order(
        broker, _sizer(), _signal(price=500.0, stop=400.0),
        _config(max_position_value=10_000))
    assert qty == 10


def test_cap_applies_to_stop_loss_leg():
    broker = FakeBroker()
    _size_and_place_order(broker, _sizer(), _signal(),
                          _config(max_position_value=10_000, auto_exit=True))
    quantities = {o.order_type: o.quantity for o in broker.placed}
    assert quantities[OrderType.MARKET] == 20
    assert quantities[OrderType.SL_M] == 20   # stop leg matches capped entry


def test_price_above_cap_is_rejected():
    # ₹12,000/share with a ₹10,000 cap → cap_qty 0 → no order placed.
    broker = FakeBroker()
    with pytest.raises(BrokerError, match="price exceeds the cap|Computed quantity 0"):
        _size_and_place_order(broker, _sizer(), _signal(price=12_000.0, stop=11_800.0),
                              _config(max_position_value=10_000))
    assert broker.placed == []
