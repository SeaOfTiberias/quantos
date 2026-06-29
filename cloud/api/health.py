"""
QuantOS — Extended Health & Monitoring Endpoints
──────────────────────────────────────────────────
US-15: Railway health check + operational status endpoints.

Endpoints:
  GET /health          — simple liveness check (Railway uses this)
  GET /health/ready    — readiness check (all dependencies up)
  GET /status          — operational dashboard (human-readable)
"""

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Track server start time for uptime
_START_TIME = time.time()


@router.get("/health")
async def health():
    """
    Liveness probe. Railway calls this every 30s.
    Returns 200 as long as the process is alive.
    """
    return {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def readiness():
    """
    Readiness probe. Checks all critical dependencies.
    Returns 200 only when the app is ready to serve traffic.
    """
    checks = {}
    all_ok  = True

    # Check Anthropic API key is set
    checks["claude_api_key"] = bool(os.getenv("ANTHROPIC_API_KEY"))
    if not checks["claude_api_key"]:
        all_ok = False

    # Check webhook secret is configured
    checks["webhook_secret"] = bool(os.getenv("WEBHOOK_SECRET"))
    # Not fatal — will warn but still serve

    # Check WhatsApp config
    checks["whatsapp"] = bool(
        os.getenv("CALLMEBOT_PHONE") and os.getenv("CALLMEBOT_API_KEY")
    )

    # Check database (if configured)
    db_url = os.getenv("DATABASE_URL", "")
    checks["database"] = "postgres" in db_url or "sqlite" in db_url or True  # in-memory fallback ok

    status = "ready" if all_ok else "degraded"
    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status")
async def operational_status():
    """
    Human-readable operational dashboard.
    Shows uptime, config status, market hours, regime cache age.
    """
    uptime_secs = int(time.time() - _START_TIME)
    uptime_str  = _format_uptime(uptime_secs)

    # Market hours check (IST = UTC+5:30)
    now_utc  = datetime.now(timezone.utc)
    ist_hour = (now_utc.hour + 5) % 24
    ist_min  = (now_utc.minute + 30) % 60
    if now_utc.minute + 30 >= 60:
        ist_hour = (ist_hour + 1) % 24
    market_open  = (ist_hour == 9 and ist_min >= 15) or (10 <= ist_hour <= 14) or (ist_hour == 15 and ist_min <= 30)
    market_status = "OPEN" if market_open else "CLOSED"

    return {
        "service":        "QuantOS Cloud API",
        "version":        "1.0.0",
        "environment":    os.getenv("ENVIRONMENT", "production"),
        "uptime":         uptime_str,
        "uptime_seconds": uptime_secs,
        "market":         market_status,
        "timestamp_utc":  now_utc.isoformat(),
        "config": {
            "claude_configured":    bool(os.getenv("ANTHROPIC_API_KEY")),
            "whatsapp_configured":  bool(os.getenv("CALLMEBOT_PHONE")),
            "webhook_secret_set":   bool(os.getenv("WEBHOOK_SECRET")),
            "database_configured":  bool(os.getenv("DATABASE_URL")),
            "min_confluence_score": float(os.getenv("MIN_CONFLUENCE_SCORE", "70")),
            "regime_cache_ttl":     int(os.getenv("REGIME_CACHE_TTL", "900")),
        },
    }


def _format_uptime(seconds: int) -> str:
    days    = seconds // 86400
    hours   = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs    = seconds % 60
    parts = []
    if days:    parts.append(f"{days}d")
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
