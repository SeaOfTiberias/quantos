"""
QuantOS — S8-3 Weekly Rotation Reporting Routes
──────────────────────────────────────────────────
The rotation strategy itself runs entirely on the local agent
(core/rotation/executor.py) — only the agent holds a connected broker
(ADR-01). This module exists purely so the cockpit and Telegram get
visibility into what the agent already did, exactly like
correlation_routes.py / discovery_routes.py do for their own agent-side
decisions. Nothing here influences a trading decision.

Unlike the discretionary Darvas flow, rotation trades are NEVER
PENDING_CONFIRMATION — the strategy runs fully automatically with no
per-trade human veto (a deliberate, narrowly-scoped carve-out; see
docs/SPRINT4_BACKLOG.md's S8-3 "Live execution engineering" section). So
each executed trade is persisted directly as status=EXECUTED, and the one
Telegram message this sends is an after-the-fact summary, not an approval
request.

Dry-run reports are NOT persisted as signals (no real trade happened — a
fake EXECUTED row would corrupt trade history/P&L), but they DO still get
the Telegram summary, tagged "(DRY RUN)", so the rollout period is actually
observable end to end.

POST /rotation/report is guarded by the same X-Cloud-Secret the agent
already sends to /signals*, /regime/sync, /discovery/watchlist, and
/correlation/sync.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret
from cloud.api.db import Signal, get_db
from cloud.api.notifier import send_error_alert, send_rotation_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rotation", tags=["rotation"])

STRATEGY_TAG = "weekly_rotation"

# Rotation trades aren't confluence-scored (no discretionary Claude
# pre-trade analysis for a systematic rotation) — the signals table's
# confluence_score column is NOT NULL, so this is an explicit "not
# applicable" sentinel rather than a real score, kept away from 0 so
# nothing mistakes it for a low-confluence rejection on the cockpit.
_NOT_APPLICABLE_CONFLUENCE = 100.0


class RotationTrade(BaseModel):
    symbol:       str
    quantity:     int
    price:        Optional[float] = None          # buys
    entry_price:  Optional[float] = None           # sells
    order_id:     Optional[str] = None


class SkippedBuy(BaseModel):
    symbol: str
    reason: str


class RotationReportRequest(BaseModel):
    dry_run:      bool
    buys:         list[RotationTrade] = []
    sells:        list[RotationTrade] = []
    skipped_buys: list[SkippedBuy] = []
    timestamp:    float


class RotationFailureRequest(BaseModel):
    error: str


def _new_signal_id() -> str:
    return f"SIG-{STRATEGY_TAG[:4].upper()}-{uuid.uuid4().hex[:8].upper()}"


async def _persist_trade(action: str, symbol: str, quantity: int, price: float) -> None:
    db = await get_db()
    now = datetime.now(timezone.utc)
    await db.insert_signal(Signal(
        signal_id=_new_signal_id(),
        user_id=os.getenv("DEFAULT_USER_ID", "system"),
        symbol=symbol,
        action=action,
        price=price,
        timeframe="1w",
        strategy=STRATEGY_TAG,
        confluence_score=_NOT_APPLICABLE_CONFLUENCE,
        status="EXECUTED",
        created_at=now,
        notified_at=now,
        executed_at=now,
        execution_price=price,
    ))


@router.post("/report")
async def report_rotation(payload: RotationReportRequest, _auth=Depends(require_cloud_secret)):
    """Called by the local agent once per weekly rebalance
    (agent/main.py _run_rotation_rebalance)."""
    if not payload.dry_run:
        for trade in payload.buys:
            try:
                await _persist_trade("BUY", trade.symbol, trade.quantity, trade.price or 0.0)
            except Exception as e:
                logger.error("Failed to persist rotation BUY for %s: %s", trade.symbol, e)
        for trade in payload.sells:
            try:
                await _persist_trade("SELL", trade.symbol, trade.quantity, trade.entry_price or 0.0)
            except Exception as e:
                logger.error("Failed to persist rotation SELL for %s: %s", trade.symbol, e)

    await send_rotation_summary(
        buys=[t.model_dump() for t in payload.buys],
        sells=[t.model_dump() for t in payload.sells],
        skipped_buys=[s.model_dump() for s in payload.skipped_buys],
        dry_run=payload.dry_run,
    )

    logger.info("Rotation report received: %d buys, %d sells, %d skipped (dry_run=%s)",
                len(payload.buys), len(payload.sells), len(payload.skipped_buys), payload.dry_run)
    return {"received": True}


@router.post("/failed")
async def report_rotation_failure(payload: RotationFailureRequest, _auth=Depends(require_cloud_secret)):
    """Called by scripts/run_rotation_rebalance.py when a scheduled weekly
    run raises (most likely a stale Fyers auth token, since this runs
    unattended via systemd timer — no interactive OAuth refresh possible).
    Without this, a missed weekly refresh would fail silently: the timer
    just logs a systemd failure nobody's watching."""
    logger.error("Rotation run failed: %s", payload.error)
    await send_error_alert("S8-3 weekly rotation", payload.error)
    return {"received": True}
