"""
core/execution/slicer.py — the loop that places sliced orders.

The properties worth protecting are the refusals. An execution loop that
degrades gracefully in the wrong direction — sending the whole order when it
cannot slice, or spinning forever against a book that has gone — is worse than
one that stops and says so.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.brokers.base import (
    DepthLevel, MarketDepth, OrderDirection, OrderResult, OrderStatus,
)
from core.execution.slicer import SlicerError, execute_sliced
from core.execution.slicing import SlicingPolicy

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def depth(bids=None, asks=None, symbol="TVSMOTOR"):
    return MarketDepth(
        symbol=symbol,
        bids=tuple(DepthLevel(p, q) for p, q in (bids or [])),
        asks=tuple(DepthLevel(p, q) for p, q in (asks or [])),
        timestamp=_NOW,
    )


THICK = depth(bids=[(99.0, 5000)], asks=[(101.0, 5000)])
EMPTY = depth(bids=[(99.0, 5000)], asks=[])


def broker_with(*snapshots, order_id="OID-1", fill_price=101.0):
    """A broker returning the given snapshots in order, repeating the last."""
    broker = MagicMock()
    sequence = list(snapshots)

    def _depth(symbol):
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    broker.get_market_depth.side_effect = _depth
    broker.place_order.return_value = _result(order_id, fill_price)
    return broker


def _result(order_id="OID-1", fill_price=101.0, quantity=0):
    return OrderResult(
        order_id=order_id, status=OrderStatus.EXECUTED, symbol="TVSMOTOR",
        direction=OrderDirection.BUY, quantity=quantity,
        filled_quantity=quantity, average_price=fill_price, timestamp=_NOW,
    )


def _noop_sleep(_seconds):
    pass


class TestHappyPath:

    def test_fills_the_parent_order_in_slices(self):
        broker = broker_with(THICK)
        report = execute_sliced(broker, "TVSMOTOR", OrderDirection.BUY, 3000,
                                policy=SlicingPolicy(participation_rate=0.2, max_levels=1),
                                dry_run=True, sleep=_noop_sleep)
        assert report.is_complete
        assert report.filled_qty == 3000
        assert len(report.fills) == 3          # 1000 per slice

    def test_records_the_arrival_price(self):
        report = execute_sliced(broker_with(THICK), "TVSMOTOR", OrderDirection.BUY,
                                100, dry_run=True, sleep=_noop_sleep)
        assert report.arrival_price == pytest.approx(100.0)

    def test_reports_realised_shortfall(self):
        report = execute_sliced(broker_with(THICK), "TVSMOTOR", OrderDirection.BUY,
                                100, dry_run=True, sleep=_noop_sleep)
        # bought at 101 against a 100 arrival mid = 100bps
        assert report.slippage_bps == pytest.approx(100.0)

    def test_dry_run_places_nothing(self):
        broker = broker_with(THICK)
        report = execute_sliced(broker, "TVSMOTOR", OrderDirection.BUY, 100,
                                dry_run=True, sleep=_noop_sleep)
        broker.place_order.assert_not_called()
        assert report.dry_run
        assert all(f.dry_run for f in report.fills)

    def test_live_run_places_orders(self):
        broker = broker_with(THICK)
        execute_sliced(broker, "TVSMOTOR", OrderDirection.BUY, 100,
                       dry_run=False, sleep=_noop_sleep)
        assert broker.place_order.call_count == 1

    def test_depth_is_re_read_between_slices(self):
        """The whole reason this is a loop and not a static plan."""
        broker = broker_with(THICK)
        execute_sliced(broker, "TVSMOTOR", OrderDirection.BUY, 3000,
                       policy=SlicingPolicy(participation_rate=0.2, max_levels=1),
                       dry_run=True, sleep=_noop_sleep)
        assert broker.get_market_depth.call_count >= 3


class TestRefusals:

    def test_broker_without_depth_raises_rather_than_sending_unsliced(self):
        """The tempting fallback is exactly what slicing exists to avoid."""
        broker = MagicMock()
        broker.get_market_depth.side_effect = NotImplementedError("no depth")
        with pytest.raises(SlicerError, match="cannot be sliced"):
            execute_sliced(broker, "TVSMOTOR", OrderDirection.BUY, 1000,
                           dry_run=True, sleep=_noop_sleep)
        broker.place_order.assert_not_called()

    def test_one_sided_book_aborts_with_no_arrival_price(self):
        report = execute_sliced(broker_with(EMPTY), "TVSMOTOR", OrderDirection.BUY,
                                1000, dry_run=True, sleep=_noop_sleep)
        assert report.filled_qty == 0
        assert "no two-sided quote" in report.aborted_reason

    def test_vanished_depth_gives_up_after_max_idle_rounds(self):
        """Rather than spinning against a book that has gone."""
        thin = depth(bids=[(99.0, 5000)], asks=[(101.0, 1)])
        report = execute_sliced(
            broker_with(thin), "TVSMOTOR", OrderDirection.BUY, 5000,
            policy=SlicingPolicy(participation_rate=0.3, min_slice_qty=100),
            dry_run=True, max_idle_rounds=3, sleep=_noop_sleep)
        assert report.filled_qty == 0
        assert "consecutive rounds" in report.aborted_reason
        assert len(report.skipped) == 3

    def test_initial_depth_failure_aborts_without_raising(self):
        broker = MagicMock()
        broker.get_market_depth.side_effect = RuntimeError("socket closed")
        report = execute_sliced(broker, "TVSMOTOR", OrderDirection.BUY, 100,
                                dry_run=True, sleep=_noop_sleep)
        assert report.filled_qty == 0
        assert "initial depth fetch failed" in report.aborted_reason

    def test_non_positive_quantity(self):
        report = execute_sliced(broker_with(THICK), "TVSMOTOR", OrderDirection.BUY,
                                0, dry_run=True, sleep=_noop_sleep)
        assert "not positive" in report.aborted_reason


class TestHaltAndFailure:

    def test_kill_switch_stops_adding_but_keeps_what_filled(self):
        """Same 'refuse entries, keep managing exits' philosophy as
        pilot_executor — a slicer mid-order is a new entry each slice."""
        calls = {"n": 0}

        def halt():
            calls["n"] += 1
            return "portfolio kill switch" if calls["n"] > 2 else None

        report = execute_sliced(
            broker_with(THICK), "TVSMOTOR", OrderDirection.BUY, 5000,
            policy=SlicingPolicy(participation_rate=0.2, max_levels=1),
            dry_run=True, halt_check=halt, sleep=_noop_sleep)

        assert 0 < report.filled_qty < 5000
        assert "kill switch" in report.aborted_reason

    def test_a_failed_slice_aborts_and_keeps_prior_fills(self):
        broker = broker_with(THICK)
        broker.place_order.side_effect = [_result("A"), RuntimeError("margin shortfall")]
        report = execute_sliced(
            broker, "TVSMOTOR", OrderDirection.BUY, 3000,
            policy=SlicingPolicy(participation_rate=0.2, max_levels=1),
            dry_run=False, sleep=_noop_sleep)

        assert report.filled_qty == 1000
        assert not report.is_complete
        assert "margin shortfall" in report.aborted_reason

    def test_depth_refresh_failure_reuses_the_last_snapshot(self):
        """Aborting a partly-filled order because one refresh failed would be
        worse than deciding against slightly stale depth."""
        broker = MagicMock()
        broker.get_market_depth.side_effect = [THICK, RuntimeError("timeout"), THICK]
        broker.place_order.return_value = _result("A")

        report = execute_sliced(
            broker, "TVSMOTOR", OrderDirection.BUY, 3000,
            policy=SlicingPolicy(participation_rate=0.2, max_levels=1),
            dry_run=True, sleep=_noop_sleep)
        assert report.filled_qty == 3000       # completed despite the failure


class TestReport:

    def test_summary_marks_dry_runs(self):
        report = execute_sliced(broker_with(THICK), "TVSMOTOR", OrderDirection.BUY,
                                100, dry_run=True, sleep=_noop_sleep)
        assert "[DRY RUN]" in report.summary()

    def test_summary_carries_fill_and_shortfall(self):
        report = execute_sliced(broker_with(THICK), "TVSMOTOR", OrderDirection.BUY,
                                100, dry_run=True, sleep=_noop_sleep)
        summary = report.summary()
        assert "100/100" in summary and "bps" in summary
