"""
QuantOS — Fill Reconciliation Routes (Sprint 6)
──────────────────────────────────────────────
One read endpoint that compares each executed signal's intended entry (the
alert `price`) against the actual broker fill (`execution_price`) and reports
realized entry slippage — per trade and in aggregate.

The headline number is `suggested_slippage_bps`: the empirical per-leg feed for
the S5-1 cost model's `slippage_bps` parameter. Realized trades use
DEFAULT_COST_MODEL (slippage 0, since fills already embed it), but backtests
need a realistic per-leg slippage assumption — this endpoint is where that
number comes from once real trades accrue.

GET is unauthenticated like the other cockpit read routes. It surfaces the same
class of per-trade data the cockpit already reads from `/signals` (symbol,
prices) plus aggregate slippage — no secrets. Single-user in practice (ADR-03).
"""

import logging

from fastapi import APIRouter

from cloud.api.db import get_db
from core.risk.fill_reconciliation import reconcile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

# How many recent signals to scan. reconcile() self-filters to the ones actually
# filled (has execution_price), so an unfiltered fetch is fine; this just bounds
# the window. 500 comfortably covers the 30–50-trade horizon Sprint 6 is gated on.
_SCAN_LIMIT = 500


@router.get("/slippage")
async def slippage_report():
    """
    Entry-slippage reconciliation across recent executed signals. Empty-but-valid
    (count 0) until trades with fills accrue.
    """
    db = await get_db()
    records = await db.fetch_recent_signals(limit=_SCAN_LIMIT)
    report = reconcile(records)
    return report.to_dict()
