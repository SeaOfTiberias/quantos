"""
QuantOS — Order Slicing: the execution loop
────────────────────────────────────────────
Drives core/execution/slicing.py against a live broker: read depth, decide a
slice, place it, wait, repeat. Everything that touches the market or the clock
is here; everything decidable is in slicing.py, so the logic can be measured
without a broker and cannot drift from what is measured.

Refusals, and why they are refusals
───────────────────────────────────
This module declines to trade more readily than most execution code, because
every one of these conditions means the thing that makes slicing worthwhile is
absent:

  • **Broker has no depth endpoint.** `get_market_depth` raises
    NotImplementedError. The tempting fallback — send it unsliced — is
    precisely the outcome slicing exists to prevent, so this aborts instead.
  • **Kill switch tripped.** agent/risk_guard's global halt refuses new
    entries. A slicer mid-order is a new entry for every remaining slice, so
    it stops adding and reports what it managed. Consistent with
    core/rotation/pilot_executor.py's "refuse entries, keep managing exits".
  • **Book has gone.** Repeated zero-quantity decisions mean the depth that
    justified starting has evaporated. After `max_idle_rounds` it stops
    rather than spinning.

A partially filled parent order is a real outcome, not a failure — the report
carries what filled, what did not, and why, so the caller can decide whether to
chase, wait, or abandon.

Live-verification status
────────────────────────
NOT YET RUN AGAINST A REAL BOOK. The depth parsing in
core/brokers/fyers.py's get_market_depth() is written from the Fyers SDK's
documented shape, not a captured response — same category of risk as
core/options/chain_builder.py, which carries the same warning. Run it in
`dry_run=True` against a live token and log a raw snapshot before trusting it
with an order.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.brokers.base import (
    BrokerAdapter, MarketDepth, Order, OrderDirection, OrderType, ProductType,
)
from core.execution.slicing import SliceDecision, SlicingPolicy, _slippage_bps, next_slice

logger = logging.getLogger(__name__)

# Pause between slices. Long enough for the book to refresh and for a resting
# order to be absorbed; short enough that a parent order completes in a
# sensible window. Not tuned against anything.
DEFAULT_SLICE_DELAY_SECONDS = 2.0

# Consecutive "do not trade" decisions tolerated before giving up.
DEFAULT_MAX_IDLE_ROUNDS = 5


class SlicerError(RuntimeError):
    """The sliced execution could not be attempted at all."""


@dataclass
class SlicedFill:
    """One placed slice and what came back."""
    quantity: int
    order_id: Optional[str]
    expected_price: Optional[float]
    fill_price: Optional[float]
    slippage_bps: Optional[float]
    dry_run: bool = False
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class SlicedExecutionReport:
    """The outcome of one parent order."""
    symbol: str
    direction: OrderDirection
    target_qty: int
    arrival_price: Optional[float] = None
    fills: list[SlicedFill] = field(default_factory=list)
    skipped: list[SliceDecision] = field(default_factory=list)
    aborted_reason: str = ""
    dry_run: bool = True

    @property
    def filled_qty(self) -> int:
        return sum(f.quantity for f in self.fills if f.succeeded)

    @property
    def is_complete(self) -> bool:
        return self.filled_qty >= self.target_qty

    @property
    def average_price(self) -> Optional[float]:
        priced = [f for f in self.fills
                  if f.succeeded and (f.fill_price or f.expected_price)]
        if not priced:
            return None
        notional = sum((f.fill_price or f.expected_price) * f.quantity for f in priced)
        return notional / sum(f.quantity for f in priced)

    @property
    def slippage_bps(self) -> Optional[float]:
        """Realised implementation shortfall for the whole parent order."""
        if self.average_price is None:
            return None
        return _slippage_bps(self.average_price, self.arrival_price, self.direction)

    def summary(self) -> str:
        price = f"{self.average_price:,.2f}" if self.average_price is not None else "—"
        slip = f"{self.slippage_bps:+.1f}bps" if self.slippage_bps is not None else "—"
        tag = "[DRY RUN] " if self.dry_run else ""
        tail = f" ABORTED: {self.aborted_reason}" if self.aborted_reason else ""
        return (f"{tag}{self.direction.value} {self.filled_qty}/{self.target_qty} "
                f"{self.symbol} @ {price} ({slip} vs arrival), "
                f"{len(self.fills)} slice(s){tail}")


def execute_sliced(
    broker: BrokerAdapter,
    symbol: str,
    direction: OrderDirection,
    total_qty: int,
    *,
    policy: SlicingPolicy = SlicingPolicy(),
    product_type: ProductType = ProductType.CNC,
    tag: str = "sliced",
    dry_run: bool = True,
    slice_delay_seconds: float = DEFAULT_SLICE_DELAY_SECONDS,
    max_idle_rounds: int = DEFAULT_MAX_IDLE_ROUNDS,
    halt_check: Optional[Callable[[], Optional[str]]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> SlicedExecutionReport:
    """Place `total_qty` of `symbol` in depth-aware slices.

    `dry_run` defaults True, matching every other real-order path in this
    codebase (core/rotation/executor.py, pilot_executor.py). Flip it only
    after watching a live-data dry run.

    `halt_check` is injected rather than imported so this module has no
    dependency on the agent package; pass `agent.risk_guard.read_halt_reason`.
    `sleep` is injected so tests do not spend real seconds.
    """
    report = SlicedExecutionReport(symbol=symbol, direction=direction,
                                   target_qty=total_qty, dry_run=dry_run)

    if total_qty <= 0:
        report.aborted_reason = f"total_qty={total_qty} is not positive"
        return report

    try:
        depth = broker.get_market_depth(symbol)
    except NotImplementedError as e:
        # Deliberately not falling back to an unsliced order — that is the
        # outcome this whole module exists to avoid.
        raise SlicerError(
            f"{type(broker).__name__} cannot supply market depth, so the order "
            f"cannot be sliced. Refusing rather than sending {total_qty} "
            f"{symbol} as one order."
        ) from e
    except Exception as e:
        report.aborted_reason = f"initial depth fetch failed: {e}"
        logger.error("Slicer: %s", report.aborted_reason)
        return report

    report.arrival_price = depth.mid
    if report.arrival_price is None:
        report.aborted_reason = (
            f"{symbol} has no two-sided quote (bid={depth.best_bid}, "
            f"ask={depth.best_ask}) — no arrival price to measure against")
        logger.warning("Slicer: %s", report.aborted_reason)
        return report

    logger.info("Slicer: %s %d %s, arrival mid %.2f, spread %.1fbps (dry_run=%s)",
                direction.value, total_qty, symbol, report.arrival_price,
                depth.spread_bps or 0.0, dry_run)

    remaining = total_qty
    idle_rounds = 0

    while remaining > 0:
        if halt_check is not None:
            reason = halt_check()
            if reason:
                report.aborted_reason = f"trading halted: {reason}"
                logger.warning("Slicer: halted mid-order with %d of %d unfilled — %s",
                               remaining, total_qty, reason)
                break

        decision = next_slice(depth, direction, remaining, policy,
                              arrival_price=report.arrival_price)

        if not decision.should_trade:
            report.skipped.append(decision)
            idle_rounds += 1
            if idle_rounds >= max_idle_rounds:
                report.aborted_reason = (
                    f"{idle_rounds} consecutive rounds with no tradable depth — "
                    f"last: {decision.reason}")
                logger.warning("Slicer: giving up with %d of %d unfilled — %s",
                               remaining, total_qty, decision.reason)
                break
            sleep(slice_delay_seconds)
            depth = _refresh(broker, symbol, depth)
            continue

        idle_rounds = 0
        fill = _place(broker, symbol, direction, decision, product_type, tag,
                      report.arrival_price, dry_run)
        report.fills.append(fill)

        if not fill.succeeded:
            report.aborted_reason = f"slice failed: {fill.error}"
            logger.error("Slicer: aborting with %d of %d unfilled — %s",
                         remaining, total_qty, fill.error)
            break

        remaining -= fill.quantity
        if remaining <= 0:
            break

        sleep(slice_delay_seconds)
        depth = _refresh(broker, symbol, depth)

    logger.info("Slicer: %s", report.summary())
    return report


def _refresh(broker: BrokerAdapter, symbol: str, previous: MarketDepth) -> MarketDepth:
    """Re-read the book. On failure keep the previous snapshot — the next
    `next_slice` will simply decide against stale depth, and the idle-round
    counter ends the loop if it stays broken. Better than aborting an order
    that is already partly done."""
    try:
        return broker.get_market_depth(symbol)
    except Exception as e:
        logger.warning("Slicer: depth refresh failed for %s (%s) — reusing the "
                       "previous snapshot", symbol, e)
        return previous


def _place(broker: BrokerAdapter, symbol: str, direction: OrderDirection,
           decision: SliceDecision, product_type: ProductType, tag: str,
           arrival_price: Optional[float], dry_run: bool) -> SlicedFill:
    if dry_run:
        logger.info("[DRY RUN] Slicer would %s %d %s @ ~%.2f (%.1fbps, %d level(s))",
                    direction.value, decision.quantity, symbol,
                    decision.expected_price or 0.0, decision.slippage_bps or 0.0,
                    decision.levels_crossed)
        return SlicedFill(
            quantity=decision.quantity, order_id=None,
            expected_price=decision.expected_price, fill_price=None,
            slippage_bps=decision.slippage_bps, dry_run=True,
        )

    try:
        result = broker.place_order(Order(
            symbol=symbol, direction=direction, quantity=decision.quantity,
            order_type=OrderType.MARKET, product_type=product_type, tag=tag,
        ))
    except Exception as e:
        return SlicedFill(quantity=0, order_id=None,
                          expected_price=decision.expected_price, fill_price=None,
                          slippage_bps=None, error=str(e))

    fill_price = getattr(result, "average_price", None) or decision.expected_price
    return SlicedFill(
        quantity=decision.quantity,
        order_id=getattr(result, "order_id", None),
        expected_price=decision.expected_price,
        fill_price=fill_price,
        slippage_bps=_slippage_bps(fill_price, arrival_price, direction),
    )
