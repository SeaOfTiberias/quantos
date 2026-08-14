"""
QuantOS — order execution mechanics.

Concerned with HOW a decided order reaches the market, not WHETHER to trade.
Nothing here generates a signal, so nothing here is scored by
core/backtest/parser.py's `has_positive_edge` bar — execution quality is
measured as implementation shortfall in basis points against an unsliced
baseline (see core/execution/slicing.simulate_execution).

    core/execution/slicing.py   pure: depth in, slice decision out
    core/execution/slicer.py    the loop: broker, orders, clock

Credit: the depth-aware slicing idea came from a derivatives-terminal design
discussed publicly by Ankit Rai and Aniketh Dsouza. The participation-rate
approach is standard execution practice; this is an independent implementation
against QuantOS's own broker interface.
"""

from core.execution.slicing import (
    BookWalk, ExecutionSimulation, SliceDecision, SlicingPolicy,
    available_depth, next_slice, simulate_execution, walk_book,
)

__all__ = [
    "BookWalk", "ExecutionSimulation", "SliceDecision", "SlicingPolicy",
    "available_depth", "next_slice", "simulate_execution", "walk_book",
]
