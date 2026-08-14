"""
core/execution/slicing.py — the pure slicing logic.

The class `TestReviewedImplementationDefects` is the point of this file. Each
case there is a defect found in the depth-aware slicer QuantOS was asked to
adopt (quantos_terminal_core.py, reviewed 2026-08-14), pinned so the
replacement cannot regress into the same behaviour.
"""

from datetime import datetime, timezone

import pytest

from core.brokers.base import DepthLevel, MarketDepth, OrderDirection
from core.execution.slicing import (
    SliceDecision, SlicingPolicy, available_depth, next_slice,
    simulate_execution, walk_book,
)

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def depth(bids=None, asks=None, symbol="NIFTY24AUG24300CE"):
    """Build a book. Prices descend on the bid, ascend on the ask."""
    return MarketDepth(
        symbol=symbol,
        bids=tuple(DepthLevel(p, q) for p, q in (bids or [])),
        asks=tuple(DepthLevel(p, q) for p, q in (asks or [])),
        timestamp=_NOW,
    )


BOOK = depth(
    bids=[(155.0, 200), (154.8, 500), (154.5, 800), (154.0, 1000)],
    asks=[(155.2, 200), (155.4, 500), (155.7, 800), (156.0, 1000)],
)


class TestWalkBook:
    """The primitive: quantity in, achieved price out."""

    def test_single_level(self):
        walk = walk_book(BOOK.asks, 100)
        assert walk.filled == 100
        assert walk.average_price == 155.2
        assert walk.levels_crossed == 1

    def test_crossing_levels_is_volume_weighted(self):
        walk = walk_book(BOOK.asks, 400)          # 200 @ 155.2 + 200 @ 155.4
        assert walk.filled == 400
        assert walk.average_price == pytest.approx((200 * 155.2 + 200 * 155.4) / 400)
        assert walk.levels_crossed == 2

    def test_exhausting_the_book_reports_it(self):
        walk = walk_book(BOOK.asks, 10_000)
        assert walk.exhausted is True
        assert walk.filled == 2500                # everything displayed

    def test_empty_book_fills_nothing(self):
        walk = walk_book((), 100)
        assert walk.filled == 0
        assert walk.average_price is None
        assert walk.exhausted is True

    def test_zero_quantity(self):
        assert walk_book(BOOK.asks, 0).filled == 0

    def test_zero_size_levels_are_skipped_not_counted(self):
        levels = (DepthLevel(100.0, 0), DepthLevel(101.0, 50))
        walk = walk_book(levels, 50)
        assert walk.average_price == 101.0
        assert walk.levels_crossed == 1


class TestSideSelection:
    """A BUY lifts the ask; a SELL hits the bid. The classic sign error."""

    def test_buy_consumes_asks(self):
        assert BOOK.side(OrderDirection.BUY) == BOOK.asks

    def test_sell_consumes_bids(self):
        assert BOOK.side(OrderDirection.SELL) == BOOK.bids

    def test_buy_slippage_is_positive_when_paying_up(self):
        d = next_slice(BOOK, OrderDirection.BUY, 100, SlicingPolicy())
        assert d.slippage_bps > 0          # paid above the mid

    def test_sell_slippage_is_also_positive_when_adverse(self):
        """Signed so positive always means 'worse than the reference',
        whichever way you are trading."""
        d = next_slice(BOOK, OrderDirection.SELL, 100, SlicingPolicy())
        assert d.slippage_bps > 0          # received below the mid


class TestNextSlice:

    def test_participation_bounds_the_slice(self):
        # top 3 ask levels = 200+500+800 = 1500; 30% = 450
        d = next_slice(BOOK, OrderDirection.BUY, 10_000,
                       SlicingPolicy(participation_rate=0.30, max_levels=3))
        assert d.available_qty == 1500
        assert d.quantity == 450

    def test_max_levels_bounds_what_counts_as_available(self):
        d = next_slice(BOOK, OrderDirection.BUY, 10_000,
                       SlicingPolicy(participation_rate=1.0, max_levels=1))
        assert d.available_qty == 200
        assert d.quantity == 200

    def test_remaining_quantity_caps_the_slice(self):
        d = next_slice(BOOK, OrderDirection.BUY, 50, SlicingPolicy())
        assert d.quantity == 50

    def test_max_slice_qty_caps_the_slice(self):
        d = next_slice(BOOK, OrderDirection.BUY, 10_000,
                       SlicingPolicy(participation_rate=1.0, max_slice_qty=75))
        assert d.quantity == 75

    def test_rounds_down_to_whole_lots(self):
        """Rounding UP would breach the participation limit the caller set."""
        d = next_slice(BOOK, OrderDirection.BUY, 10_000,
                       SlicingPolicy(participation_rate=0.30, max_levels=3, lot_size=100))
        assert d.quantity == 400          # 450 floored to a 100 lot

    def test_slice_smaller_than_one_lot_refuses(self):
        d = next_slice(depth(asks=[(155.0, 10)]), OrderDirection.BUY, 1000,
                       SlicingPolicy(participation_rate=0.30, lot_size=100))
        assert d.quantity == 0
        assert "below one lot" in d.reason

    def test_nothing_left_to_trade(self):
        assert next_slice(BOOK, OrderDirection.BUY, 0, SlicingPolicy()).quantity == 0

    def test_reports_levels_crossed(self):
        d = next_slice(BOOK, OrderDirection.BUY, 400,
                       SlicingPolicy(participation_rate=1.0))
        assert d.levels_crossed == 2


class TestRefusals:
    """Every path that declines to trade says why."""

    def test_no_ask_side_refuses(self):
        d = next_slice(depth(bids=[(155.0, 100)]), OrderDirection.BUY, 100, SlicingPolicy())
        assert d.quantity == 0
        assert "no ask side" in d.reason

    def test_no_bid_side_refuses(self):
        d = next_slice(depth(asks=[(155.0, 100)]), OrderDirection.SELL, 100, SlicingPolicy())
        assert d.quantity == 0
        assert "no bid side" in d.reason

    def test_slippage_limit_refuses_an_expensive_slice(self):
        wide = depth(bids=[(100.0, 1000)], asks=[(140.0, 1000)])   # ~33% spread
        d = next_slice(wide, OrderDirection.BUY, 100,
                       SlicingPolicy(max_slippage_bps=50.0))
        assert d.quantity == 0
        assert "exceeds" in d.reason
        assert d.slippage_bps > 50

    def test_slippage_limit_allows_a_tight_book(self):
        d = next_slice(BOOK, OrderDirection.BUY, 100, SlicingPolicy(max_slippage_bps=50.0))
        assert d.should_trade

    def test_large_remainder_waits_rather_than_sending_dust(self):
        d = next_slice(depth(asks=[(155.0, 30)]), OrderDirection.BUY, 5000,
                       SlicingPolicy(participation_rate=0.30, min_slice_qty=50))
        assert d.quantity == 0
        assert "waiting for depth" in d.reason

    def test_the_tail_of_an_order_is_allowed_through(self):
        """Otherwise the last few units could never be traded."""
        d = next_slice(depth(asks=[(155.0, 30)]), OrderDirection.BUY, 5,
                       SlicingPolicy(participation_rate=0.30, min_slice_qty=50))
        assert d.quantity == 5


class TestReviewedImplementationDefects:
    """Regression cases from quantos_terminal_core.py's OrderSlicingHandler,
    reviewed 2026-08-14. Each was verified against that code before this
    module was written."""

    def test_empty_depth_refuses_instead_of_slicing_into_units(self):
        """The original computed max(1, int(0 * rate)) == 1 and looped, so
        2,000 units became 2,000 orders of 1."""
        d = next_slice(depth(asks=[]), OrderDirection.BUY, 2000, SlicingPolicy())
        assert d.quantity == 0
        assert d.available_qty == 0

    def test_zero_size_levels_are_treated_as_empty(self):
        d = next_slice(depth(asks=[(155.0, 0), (155.2, 0)]),
                       OrderDirection.BUY, 2000, SlicingPolicy())
        assert d.quantity == 0
        assert "no displayed depth" in d.reason

    def test_participation_does_not_apply_to_the_whole_book(self):
        """The original summed EVERY level, so 30% of a 5-deep book meant
        deliberately crossing four levels — the impact it claimed to avoid.
        Here the default max_levels=3 bounds it."""
        deep = depth(asks=[(155.0, 200), (155.2, 200), (155.4, 200),
                           (155.6, 200), (155.8, 200)])
        d = next_slice(deep, OrderDirection.BUY, 10_000,
                       SlicingPolicy(participation_rate=0.30, max_levels=3))
        assert d.available_qty == 600           # not 1000
        assert d.quantity == 180                # 30% of 600
        assert d.levels_crossed == 1            # stayed at the touch

    def test_an_order_larger_than_the_book_does_not_get_sent_whole(self):
        """The original produced [450,450,450,450,200] for 2,000 units against
        1,500 displayed — the full size regardless of what was there."""
        book = depth(asks=[(155.0, 200), (155.2, 500), (155.4, 800)])
        d = next_slice(book, OrderDirection.BUY, 2000, SlicingPolicy())
        assert d.quantity == 450                # one bounded slice, not the lot
        assert d.quantity < 2000

    def test_each_decision_reflects_the_current_book_not_a_static_plan(self):
        """The original divided once and never looked at depth again."""
        thick = next_slice(depth(asks=[(155.0, 1000)]), OrderDirection.BUY,
                           10_000, SlicingPolicy(max_levels=1))
        thin = next_slice(depth(asks=[(155.0, 100)]), OrderDirection.BUY,
                          10_000, SlicingPolicy(max_levels=1))
        assert thick.quantity == 300
        assert thin.quantity == 30

    def test_expected_cost_is_reported_so_impact_is_measurable(self):
        """The original returned bare integers — no price, no slippage, so no
        way to tell whether slicing helped."""
        d = next_slice(BOOK, OrderDirection.BUY, 400, SlicingPolicy(participation_rate=1.0))
        assert d.expected_price is not None
        assert d.slippage_bps is not None


class TestSimulateExecution:
    """The measurement harness — the honest way to score an execution
    algorithm, as distinct from a strategy."""

    def _snapshots(self, n=10, size=200):
        return [depth(bids=[(155.0, size)], asks=[(155.2, size)]) for _ in range(n)]

    def test_fills_across_snapshots(self):
        sim = simulate_execution(self._snapshots(), OrderDirection.BUY, 300,
                                 SlicingPolicy(participation_rate=0.5, max_levels=1))
        assert sim.filled_qty == 300
        assert sim.is_complete

    def test_reports_shortfall_against_the_arrival_price(self):
        sim = simulate_execution(self._snapshots(), OrderDirection.BUY, 100,
                                 SlicingPolicy(participation_rate=1.0, max_levels=1))
        assert sim.arrival_price == pytest.approx(155.1)
        assert sim.slippage_bps == pytest.approx((155.2 - 155.1) / 155.1 * 10_000)

    def test_incomplete_execution_says_why(self):
        sim = simulate_execution(self._snapshots(n=2, size=10), OrderDirection.BUY,
                                 5000, SlicingPolicy())
        assert not sim.is_complete
        assert "unfilled" in sim.unfilled_reason

    def test_no_snapshots_is_not_a_crash(self):
        sim = simulate_execution([], OrderDirection.BUY, 100)
        assert sim.filled_qty == 0
        assert "no depth snapshots" in sim.unfilled_reason

    def test_slicing_beats_one_lump_on_a_laddered_book(self):
        """The comparison the module exists to make: same order, same book,
        participation-limited versus sent whole."""
        ladder = [depth(bids=[(154.8, 100)],
                        asks=[(155.0, 100), (156.0, 100), (158.0, 100)])
                  for _ in range(6)]

        sliced = simulate_execution(ladder, OrderDirection.BUY, 300,
                                    SlicingPolicy(participation_rate=1.0, max_levels=1))
        lump = simulate_execution(ladder[:1], OrderDirection.BUY, 300,
                                  SlicingPolicy(participation_rate=1.0, max_levels=99))

        assert sliced.filled_qty == lump.filled_qty == 300
        assert sliced.average_price == 155.0          # never left the touch
        assert lump.average_price == pytest.approx((155.0 + 156.0 + 158.0) / 3)
        assert sliced.slippage_bps < lump.slippage_bps


class TestSlicingPolicy:

    @pytest.mark.parametrize("kw", [
        {"participation_rate": 0.0}, {"participation_rate": 1.5},
        {"max_levels": 0}, {"lot_size": 0}, {"min_slice_qty": 0},
    ])
    def test_invalid_policy_rejected_at_construction(self, kw):
        with pytest.raises(ValueError):
            SlicingPolicy(**kw)


class TestMarketDepth:

    def test_mid_and_spread(self):
        assert BOOK.mid == pytest.approx(155.1)
        assert BOOK.spread == pytest.approx(0.2)
        assert BOOK.spread_bps == pytest.approx(0.2 / 155.1 * 10_000)

    def test_one_sided_book_has_no_mid(self):
        """Substituting the quoted side would make every slippage measurement
        against it silently wrong."""
        assert depth(asks=[(155.0, 100)]).mid is None
        assert depth(bids=[(155.0, 100)]).spread is None

    def test_is_two_sided(self):
        assert BOOK.is_two_sided
        assert not depth(asks=[(1.0, 1)]).is_two_sided

    def test_available_depth_is_bounded_by_max_levels(self):
        assert available_depth(BOOK.asks, 2) == 700
        assert available_depth(BOOK.asks, 99) == 2500
