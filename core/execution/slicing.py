"""
QuantOS — Order Slicing: the pure logic
────────────────────────────────────────
Given an order book snapshot and a quantity still to trade, decide how much to
send right now and what it should cost. No I/O, no broker, no clock — every
function here is deterministic given its inputs, so it can be unit-tested and
replayed over recorded depth. The loop that actually places orders lives in
core/execution/slicer.py.

The split is the same one core/rotation/ranker.py draws against executor.py:
one definition of the logic, imported by both the measurement and the live
path, so what gets measured cannot drift from what gets traded.

Why not just divide the quantity
────────────────────────────────
The naive version — total depth × participation rate, repeat until done — was
what prompted this module, and it fails in three ways that matter:

  • **Summing the whole book.** Taking 30% of depth summed across five price
    levels means deliberately crossing four of them. Participation limits
    exist to avoid moving the price; applying one to the aggregate guarantees
    you move it. Here `max_levels` bounds how deep a single slice may reach,
    and the participation rate applies to that bounded depth only.
  • **Dividing once.** A static plan assumes the book is unchanged after each
    fill. It never is. `next_slice` answers for the CURRENT snapshot and is
    meant to be called again after each fill against a fresh one.
  • **Degrading instead of refusing.** With an empty book the naive version
    produced one slice of 1 per unit — 2,000 orders for 2,000 units. A slice
    of zero with a stated reason is the correct answer when there is nothing
    to trade against.

What "cost" means here
──────────────────────
`slippage_bps` is measured against the arrival mid — the mid at the moment the
decision to trade was made — which makes it implementation shortfall, the
standard measure for execution quality. It is NOT profit and loss, and it is
not what core/backtest/parser.py's `has_positive_edge` gate scores. A slicer
does not generate trades; it changes how an already-decided trade reaches the
market, so PF and Sharpe are the wrong instruments for it. The right question
is "did slicing cost fewer basis points than sending it in one lump", and
`simulate_execution` is what answers it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from core.brokers.base import DepthLevel, MarketDepth, OrderDirection

logger = logging.getLogger(__name__)

# Fraction of visible depth a single slice may consume. 0.30 is a common
# starting point for participation-limited execution; it is not tuned against
# anything here and should not be treated as calibrated.
DEFAULT_PARTICIPATION_RATE = 0.30

# How many price levels one slice may reach through. Three keeps a slice near
# the touch; raising it trades impact for speed.
DEFAULT_MAX_LEVELS = 3


@dataclass(frozen=True)
class SlicingPolicy:
    """The constraints a slice must satisfy. All limits, no strategy."""

    participation_rate: float = DEFAULT_PARTICIPATION_RATE
    max_levels: int = DEFAULT_MAX_LEVELS
    max_slice_qty: Optional[int] = None      # exchange/broker freeze limit
    min_slice_qty: int = 1                   # do not send dust
    lot_size: int = 1                        # round down to whole lots
    max_slippage_bps: Optional[float] = None  # refuse a slice costing more

    def __post_init__(self) -> None:
        if not 0.0 < self.participation_rate <= 1.0:
            raise ValueError("participation_rate must be in (0, 1]")
        if self.max_levels < 1:
            raise ValueError("max_levels must be at least 1")
        if self.lot_size < 1:
            raise ValueError("lot_size must be at least 1")
        if self.min_slice_qty < 1:
            raise ValueError("min_slice_qty must be at least 1")


@dataclass(frozen=True)
class BookWalk:
    """The result of consuming `filled` units from one side of the book."""
    filled: int
    average_price: Optional[float]
    levels_crossed: int
    exhausted: bool          # ran out of displayed depth before filling

    @property
    def notional(self) -> float:
        return (self.average_price or 0.0) * self.filled


@dataclass(frozen=True)
class SliceDecision:
    """How much to send now, and what it is expected to cost.

    `quantity == 0` means do not trade against this snapshot. That is a normal
    outcome — thin book, spread too wide, remainder below the minimum — and
    `reason` always says which.
    """
    quantity: int
    reason: str
    expected_price: Optional[float] = None
    slippage_bps: Optional[float] = None
    levels_crossed: int = 0
    available_qty: int = 0        # displayed depth within max_levels

    @property
    def should_trade(self) -> bool:
        return self.quantity > 0


def walk_book(levels: Sequence[DepthLevel], quantity: int) -> BookWalk:
    """Consume `quantity` from `levels` (best price first) and report the
    volume-weighted average price it would achieve.

    This is the primitive everything else is built on: it is what turns "how
    many units" into "at what price", and therefore what makes market impact
    a number rather than a worry.
    """
    if quantity <= 0:
        return BookWalk(filled=0, average_price=None, levels_crossed=0, exhausted=False)

    remaining = quantity
    notional = 0.0
    crossed = 0

    for level in levels:
        if remaining <= 0:
            break
        if level.quantity <= 0:
            continue
        take = min(remaining, level.quantity)
        notional += take * level.price
        remaining -= take
        crossed += 1

    filled = quantity - remaining
    if filled == 0:
        return BookWalk(filled=0, average_price=None, levels_crossed=0, exhausted=True)

    return BookWalk(
        filled=filled,
        average_price=notional / filled,
        levels_crossed=crossed,
        exhausted=remaining > 0,
    )


def available_depth(levels: Sequence[DepthLevel], max_levels: int) -> int:
    """Displayed quantity within the first `max_levels` price levels.

    Bounded deliberately — see the module docstring on why summing the whole
    book defeats a participation limit.
    """
    return sum(l.quantity for l in levels[:max_levels] if l.quantity > 0)


def next_slice(
    depth: MarketDepth,
    direction: OrderDirection,
    remaining_qty: int,
    policy: SlicingPolicy = SlicingPolicy(),
    arrival_price: Optional[float] = None,
) -> SliceDecision:
    """Decide the next slice against ONE depth snapshot.

    Call again with a fresh snapshot after each fill. `arrival_price` is the
    mid at the moment the parent order was decided; slippage is measured
    against it, and against the current mid when it is not supplied.
    """
    if remaining_qty <= 0:
        return SliceDecision(quantity=0, reason="nothing left to trade")

    levels = depth.side(direction)
    if not levels:
        return SliceDecision(
            quantity=0,
            reason=f"no {'ask' if direction == OrderDirection.BUY else 'bid'} "
                   f"side quoted for {depth.symbol}",
        )

    visible = available_depth(levels, policy.max_levels)
    if visible <= 0:
        # The naive implementation produced a slice of 1 here and repeated it
        # once per unit. Refusing is the only sane answer to an empty book.
        return SliceDecision(
            quantity=0, available_qty=0,
            reason=f"no displayed depth in the top {policy.max_levels} levels",
        )

    # Participation applies to the BOUNDED depth, not the whole book.
    budget = int(visible * policy.participation_rate)
    candidate = min(remaining_qty, max(budget, 0))
    if policy.max_slice_qty is not None:
        candidate = min(candidate, policy.max_slice_qty)

    # Round down to whole lots. Rounding up would breach the participation
    # limit the caller asked for.
    candidate = (candidate // policy.lot_size) * policy.lot_size

    if candidate <= 0:
        return SliceDecision(
            quantity=0, available_qty=visible,
            reason=(f"{visible} units visible; {policy.participation_rate:.0%} of that "
                    f"is below one lot of {policy.lot_size}"),
        )

    if candidate < policy.min_slice_qty:
        # The tail of an order is allowed through even when small — otherwise
        # the last few units could never be traded. A large remainder waits.
        if remaining_qty > policy.min_slice_qty:
            return SliceDecision(
                quantity=0, available_qty=visible,
                reason=(f"slice {candidate} below min_slice_qty {policy.min_slice_qty} "
                        f"and {remaining_qty} still to trade — waiting for depth"),
            )
        candidate = remaining_qty

    walk = walk_book(levels, candidate)
    if walk.average_price is None:
        return SliceDecision(quantity=0, available_qty=visible,
                             reason="book walk filled nothing")

    reference = arrival_price if arrival_price is not None else depth.mid
    slippage = _slippage_bps(walk.average_price, reference, direction)

    if (policy.max_slippage_bps is not None and slippage is not None
            and slippage > policy.max_slippage_bps):
        return SliceDecision(
            quantity=0, available_qty=visible, expected_price=walk.average_price,
            slippage_bps=slippage, levels_crossed=walk.levels_crossed,
            reason=(f"expected slippage {slippage:.1f}bps exceeds the "
                    f"{policy.max_slippage_bps:.1f}bps limit"),
        )

    return SliceDecision(
        quantity=walk.filled,
        reason=(f"{walk.filled} of {remaining_qty} against {visible} visible "
                f"across {walk.levels_crossed} level(s)"),
        expected_price=walk.average_price,
        slippage_bps=slippage,
        levels_crossed=walk.levels_crossed,
        available_qty=visible,
    )


def _slippage_bps(fill_price: float, reference: Optional[float],
                  direction: OrderDirection) -> Optional[float]:
    """Implementation shortfall in basis points, signed so POSITIVE is always
    adverse regardless of side — paying above the reference when buying, or
    receiving below it when selling."""
    if reference is None or reference <= 0:
        return None
    raw = (fill_price - reference) / reference * 10_000.0
    return raw if direction == OrderDirection.BUY else -raw


# ── Measurement ────────────────────────────────────────────────────────────

@dataclass
class ExecutionSimulation:
    """What a sliced execution would have cost, replayed over recorded depth."""
    symbol: str
    direction: OrderDirection
    target_qty: int
    filled_qty: int = 0
    slices: list[SliceDecision] = field(default_factory=list)
    arrival_price: Optional[float] = None
    unfilled_reason: str = ""

    @property
    def average_price(self) -> Optional[float]:
        traded = [s for s in self.slices if s.should_trade and s.expected_price]
        if not traded:
            return None
        notional = sum(s.expected_price * s.quantity for s in traded)
        return notional / sum(s.quantity for s in traded)

    @property
    def slippage_bps(self) -> Optional[float]:
        """Shortfall of the WHOLE execution against the arrival price — the
        number to compare against an unsliced baseline."""
        return _slippage_bps(self.average_price, self.arrival_price, self.direction) \
            if self.average_price is not None else None

    @property
    def is_complete(self) -> bool:
        return self.filled_qty >= self.target_qty

    def summary(self) -> str:
        price = f"{self.average_price:,.2f}" if self.average_price is not None else "—"
        slip = f"{self.slippage_bps:+.1f}bps" if self.slippage_bps is not None else "—"
        return (f"{self.direction.value} {self.filled_qty}/{self.target_qty} "
                f"{self.symbol} @ {price} ({slip} vs arrival) in "
                f"{len([s for s in self.slices if s.should_trade])} slice(s)")


def simulate_execution(
    snapshots: Iterable[MarketDepth],
    direction: OrderDirection,
    target_qty: int,
    policy: SlicingPolicy = SlicingPolicy(),
) -> ExecutionSimulation:
    """Replay a sliced order over a sequence of recorded depth snapshots.

    This is the measurement harness. Run it once with a slicing policy and
    once with `participation_rate=1.0, max_levels=99` (i.e. send it all at
    once) and compare `slippage_bps` — that difference, in basis points, is
    what slicing bought. It is the honest way to evaluate an execution
    algorithm, and it is a different question from whether a STRATEGY has
    edge.

    Assumes each slice fills fully at its walked price and that the next
    snapshot reflects the market afterwards. Real fills are partial and the
    book reacts; treat the result as an upper bound on the benefit.
    """
    snapshots = list(snapshots)
    if not snapshots:
        return ExecutionSimulation(symbol="?", direction=direction,
                                   target_qty=target_qty,
                                   unfilled_reason="no depth snapshots supplied")

    sim = ExecutionSimulation(
        symbol=snapshots[0].symbol, direction=direction, target_qty=target_qty,
        arrival_price=snapshots[0].mid,
    )

    remaining = target_qty
    for depth in snapshots:
        if remaining <= 0:
            break
        decision = next_slice(depth, direction, remaining, policy,
                              arrival_price=sim.arrival_price)
        sim.slices.append(decision)
        if decision.should_trade:
            remaining -= decision.quantity
            sim.filled_qty += decision.quantity

    if remaining > 0:
        last = sim.slices[-1].reason if sim.slices else "no slices attempted"
        sim.unfilled_reason = (f"{remaining} of {target_qty} unfilled after "
                               f"{len(snapshots)} snapshot(s) — last: {last}")
    return sim
