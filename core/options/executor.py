"""
QuantOS — Options Signal Executor
────────────────────────────────────
Places every leg of a CONFIRMED multi-leg options signal via the broker,
sequentially. If any leg after the first is rejected, immediately market-
flattens every leg that already filled in this batch — the user's explicit
decision (2026-07-21) over the alternative of just alerting and leaving a
naked position, on the reasoning that a bounded automatic response beats
an unbounded-risk gap while waiting for a human to see a Telegram alert.
This is the first case in this codebase of the agent placing an order that
wasn't itself individually confirmed by the user — narrowly scoped to
closing a position the user DID confirm opening, never to opening a new one.

product_type=MARGIN (not INTRADAY): the whole point of this strategy is to
hold to expiry (see the design decision in quantos-dashboard-polish-
next-session), and INTRADAY would get auto-squared-off by the broker
before market close, silently destroying that. NOT yet live-verified that
Fyers accepts MARGIN for options legs specifically (confirmed live only
for equities, core/brokers/fyers.py's _PRODUCT_MAP comment) — same
category of risk as chain_builder.py's unverified field-name assumptions.

Capital is pre-checked only for net-DEBIT strategies (straightforward:
required cash = net debit x lot size x lots). Net-credit / zero-cost
strategies (iron condor, short strangle) need a real margin calculator to
pre-check accurately, which isn't built here — the broker's own order
rejection remains the authoritative gate for those, same as it always was
for every other order this codebase places.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.brokers.base import (
    BrokerError, Order, OrderDirection, OrderType, ProductType,
)

logger = logging.getLogger(__name__)

AUTOFLATTEN_TAG = "quantos-options-autoflatten"


@dataclass
class LegFill:
    leg:         dict
    order_id:    str
    fill_price:  Optional[float]


@dataclass
class FlattenResult:
    leg:        dict
    flattened:  bool
    order_id:   Optional[str] = None
    error:      Optional[str] = None


@dataclass
class ExecutionOutcome:
    success:          bool
    filled_legs:      list[LegFill] = field(default_factory=list)
    failed_leg:       Optional[dict] = None
    error:            Optional[str] = None
    flatten_results:  list[FlattenResult] = field(default_factory=list)


def _net_debit_required(legs: list[dict]) -> float:
    """Positive = net cash required (debit strategy). Zero or negative =
    net credit received — not pre-checked here, see module docstring."""
    total = 0.0
    for leg in legs:
        sign = 1 if leg["action"] == "BUY" else -1
        total += sign * leg["premium"] * leg["lot_size"] * leg["quantity"]
    return total


def check_capital(broker, legs: list[dict]) -> Optional[str]:
    """Returns a refusal reason string if a net-debit spread can't be
    afforded, else None (also None for credit/zero-cost strategies — see
    module docstring)."""
    required = _net_debit_required(legs)
    if required <= 0:
        return None
    try:
        funds = broker.get_funds()
    except BrokerError as e:
        return f"Could not verify available funds: {e}"
    available = funds.get("available", 0.0)
    if required > available:
        return (f"Insufficient funds: spread needs ~INR {required:,.2f} net debit, "
                f"only INR {available:,.2f} available")
    return None


def _place_leg(broker, leg: dict, tag: str) -> LegFill:
    order = Order(
        symbol=leg["symbol"],
        direction=OrderDirection.BUY if leg["action"] == "BUY" else OrderDirection.SELL,
        quantity=leg["quantity"] * leg["lot_size"],
        order_type=OrderType.MARKET,
        product_type=ProductType.MARGIN,
        tag=tag,
    )
    result = broker.place_order(order)
    return LegFill(leg=leg, order_id=result.order_id, fill_price=result.average_price)


def _flatten_all(broker, filled_legs: list[LegFill]) -> list[FlattenResult]:
    results = []
    for lf in filled_legs:
        leg = lf.leg
        flatten_direction = (OrderDirection.SELL if leg["action"] == "BUY"
                              else OrderDirection.BUY)
        order = Order(
            symbol=leg["symbol"], direction=flatten_direction,
            quantity=leg["quantity"] * leg["lot_size"],
            order_type=OrderType.MARKET, product_type=ProductType.MARGIN,
            tag=AUTOFLATTEN_TAG,
        )
        try:
            result = broker.place_order(order)
            results.append(FlattenResult(leg=leg, flattened=True, order_id=result.order_id))
            logger.warning("Auto-flattened %s %s %s (order %s)",
                           leg["action"], leg["option_type"], leg["strike"], result.order_id)
        except BrokerError as e:
            results.append(FlattenResult(leg=leg, flattened=False, error=str(e)))
            logger.critical(
                "AUTO-FLATTEN FAILED for %s %s %s — position is NAKED, manual "
                "intervention required NOW: %s",
                leg["action"], leg["option_type"], leg["strike"], e,
            )
    return results


def execute_confirmed_signal(broker, signal_id: str, legs: list[dict]) -> ExecutionOutcome:
    """
    Places every leg sequentially. On the first rejection, flattens every
    leg that already filled in this call before returning — never leaves
    the function with a still-open, un-flattened partial position without
    it being reflected in the returned flatten_results for the caller to
    alert on.
    """
    capital_refusal = check_capital(broker, legs)
    if capital_refusal:
        return ExecutionOutcome(success=False, error=capital_refusal)

    filled: list[LegFill] = []
    tag = f"quantos-opt-{signal_id}"[:20]  # Fyers order tags are length-limited

    for leg in legs:
        try:
            filled.append(_place_leg(broker, leg, tag))
        except BrokerError as e:
            logger.error("[%s] Leg failed (%s %s %s): %s — flattening %d already-filled leg(s)",
                         signal_id, leg["action"], leg["option_type"], leg["strike"],
                         e, len(filled))
            flatten_results = _flatten_all(broker, filled)
            return ExecutionOutcome(
                success=False, filled_legs=filled, failed_leg=leg,
                error=str(e), flatten_results=flatten_results,
            )

    return ExecutionOutcome(success=True, filled_legs=filled)
