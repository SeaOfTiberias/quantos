"""
QuantOS — Market Snapshot Routes
──────────────────────────────────
Deliberately NOT a regime classifier. cloud/api/regime_routes.py's full
bull/bear/ranging classification (trend + VIX + breadth) depends entirely
on the mothballed quantos-agent, which hasn't synced since Darvas was
disabled — that endpoint is left alone (still correctly returns None/stale
to anything reading it, which is honest) rather than faked here.

This is three plain facts, synced daily by
scripts/run_momentum_shortlist.py (which already connects to the broker
for the momentum scans, at no extra systemd/cron cost): NIFTY's LTP and
short-term trend (EMA9 > EMA21, the exact same check and thresholds
core/discovery/momentum_shortlist.py applies to every stock in the
shortlist, so the cockpit's NIFTY reading and its per-stock readings never
use two different definitions of "uptrend"), and India VIX's LTP. No
classification layered on top — the cockpit shows the numbers and lets a
human decide what they mean.

Same auth split as every other read-only router in this app: POST (from
the standalone script) is guarded with X-Cloud-Secret; GET (cockpit
browser JS) is public.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market", tags=["market"])

_snapshot: Optional[dict] = None
_synced_at: Optional[datetime] = None


class MarketSnapshotIn(BaseModel):
    nifty_ltp:      float
    nifty_trend_up: bool
    vix_current:    Optional[float] = None


@router.post("/snapshot")
async def sync_market_snapshot(payload: MarketSnapshotIn,
                                _auth=Depends(require_cloud_secret)):
    """Called once a day by scripts/run_momentum_shortlist.py."""
    global _snapshot, _synced_at
    _snapshot = payload.model_dump()
    _synced_at = datetime.now(timezone.utc)
    logger.info("Market snapshot synced: nifty_ltp=%.1f trend_up=%s vix=%s",
                payload.nifty_ltp, payload.nifty_trend_up, payload.vix_current)
    return {"synced": True}


@router.get("/snapshot")
async def get_market_snapshot():
    """Read by the cockpit dashboard."""
    return {
        **(_snapshot or {"nifty_ltp": None, "nifty_trend_up": None, "vix_current": None}),
        "updated_at": _synced_at.isoformat() if _synced_at else None,
    }


def get_last_synced_at() -> Optional[datetime]:
    """Last time the daily script pushed a snapshot — folded into
    cloud/api/observability_routes.py's heartbeat as a liveness signal for
    the current (post-agent) daily automation."""
    return _synced_at
