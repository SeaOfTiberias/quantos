"""
QuantOS — Correlation Sync Routes (S5-5 / P1-6)
────────────────────────────────────────────────
The correlation gate runs on the LOCAL AGENT, not here: only the agent
holds a connected Fyers broker to fetch the price history a correlation
check needs (ADR-01). So — exactly like regime and the discovery watchlist
— the agent runs the check at sizing time and pushes each decision here
purely so the cockpit can display it. This module stores nothing that any
trading decision depends on.

(This replaces the earlier US-08 `POST /correlation/check`, which tried to
run the check cloud-side against a `_correlation_service` that was never
assignable — the cloud has no broker — so it 503'd unconditionally and the
r>0.75 rejection existed only in unit tests. See docs/AUDIT_FINDINGS.md.)

POST /correlation/sync is guarded by the same X-Cloud-Secret the agent
already sends to /signals*, /regime/sync, and /discovery/watchlist.
GET /correlation/status is public (read-only aggregate, like the watchlist).
"""

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret
from core.risk.correlation import CORRELATION_THRESHOLD

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/correlation", tags=["correlation"])

# Rolling window of the agent's most recent gate decisions, newest last.
# In-memory and process-local (resets on Railway redeploy, like every other
# agent-synced mirror here) — it's a display feed, not a system of record.
_MAX_DECISIONS = 20
_decisions: "deque[dict]" = deque(maxlen=_MAX_DECISIONS)
_synced_at: Optional[datetime] = None


class CorrelationSyncRequest(BaseModel):
    candidate_symbol: str
    is_blocked:       bool
    max_correlation:  float
    correlated_with:  list[str] = []
    reason:           str = ""
    checked_at:       str            # ISO — when the agent ran the check


@router.post("/sync")
async def sync_correlation(payload: CorrelationSyncRequest, _auth=Depends(require_cloud_secret)):
    """Called by the local agent (agent/main.py) after each correlation gate
    check at sizing time — one decision per candidate evaluated."""
    global _synced_at
    _decisions.append({
        "candidate_symbol": payload.candidate_symbol,
        "is_blocked":       payload.is_blocked,
        "max_correlation":  payload.max_correlation,
        "correlated_with":  payload.correlated_with,
        "reason":           payload.reason,
        "checked_at":       payload.checked_at,
    })
    _synced_at = datetime.now(timezone.utc)
    logger.info("Correlation decision synced: %s blocked=%s maxcorr=%.2f",
                payload.candidate_symbol, payload.is_blocked, payload.max_correlation)
    return {"synced": True}


@router.get("/status")
async def correlation_status():
    """Recent correlation gate decisions for the cockpit — newest last."""
    return {
        "threshold":  CORRELATION_THRESHOLD,
        "decisions":  list(_decisions),
        "updated_at": _synced_at.isoformat() if _synced_at else None,
    }


def get_last_synced_at() -> Optional[datetime]:
    """Last time the agent pushed a correlation decision (agent-liveness signal,
    parallel to regime/watchlist sync timestamps)."""
    return _synced_at


def _reset() -> None:
    """Test hook — clear the decision feed."""
    global _synced_at
    _decisions.clear()
    _synced_at = None
