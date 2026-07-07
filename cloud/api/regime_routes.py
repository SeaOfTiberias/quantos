"""
QuantOS — Regime Sync Routes
──────────────────────────────
Exposes the market regime engine (core/regime/service.py) to the rest of
the cloud API. Same reasoning as cloud/api/discovery_routes.py: the
Fyers broker connection only ever exists on the local agent's machine
(ADR-01), so Railway can never instantiate RegimeService itself — the
agent runs it locally (it already has a connected broker) and pushes the
classified result here after every refresh.

POST is guarded with the same X-Cloud-Secret the agent already sends to
/signals* and /discovery/watchlist (cloud/api/auth.py). There's no public
GET here (unlike /discovery/watchlist) because nothing outside this
process needs to read it yet — cloud/analyst/pre_trade.py and
cloud/api/strategy_routes.py just import get_synced_regime() directly.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cloud.api.auth import require_cloud_secret
from core.regime.models import Regime, RegimeResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/regime", tags=["regime"])

# In-memory mirror — replaced wholesale on every sync from the agent.
# Resets to None on every Railway redeploy, same as discovery_routes.py's
# _watchlist_store — get_synced_regime()'s staleness check handles that.
_synced_regime: Optional[RegimeResult] = None
_synced_at: Optional[datetime] = None

# How old a synced regime can be before it's treated as unavailable rather
# than trusted — double core.regime.service.CACHE_TTL's default 15 min, so
# a single missed agent sync tick doesn't immediately go stale.
MAX_REGIME_AGE_SECONDS = 1800


class RegimeSyncRequest(BaseModel):
    regime:             str            # Regime enum value, e.g. "TRENDING_BULL"
    confidence:         float
    allowed_strategies: list[str]
    size_multiplier:    float
    timestamp:          str            # ISO — the classification time, not sync time
    trend_signal:       str = ""
    vix_signal:         str = ""
    breadth_signal:     str = ""
    notes:              list[str] = []


@router.post("/sync")
async def sync_regime(payload: RegimeSyncRequest, _auth=Depends(require_cloud_secret)):
    """Called by the local agent (agent/main.py) after every regime refresh."""
    global _synced_regime, _synced_at
    _synced_regime = RegimeResult(
        regime=Regime(payload.regime),
        confidence=payload.confidence,
        allowed_strategies=payload.allowed_strategies,
        size_multiplier=payload.size_multiplier,
        timestamp=datetime.fromisoformat(payload.timestamp),
        trend_signal=payload.trend_signal,
        vix_signal=payload.vix_signal,
        breadth_signal=payload.breadth_signal,
        notes=payload.notes,
    )
    _synced_at = datetime.now(timezone.utc)
    logger.info("Regime synced: %s (confidence=%.0f)", payload.regime, payload.confidence)
    return {"synced": True}


def get_synced_regime() -> Optional[RegimeResult]:
    """
    Read by cloud/analyst/pre_trade.py and cloud/api/strategy_routes.py.
    Returns None if the agent has never synced, or its last sync is old
    enough that trusting it would be worse than admitting we don't know.
    """
    if _synced_regime is None or _synced_at is None:
        return None
    age = (datetime.now(timezone.utc) - _synced_at).total_seconds()
    if age > MAX_REGIME_AGE_SECONDS:
        logger.warning("Synced regime is stale (%.0fs old) — treating as unavailable", age)
        return None
    return _synced_regime
