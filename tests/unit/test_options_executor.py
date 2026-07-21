"""
core/options/executor.py — multi-leg confirmed-signal execution with
auto-flatten-on-partial-failure (the user's explicit 2026-07-21 decision:
bound the naked-leg risk window automatically rather than only alert).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.brokers.base import BrokerError, OrderDirection, OrderResult, OrderStatus, ProductType
from core.options import executor


def _order_result(order_id, price):
    return OrderResult(
        order_id=order_id, status=OrderStatus.PENDING, symbol="X",
        direction=OrderDirection.BUY, quantity=1, filled_quantity=0,
        average_price=price, timestamp=datetime.now(timezone.utc),
    )


def _leg(**overrides):
    leg = {
        "action": "BUY", "option_type": "CE", "strike": 24800.0,
        "premium": 120.0, "quantity": 1, "symbol": "NSE:NIFTY2672124800CE",
        "lot_size": 65,
    }
    leg.update(overrides)
    return leg


class TestCheckCapital:

    def test_debit_strategy_within_funds_passes(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 100_000.0}
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]
        # net debit = (120 - 40) * 65 = 5200
        assert executor.check_capital(broker, legs) is None

    def test_debit_strategy_exceeding_funds_refused(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1000.0}
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]
        reason = executor.check_capital(broker, legs)
        assert reason is not None
        assert "Insufficient funds" in reason

    def test_credit_strategy_not_capital_checked(self):
        """Net credit (SELL premium > BUY premium) isn't pre-checked here —
        needs a real margin calculator, not built (see module docstring)."""
        broker = MagicMock()
        legs = [_leg(action="SELL", premium=120.0), _leg(action="BUY", premium=40.0, strike=25000.0)]
        assert executor.check_capital(broker, legs) is None
        broker.get_funds.assert_not_called()

    def test_funds_lookup_failure_refuses(self):
        broker = MagicMock()
        broker.get_funds.side_effect = BrokerError("session expired")
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]
        reason = executor.check_capital(broker, legs)
        assert "Could not verify available funds" in reason


class TestExecuteConfirmedSignal:

    def test_all_legs_fill_successfully(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.side_effect = [
            _order_result("ORD1", 121.0), _order_result("ORD2", 39.5),
        ]
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]

        outcome = executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        assert outcome.success is True
        assert len(outcome.filled_legs) == 2
        assert outcome.filled_legs[0].order_id == "ORD1"
        assert outcome.flatten_results == []

    def test_places_legs_as_margin_product_not_intraday(self):
        """The whole point is hold-to-expiry — INTRADAY would get
        auto-squared-off by the broker before market close."""
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.side_effect = [_order_result("ORD1", 121.0), _order_result("ORD2", 39.5)]
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]

        executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        for call in broker.place_order.call_args_list:
            assert call.args[0].product_type == ProductType.MARGIN

    def test_quantity_scaled_by_lot_size(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.return_value = _order_result("ORD1", 121.0)
        legs = [_leg(action="BUY", quantity=2, lot_size=65)]

        executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        assert broker.place_order.call_args.args[0].quantity == 130

    def test_second_leg_failure_flattens_first_leg(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.side_effect = [
            _order_result("ORD1", 121.0),               # leg 1 fills
            BrokerError("Order rejected: bad symbol"),   # leg 2 fails
            _order_result("ORD-FLAT-1", 121.5),          # flatten of leg 1 succeeds
        ]
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]

        outcome = executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        assert outcome.success is False
        assert outcome.failed_leg == legs[1]
        assert len(outcome.filled_legs) == 1
        assert len(outcome.flatten_results) == 1
        assert outcome.flatten_results[0].flattened is True
        assert outcome.flatten_results[0].order_id == "ORD-FLAT-1"

    def test_flatten_direction_is_opposite_of_original_leg(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.side_effect = [
            _order_result("ORD1", 121.0),
            BrokerError("rejected"),
            _order_result("ORD-FLAT-1", 121.5),
        ]
        legs = [_leg(action="BUY"), _leg(action="SELL", strike=25000.0)]

        executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        flatten_call = broker.place_order.call_args_list[-1]
        assert flatten_call.args[0].direction == OrderDirection.SELL  # opposite of BUY

    def test_flatten_itself_failing_is_reported_not_swallowed(self):
        """Worst case: the corrective flatten order ALSO fails — the
        caller (cloud alert) must be told, not left thinking it's handled."""
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.side_effect = [
            _order_result("ORD1", 121.0),
            BrokerError("rejected"),
            BrokerError("broker unreachable"),
        ]
        legs = [_leg(action="BUY"), _leg(action="SELL", strike=25000.0)]

        outcome = executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        assert outcome.flatten_results[0].flattened is False
        assert "broker unreachable" in outcome.flatten_results[0].error

    def test_third_leg_failure_flattens_both_prior_legs(self):
        """Iron condor style — 3+ legs, failure on the last one must
        flatten ALL previously-filled legs, not just the most recent."""
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 1_000_000.0}
        broker.place_order.side_effect = [
            _order_result("ORD1", 10.0), _order_result("ORD2", 8.0),
            BrokerError("rejected"),
            _order_result("ORD-FLAT-1", 10.5), _order_result("ORD-FLAT-2", 8.5),
        ]
        legs = [_leg(strike=24000, action="SELL"), _leg(strike=23800, action="BUY"),
                _leg(strike=25600, action="SELL")]

        outcome = executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        assert len(outcome.flatten_results) == 2
        assert all(f.flattened for f in outcome.flatten_results)

    def test_capital_refusal_places_no_orders(self):
        broker = MagicMock()
        broker.get_funds.return_value = {"available": 100.0}
        legs = [_leg(action="BUY", premium=120.0), _leg(action="SELL", premium=40.0, strike=25000.0)]

        outcome = executor.execute_confirmed_signal(broker, "SIG-OPT-TEST0001", legs)

        assert outcome.success is False
        assert outcome.error is not None
        broker.place_order.assert_not_called()
