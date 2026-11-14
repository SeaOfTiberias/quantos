"""
QuantOS — Map plans routes (cockpit #/plans, user 2026-11-14)
──────────────────────────────────────────────────────────────
GET /plans        every pick the plans job has planned (F&O calls and Darvas breakouts):
                  the call, where each plan track stands, the latest levels, the last close.
GET /plans/{key}  one pick's page: the plan (versions, tracks, events) and the snapshot the
                  20:00 IST job wrote (map card + the last 120 daily bars).

Read-only: every number comes from scripts/call_plans.py and core/market_map/call_plan.py
(state.json and pages/ under ~/.quantos/call_plans); no model feeds these routes, nothing is
rebuilt here, and nothing places, sizes or moves an order. Paper plans on an UNTESTED rule.
The /plans prefix must be in the VM's nginx allowlist (deploy/nginx/quantos-locations.conf).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.market_map import call_plan as cp

router = APIRouter(prefix="/plans", tags=["plans"])

ROOT = Path.home() / ".quantos" / "call_plans"
KEY = re.compile(r"\d{4}-\d{2}-\d{2}\|(CE|PE|DARVAS)\|[A-Z0-9&\-]{1,20}")
# the most advanced state of a pick's tracks, for its status chip
RANK = ["triggered", "trigger_pending", "swept", "waiting", "target", "stopped", "time",
        "skipped", "broke", "lapsed"]


def _state(root: Path) -> dict:
    f = root / "state.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        raise HTTPException(status_code=503, detail="plan state unreadable; the job may be writing it")


def _page(root: Path, key: str) -> Optional[dict]:
    f = root / "pages" / (key.replace("|", "_") + ".json")
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return None


def expires(day: str, n: int = cp.EXPIRY) -> str:
    d = date.fromisoformat(day)
    for _ in range(n):
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    return d.isoformat()


def status(tracks: list[dict]) -> str:
    states = [t.get("state", "waiting") for t in tracks] or ["no plan"]
    known = [s for s in states if s in RANK]
    return min(known, key=RANK.index) if known else states[0]


def summary(key: str, p: dict, last_close: Optional[float]) -> dict:
    """One row of the list: the call, the latest levels, each track's state and result."""
    c, v = p["call"], (p.get("versions") or [{}])[-1]
    sg = 1 if c["side"] == "CE" else -1
    tracks = []
    for t in p.get("tracks", []):
        m = cp.mark(t, last_close) if last_close is not None and t.get("state") == "triggered" else {}
        tracks.append(dict(kind=t["kind"], state=t["state"], entry=t.get("entry"), stop=t.get("stop"),
                           target=t.get("target"), exit=t.get("exit"),
                           r=t.get("r", m.get("r")), pct=t.get("pct", m.get("pct")), open=bool(m)))
    lv = lambda k: ({"level": v[k]["level"], "target": (v[k].get("target") or {}).get("level")} if v.get(k) else None)
    return dict(key=key, sym=c["sym"], side=c["side"], src=c.get("src", "F&O"), date=c["date"], called=c["spot"],
                expires=expires(c["date"]), status=status(p.get("tracks", [])),
                open=any(t["state"] in cp.OPEN_STATES for t in p.get("tracks", [])),
                sweep=lv("sweep"), breakout=lv("breakout"), error=v.get("error"), plan_as_of=v.get("as_of"),
                replans=max(0, len(p.get("versions", [])) - 1), through=p.get("through"), last_close=last_close,
                as_sent_pct=(round(sg * (last_close / c["spot"] - 1) * 100, 2) if last_close and c.get("spot") else None),
                tracks=tracks)


def _last_close(page: Optional[dict]) -> Optional[float]:
    bars = (page or {}).get("bars") or []
    return float(bars[-1][4]) if bars else None


def list_plans(root: Path = ROOT) -> dict:
    st = _state(root)
    rows = [summary(k, p, _last_close(_page(root, k))) for k, p in st.items()]
    rows.sort(key=lambda r: r["sym"])                                    # open first, newest call first
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows.sort(key=lambda r: not r["open"])
    return dict(plans=rows, n_open=sum(r["open"] for r in rows),
                rule="UNTESTED paper plans, scored against the calls as sent; not orders")


def one_plan(key: str, root: Path = ROOT) -> dict:
    if not KEY.fullmatch(key):
        raise HTTPException(status_code=400, detail="not a plan key")
    st = _state(root)
    if key not in st:
        raise HTTPException(status_code=404, detail=f"no plan {key}")
    page = _page(root, key)
    p = st[key]
    return dict(summary=summary(key, p, _last_close(page)), plan=p, page=page,
                rule="UNTESTED paper plan, not an order")


@router.get("")
def get_plans():
    return list_plans()


@router.get("/{key}")
def get_plan(key: str):
    return one_plan(key)
