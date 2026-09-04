"""
QuantOS — Trade Intent (execution-layer handoff shape)
────────────────────────────────────────────────────────────
Fixes the SHAPE of "a trade should happen now", independent of which
producer decided it and which transport carries it. See
docs/ORB_EXECUTION_LAYER_DESIGN.md's "Layer 3" and "Webhook/queue
transport seam" sections.

core/orb_scalping's own layer-2 poller is, today, the only producer, and
constructs one of these in-process without ever serializing it — no
dispatcher, queue, or registry exists yet, deliberately: building one
before a second producer needs it would be speculative. A future,
less-mechanical strategy (or a discretionary cockpit "buy" button) should
produce this same shape and feed the same core/execution/order_service.py
functions, whether that reaches order_service via a direct in-process
call or a future webhook route is a transport decision for that later
work, not this one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TradeIntent:
    underlying: str            # e.g. "NIFTY" | "BANKNIFTY"
    direction: str             # "CALL" | "PUT"
    index_entry_price: float
    timestamp: datetime
    source: str = "orb_scalping"   # which producer emitted this
