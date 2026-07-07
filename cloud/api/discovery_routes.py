"""
QuantOS — Discovery Watchlist Routes
───────────────────────────────────────
Exposes Stage A's discovery watchlist (core/darvas/weekly_discovery.py +
agent/discovery_watchlist.py) to the cockpit dashboard.

The watchlist itself only ever lives on the local agent's machine
(~/.quantos/discovery_watchlist.json) — same "keys never leave this
machine" reasoning as the rest of the agent (ADR-01). This module is just
a thin in-memory mirror the agent pushes to after every Stage A/B run, so
the cockpit has something to read without needing broker access itself.

POST is guarded with the same X-Cloud-Secret the agent already sends to
/signals* (cloud/api/auth.py) — it's a write endpoint. GET is left
unauthenticated, matching every other read-only router in this app
(screener/risk/events/etc.) — the cockpit is a browser client, and
embedding the cloud secret in frontend JS would defeat the point of
guarding it.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["discovery"])

# In-memory mirror — replaced wholesale on every sync from the agent.
_watchlist_store: dict[str, dict] = {}
_last_synced_at: Optional[datetime] = None


class WatchlistEntryIn(BaseModel):
    symbol:                str
    date_added:             str
    date_updated:           str
    status:                 str
    prev_status:            str = ""
    alert_tier:             str = ""
    box_ceiling:            Optional[float] = None
    box_floor:              Optional[float] = None
    box_width_pct:          Optional[float] = None
    dist_to_ceil:           Optional[float] = None
    sl_price:               Optional[float] = None
    mm_target:              Optional[float] = None
    rr_ratio:               Optional[float] = None
    days_in_box:            Optional[int] = None
    last_fired_date:        str = ""
    last_fired_signal_id:   str = ""
    last_fired_confluence:  Optional[float] = None
    last_fired_status:      str = ""
    entry_price:            Optional[float] = None
    quantity:               Optional[int] = None


class WatchlistSyncRequest(BaseModel):
    entries: list[WatchlistEntryIn]


@router.post("/watchlist")
async def sync_watchlist(payload: WatchlistSyncRequest,
                          _auth=Depends(require_cloud_secret)):
    """Called by the local agent (agent/main.py) after every Stage A
    discovery scan and Stage B granular timing pass."""
    global _watchlist_store, _last_synced_at
    _watchlist_store = {e.symbol: e.model_dump() for e in payload.entries}
    _last_synced_at = datetime.now(timezone.utc)
    logger.info("Discovery watchlist synced: %d entries", len(_watchlist_store))
    return {"synced": len(_watchlist_store)}


@router.get("/watchlist")
async def get_watchlist():
    """Read by the cockpit dashboard."""
    return {
        "entries": list(_watchlist_store.values()),
        "updated_at": _last_synced_at.isoformat() if _last_synced_at else None,
    }
