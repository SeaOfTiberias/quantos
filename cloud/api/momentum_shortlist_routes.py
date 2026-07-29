"""
QuantOS — Momentum + Base Quality Shortlist Routes
─────────────────────────────────────────────────────
Exposes core/discovery/momentum_shortlist.py's output (produced daily by
scripts/run_momentum_shortlist.py, deploy/systemd/quantos-momentum-shortlist.timer)
to the cockpit dashboard. Replaces the cockpit's use of the pure-Darvas
/discovery/watchlist endpoint (cloud/api/discovery_routes.py), which has had
no evidenced edge since S7-3 and no live feed since quantos-agent was
mothballed — this is a fresh feed, not a repurposing of that one, so the old
endpoint and its tests stay untouched.

This is a discretionary review aid, not a trading signal: no dry_run flag,
no execution path, nothing here is ever wired to broker.place_order().

Keyed by `universe` (2026-07-29: added a second scan, Nifty200 Momentum 30,
alongside the original Nifty Alpha 50 — a single wholesale-replace store
would have let the second script's daily sync silently clobber the first's).
The label is whatever scripts/run_momentum_shortlist.py derives from its
universe filename (e.g. "alpha50", "nifty200momentum30") — see that
script's `_universe_label()`.

Same auth split as every other read-only router in this app: POST (from the
standalone script, same "keys never leave this machine" trust boundary as
the agent) is guarded with X-Cloud-Secret; GET (from the cockpit's browser
JS) is intentionally public, same reasoning as cloud/api/discovery_routes.py.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["discovery"])

# In-memory mirrors, keyed by universe label — each replaced wholesale on
# every daily sync from that universe's scan.
_shortlist_store: dict[str, list[dict]] = {}
_last_synced_at: dict[str, datetime] = {}


class ShortlistEntryIn(BaseModel):
    symbol:         str
    close:          float
    momentum_pct:   float
    momentum_rank:  int
    momentum_tier:  str
    bucket:         str
    base_status:    str
    trend_up:       bool = False
    box_width_pct:  Optional[float] = None
    dist_to_ceil:   Optional[float] = None
    rr_ratio:       Optional[float] = None
    vol_ratio:      float = 0.0


class ShortlistSyncRequest(BaseModel):
    entries: list[ShortlistEntryIn]


@router.post("/momentum-shortlist/{universe}")
async def sync_momentum_shortlist(universe: str, payload: ShortlistSyncRequest,
                                   _auth=Depends(require_cloud_secret)):
    """Called once a day by scripts/run_momentum_shortlist.py, once per
    configured universe."""
    _shortlist_store[universe] = [e.model_dump() for e in payload.entries]
    _last_synced_at[universe] = datetime.now(timezone.utc)
    logger.info("Momentum shortlist synced (%s): %d entries",
                universe, len(_shortlist_store[universe]))
    return {"universe": universe, "synced": len(_shortlist_store[universe])}


@router.get("/momentum-shortlist/{universe}")
async def get_momentum_shortlist(universe: str):
    """Read by the cockpit dashboard, one call per panel/universe."""
    entries = _shortlist_store.get(universe, [])
    updated_at = _last_synced_at.get(universe)
    return {
        "entries": entries,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
