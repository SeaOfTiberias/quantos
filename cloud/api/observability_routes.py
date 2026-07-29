"""
QuantOS — Observability Routes (S5-6 / P2-8)
──────────────────────────────────────────────
One read endpoint the cockpit polls to show live system health with real
data instead of mock panels:

  • signal_counts   — today's signals grouped by status (from the S4-1
                      SignalDB: Postgres in prod, in-memory fallback)
  • webhook_latency — /webhook/tradingview round-trip p50/p95/last (S5-6 middleware)
  • claude_latency  — Claude pre-trade call p50/p95/last
  • claude_spend    — today's estimated Claude cost + token counts
  • heartbeat       — freshest agent contact (regime/watchlist sync
                      timestamps) + a stale flag. Doubles as the S4-2
                      dead-man display: when the agent stops syncing, the
                      heartbeat visibly goes stale.

GET is unauthenticated, matching every other read-only cockpit router
(discovery/risk/screener/…): the cockpit is a browser client and this view
exposes only aggregate counts and latency, never a secret or per-trade data.

Heartbeat granularity is bounded by how often the agent pushes — regime
syncs every REGIME_CACHE_TTL (~15 min), so cloud-side detection of a dead
agent is on that order, not seconds. A sharper dead-man would need a
dedicated agent ping (deliberately out of scope here — see the backlog).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from cloud.api import metrics
from cloud.api.db import get_db
from cloud.api.discovery_routes import get_last_synced_at as discovery_synced_at
from cloud.api.market_snapshot_routes import get_last_synced_at as market_snapshot_synced_at
from cloud.api.regime_routes import get_last_synced_at as regime_synced_at

logger = logging.getLogger(__name__)
router = APIRouter(tags=["observability"])

# How stale the heartbeat may get before the cockpit flags it. 2026-07-29:
# raised from 1800s (30 min) to 36h. The 30-min window was calibrated for
# the old quantos-agent's continuous ~15-min regime-sync loop, which has
# been mothballed since Darvas was disabled -- regime_synced_at/
# discovery_synced_at below are effectively permanently None now. Current
# "contact" is scripts/run_momentum_shortlist.py's market-snapshot sync,
# which runs once a day (quantos-momentum-shortlist.timer) -- a 30-min
# window would flag "STALE" for all but a few minutes of every day even
# when everything is working exactly as designed. 36h survives one missed
# day (stale token, VM hiccup) without a false alarm, but catches two.
HEARTBEAT_STALE_SECONDS = float(os.getenv("HEARTBEAT_STALE_SECONDS", str(36 * 3600)))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _heartbeat() -> dict:
    """Freshest contact timestamp across the sync sources, plus its age and
    a stale flag — the dead-man display. regime_at/watchlist_at are legacy
    quantos-agent sources, permanently None since it was mothballed;
    snapshot_at (scripts/run_momentum_shortlist.py, current daily
    automation) is what actually drives this now."""
    regime_at = regime_synced_at()
    watchlist_at = discovery_synced_at()
    snapshot_at = market_snapshot_synced_at()
    candidates = [t for t in (regime_at, watchlist_at, snapshot_at) if t is not None]
    last_contact = max(candidates) if candidates else None

    age_seconds = None
    stale = True
    if last_contact is not None:
        # Sync timestamps are tz-aware UTC (set with datetime.now(timezone.utc)).
        if last_contact.tzinfo is None:
            last_contact = last_contact.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - last_contact).total_seconds()
        stale = age_seconds > HEARTBEAT_STALE_SECONDS

    return {
        "last_contact":       _iso(last_contact),
        "age_seconds":        round(age_seconds, 1) if age_seconds is not None else None,
        "stale":              stale,
        "stale_after_seconds": HEARTBEAT_STALE_SECONDS,
        "regime_synced_at":   _iso(regime_at),
        "watchlist_synced_at": _iso(watchlist_at),
    }


@router.get("/observability")
async def observability():
    """Live operational snapshot for the cockpit System Health panel."""
    db = await get_db()
    try:
        signal_counts = await db.counts_by_status_today()
    except Exception as e:
        logger.error("Observability: signal counts failed: %s", e)
        signal_counts = {}

    snap = metrics.snapshot()
    return {
        "signal_counts_today": signal_counts,
        "signals_today_total": sum(signal_counts.values()),
        "webhook_latency":     snap["webhook_latency"],
        "claude_latency":      snap["claude_latency"],
        "claude_spend_today":  snap["claude_spend_today"],
        "heartbeat":           _heartbeat(),
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }
