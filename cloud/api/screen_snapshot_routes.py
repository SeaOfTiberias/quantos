"""
QuantOS — techno-funda screen snapshot route (cockpit #/screen)
────────────────────────────────────────────────────────────────
GET /discovery/screen  the newest saved snapshot of the user's screener.in screen
                       (scripts/run_screen_snapshot.py), each stock with its TradingView
                       link, first-seen date and days on the list; plus names that dropped off.

Read-only, record only: no tested edge, no paper trades, no orders. Under the existing
/discovery prefix so the VM's nginx allowlist needs no change.
"""

from __future__ import annotations

from fastapi import APIRouter

from core.techno_funda import screen_snapshot as ss

router = APIRouter(prefix="/discovery/screen", tags=["discovery"])


@router.get("")
def get_screen():
    view = ss.latest_view(ss.load_all())
    if view is None:
        return {"session": None, "rows": [], "dropped": [], "sessions_recorded": 0, "url": ss.SCREEN_URL}
    return view
