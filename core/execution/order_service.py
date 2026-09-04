"""
QuantOS — Position Lifecycle Execution Service (layer 1)
────────────────────────────────────────────────────────────
docs/ORB_EXECUTION_LAYER_DESIGN.md's layer 1: deterministic code, no LLM
agents, no MCP. Talks to a broker, places orders, manages the resting
stop-loss order, and reports closure. Pure functions against
core.brokers.base.BrokerAdapter's interface -- mockable with a fake
broker in tests, no network, no Fyers.

Named to avoid confusion with core/execution/slicer.py and slicing.py,
which solve a different problem (intra-order depth-slicing of one large
order, orthogonal to managing a position's whole lifecycle).

Every function is `dry_run`-aware: dry_run logs the intended action and
returns without ever calling broker.place_order/modify_stop_loss, same
convention as rotation/rotation_pilot/options' own dry_run branches
elsewhere in this codebase.

`reconcile_position` is extracted from agent/main.py::_manage_open_
positions' inline logic (the only other place in this codebase that
already reconciles a position against broker.get_positions()/
get_order_history()) so ORB -- and any future strategy -- doesn't
reimplement it a fourth time. The extraction is read-only against
agent/main.py: the live Darvas path is not rewired to use this module in
this pass, so the already-live equity execution is untouched.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.brokers.base import (
    Order,
    OrderDirection,
    OrderStatus,
    OrderType,
    ProductType,
)

logger = logging.getLogger(__name__)

FILL_POLL_ATTEMPTS = 5
FILL_POLL_SLEEP_SECONDS = 1.0


@dataclass(frozen=True)
class EntryResult:
    """Result of placing one directional order (+ its paired protective
    stop, for an entry). `entry_order_id` names the order this call itself
    placed -- the closing order for flatten_position(), not necessarily
    the original entry."""
    dry_run: bool
    entry_order_id: Optional[str]
    stop_order_id: Optional[str]
    fill_price: Optional[float]
    quantity: int
    message: str = ""


@dataclass(frozen=True)
class ReconcileResult:
    still_open: bool
    exit_price: Optional[float] = None
    exit_timestamp: Optional[datetime] = None
    exit_reason: Optional[str] = None   # "sl_fill" | "manual" | None (still open)


def enter_position(broker, *, symbol: str, direction: OrderDirection, quantity: int,
                    product_type: ProductType, protective_stop_trigger: float,
                    tag: str, dry_run: bool) -> EntryResult:
    """MARKET entry, then (if not dry_run) a second SL_M stop order in the
    opposite direction -- Fyers v3 rejects Cover Orders ("CO" productType)
    outright, so a resting stop-loss is always a second, separate order,
    same as agent/main.py::_size_and_place_order."""
    if dry_run:
        logger.info(
            "[dry_run] would enter %s %s x%d, protective stop trigger=%.4f (tag=%s)",
            direction.value, symbol, quantity, protective_stop_trigger, tag,
        )
        return EntryResult(
            dry_run=True, entry_order_id=None, stop_order_id=None,
            fill_price=None, quantity=quantity,
            message=f"dry_run: would enter {direction.value} {symbol} x{quantity}",
        )

    entry_order = Order(
        symbol=symbol, direction=direction, quantity=quantity,
        order_type=OrderType.MARKET, product_type=product_type, tag=tag,
    )
    result = broker.place_order(entry_order)

    # MARKET orders usually fill within seconds -- poll briefly, don't
    # block indefinitely if it's slow. Same pattern as
    # agent/main.py::_size_and_place_order.
    fill_price = result.average_price
    for _ in range(FILL_POLL_ATTEMPTS):
        if fill_price:
            break
        time.sleep(FILL_POLL_SLEEP_SECONDS)
        try:
            fill_price = broker.get_order_status(result.order_id).average_price
        except Exception:
            break

    stop_direction = OrderDirection.SELL if direction == OrderDirection.BUY else OrderDirection.BUY
    stop_order = Order(
        symbol=symbol, direction=stop_direction, quantity=quantity,
        order_type=OrderType.SL_M, product_type=product_type,
        trigger_price=protective_stop_trigger, tag=f"{tag}-sl",
    )
    stop_result = broker.place_order(stop_order)

    return EntryResult(
        dry_run=False, entry_order_id=result.order_id, stop_order_id=stop_result.order_id,
        fill_price=fill_price, quantity=quantity,
        message=f"entered {direction.value} {symbol} x{quantity} @ {fill_price}",
    )


def update_stop(broker, *, stop_order_id: str, new_trigger_price: float, dry_run: bool) -> bool:
    """Wraps broker.modify_stop_loss(). NOTE: Fyers' modify_stop_loss is
    implemented but 'not yet verified against a live Fyers account' per
    core/brokers/fyers.py -- a known risk, not a blocker here since
    dry_run never calls it for real."""
    if dry_run:
        logger.info("[dry_run] would trail stop %s -> %.4f", stop_order_id, new_trigger_price)
        return True
    return broker.modify_stop_loss(stop_order_id, new_trigger_price)


def reconcile_position(broker, *, symbol: str, stop_order_id: str) -> ReconcileResult:
    """Cross-checks broker.get_positions() against `symbol`; if closed,
    walks broker.get_order_history() to find the fill -- the SL_M order
    filling is the exit itself; otherwise the latest executed fill for the
    symbol (e.g. a manual square-off), with the now-orphaned stop
    cancelled."""
    live_positions = {p.symbol: p for p in broker.get_positions()}
    live = live_positions.get(symbol)
    if live is not None and live.quantity != 0:
        return ReconcileResult(still_open=True)

    exit_price, exit_timestamp, exit_reason = None, None, None
    try:
        history = broker.get_order_history()
        sl_fill = next(
            (o for o in history
             if o.order_id == stop_order_id and o.status == OrderStatus.EXECUTED),
            None,
        )
        if sl_fill:
            exit_price = sl_fill.average_price
            exit_timestamp = sl_fill.timestamp
            exit_reason = "sl_fill"
        else:
            candidates = [
                o for o in history
                if o.symbol == symbol and o.order_id != stop_order_id
                and o.status == OrderStatus.EXECUTED
            ]
            if candidates:
                latest = max(candidates, key=lambda o: o.timestamp)
                exit_price = latest.average_price
                exit_timestamp = latest.timestamp
                exit_reason = "manual"
            try:
                broker.cancel_order(stop_order_id)
            except Exception:
                pass
    except Exception as e:
        logger.error("Failed to read order history while reconciling %s: %s", symbol, e)

    return ReconcileResult(
        still_open=False, exit_price=exit_price,
        exit_timestamp=exit_timestamp, exit_reason=exit_reason,
    )


def flatten_position(broker, *, symbol: str, direction: OrderDirection, quantity: int,
                      product_type: ProductType, stop_order_id: Optional[str],
                      tag: str, dry_run: bool) -> EntryResult:
    """Session-flatten (15:20 IST): an opposite-direction MARKET close, plus
    cancelling the resting stop order. `direction` is the ORIGINAL entry
    direction -- the closing direction is derived from it, not passed in."""
    close_direction = OrderDirection.SELL if direction == OrderDirection.BUY else OrderDirection.BUY

    if dry_run:
        logger.info("[dry_run] would flatten %s %s x%d (tag=%s)",
                     close_direction.value, symbol, quantity, tag)
        return EntryResult(
            dry_run=True, entry_order_id=None, stop_order_id=None,
            fill_price=None, quantity=quantity,
            message=f"dry_run: would flatten {symbol} x{quantity}",
        )

    if stop_order_id:
        try:
            broker.cancel_order(stop_order_id)
        except Exception as e:
            logger.warning("Failed to cancel resting stop %s before flatten: %s", stop_order_id, e)

    close_order = Order(
        symbol=symbol, direction=close_direction, quantity=quantity,
        order_type=OrderType.MARKET, product_type=product_type, tag=tag,
    )
    result = broker.place_order(close_order)
    return EntryResult(
        dry_run=False, entry_order_id=result.order_id, stop_order_id=None,
        fill_price=result.average_price, quantity=quantity,
        message=f"flattened {symbol} x{quantity}",
    )
