"""
QuantOS Cloud API — Shared Auth Dependency
─────────────────────────────────────────────
Split out of cloud/api/main.py so other routers (e.g. discovery_routes.py)
can guard agent-facing write endpoints without a circular import back
into main.py.
"""

import os

from fastapi import Header, HTTPException, status

CLOUD_API_SECRET = os.getenv("CLOUD_API_SECRET", "")


def require_cloud_secret(x_cloud_secret: str = Header(default="")):
    """Guards agent-facing endpoints. No-op if CLOUD_API_SECRET isn't set
    (dev mode), but that's a deliberately loud default — see .env.example."""
    if CLOUD_API_SECRET and x_cloud_secret != CLOUD_API_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail="Invalid or missing X-Cloud-Secret header")
