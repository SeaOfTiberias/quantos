"""
QuantOS — Open Positions Sync Routes
─────────────────────────────────────
Same reasoning as regime_routes.py / discovery_routes.py: only the local
agent ever holds a connected broker (ADR-01), so Railway can never know
live open positions itself — the agent pushes its broker-reported
positions (qty/entry/LTP/PnL already computed broker-side, see
core/brokers/base.py's Position) after every trailing-stop check.

POST /positions/sync is guarded by the same X-Cloud-Secret as /regime/sync
and /discovery/watchlist. GET /positions/status is public (read-only, no
credentials in the payload — same pattern as regime/discovery/correlation)
and feeds the cockpit's Open Positions panel.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/positions", tags=["positions"])

# In-memory mirror — replaced wholesale on every sync from the agent.
# Resets to None on every Railway redeploy, same as the other sync routes.
_synced_positions: Optional[list[dict]] = None
_synced_at: Optional[datetime] = None


class PositionEntry(BaseModel):
    symbol:   str
    qty:      int
    entry:    float
    ltp:      float
    pnl:      float
    pnl_pct:  float
    strategy: str = "unknown"


class PositionsSyncRequest(BaseModel):
    positions: list[PositionEntry]


@router.post("/sync")
async def sync_positions(payload: PositionsSyncRequest, _auth=Depends(require_cloud_secret)):
    """Called by the local agent (agent/main.py) after every trailing-stop check."""
    global _synced_positions, _synced_at
    _synced_positions = [p.model_dump() for p in payload.positions]
    _synced_at = datetime.now(timezone.utc)
    return {"synced": True, "count": len(_synced_positions)}


@router.get("/status")
async def positions_status():
    """
    Public read for the cockpit's Open Positions panel. `positions` is an
    empty list until the agent's first sync (or after a redeploy wipes the
    mirror) — same semantics as an agent with no open positions, which the
    cockpit's LIVE/STALE heartbeat badge already disambiguates from a dead
    agent.
    """
    return {
        "positions":  _synced_positions or [],
        "updated_at": _synced_at.isoformat() if _synced_at else None,
    }


def get_last_synced_at() -> Optional[datetime]:
    """Last time the agent pushed open positions."""
    return _synced_at


def get_synced_positions() -> list[dict]:
    """Read by cloud/analyst/chat.py for the analyst chat's live context."""
    return _synced_positions or []
