"""
QuantOS — Call ledger route (docs/EXECUTION_PLAN_2026-11-19.md, E5)
───────────────────────────────────────────────────────────────────
GET /ledger   every call (newest first) with its latest score, and the running comparison:
              discretionary calls (user, Claude) against the call as sent and the map plan, in R.

Calls are added by scripts/ledger.py on the VM (CLI, a Claude Code session, trade_ideas.py, the
call-plans job) and scored each evening by `scripts/ledger.py score`. Read-only here. The frozen
map read stays in calls.jsonl; this route sends the map plan's levels only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/ledger", tags=["ledger"])


def _root() -> Path:
    override = os.getenv("QUANTOS_HOME_DIR")
    return (Path(override) if override else Path.home() / ".quantos") / "ledger"


def _plan(mp: dict | None) -> dict | None:
    sw = (mp or {}).get("sweep")
    if not sw:
        return None
    return dict(level=sw.get("level"), kinds=sw.get("kinds"), target=(sw.get("target") or {}).get("level"))


@router.get("")
async def ledger():
    root = _root()
    calls = []
    p = root / "calls.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                calls.append(json.loads(line))
            except ValueError:
                continue
    sp = root / "scores.json"
    sc = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    scores = sc.get("scores", {})
    rows = []
    for c in reversed(calls):
        s = scores.get(c["id"], {})
        rows.append(dict(
            {k: c.get(k) for k in ("id", "at", "as_of", "symbol", "side", "who", "entry", "stop", "target",
                                   "max_hold", "size_r", "salvage", "decision", "why", "source_ref")},
            map_plan=_plan(c.get("map_plan")), score=s))
    return {"scored_at": sc.get("as_of"), "summary": sc.get("summary"), "calls": rows}
