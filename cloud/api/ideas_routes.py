"""
QuantOS — Trade-idea log route
───────────────────────────────
GET /ideas   every logged trade idea with its latest score (written by
             scripts/trade_ideas.py evaluate), newest first, plus the
             scoreboard by action (enter_if / enter_now / avoid).

Read-only: ideas are added and updated through the CLI on the VM. Same
protection as every cockpit route (nginx Basic auth).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter

from core.ideas.log import scoreboard

router = APIRouter(prefix="/ideas", tags=["ideas"])


def _path() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return (Path(override) if override else Path.home() / ".quantos") / "trade_ideas.json"


@router.get("")
def list_ideas():
    try:
        ideas = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ideas = []
    ideas = sorted(ideas, key=lambda i: i.get("created_at", ""), reverse=True)
    return {"ideas": ideas, "scoreboard": scoreboard([(i, i.get("eval") or {}) for i in ideas])}
