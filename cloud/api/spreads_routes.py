"""
QuantOS — Spread Watcher Route
───────────────────────────────
GET  /spreads        what the ICICI Direct spread watcher (scripts/run_spread_watcher.py)
                     sees right now, for the cockpit's #/spreads page: each open
                     spread with its live P&L, stops and alerts sent, any
                     uncovered short, the alert timeline, and whether the
                     watcher is alive (heartbeat < HEARTBEAT_STALE_S old).
POST /spreads/level  set or clear YOUR stock-price exit level for one stock
                     ({"stock_code": "TECMAH", "level": 1775} / "level": null).
                     It replaces trail A for that stock; the watcher reads it
                     every minute. An alert setting, never an order.

Reads the watcher's own files in ~/.quantos on this box. Same protection
as every cockpit route (nginx Basic auth).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/spreads", tags=["spreads"])

IST = timezone(timedelta(hours=5, minutes=30))
HEARTBEAT_STALE_S = 90
ALERTS_SHOWN = 40


def _dir() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return Path(override) if override else Path.home() / ".quantos"


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _alerts(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-ALERTS_SHOWN:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _market_open(now: datetime) -> bool:
    return now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) < (15, 31)


@router.get("")
def spreads():
    base = _dir()
    now = datetime.now(IST)
    hb = _json(base / "spread_watcher_heartbeat.json", {})
    age = None
    if hb.get("at"):
        age = (now - datetime.fromisoformat(hb["at"])).total_seconds()
    state = _json(base / "spread_watcher_state.json", {})
    rows = []
    for key, st in state.items():
        view = st.pop("view", None) or {}
        rows.append({"key": key, **st, **view})
    rows.sort(key=lambda r: (r.get("expiry") or "", r.get("stock_code") or ""))
    return {
        "watcher": {"heartbeat_at": hb.get("at"), "alive": age is not None and age < HEARTBEAT_STALE_S,
                    "session_ok": bool(hb.get("session_ok")), "market_open": _market_open(now)},
        "rules": hb.get("rules"),
        "spreads": rows,
        "uncovered": hb.get("naked", []) if age is not None and age < HEARTBEAT_STALE_S else [],
        "alerts": _alerts(base / "spread_watcher_alerts.jsonl"),
        "levels": _json(base / "spread_watcher_levels.json", {}),
    }


class LevelRequest(BaseModel):
    stock_code: str
    level: Optional[float] = None


@router.post("/level")
def set_level(body: LevelRequest):
    code = body.stock_code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9&-]{2,20}", code):
        raise HTTPException(status_code=400, detail="not an ICICI stock code")
    if body.level is not None and not 0 < body.level < 10_000_000:
        raise HTTPException(status_code=400, detail="level must be a positive price")
    path = _dir() / "spread_watcher_levels.json"
    levels = _json(path, {})
    if body.level is None:
        levels.pop(code, None)
    else:
        levels[code] = round(body.level, 2)
    path.write_text(json.dumps(levels))
    return {"levels": levels}
