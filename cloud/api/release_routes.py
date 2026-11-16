"""
QuantOS — order release routes (cockpit #/release, user 2026-11-16)
───────────────────────────────────────────────────────────────────
The order rule is unchanged (code drafts, code checks, the user releases); this page replaces
typing `qorder.py --yes` on the VM.

GET  /release                 mode (paper / live / off), tickets (pending first), the setup state
POST /release/{id}/release    {code, qty_scale?}: a 6-digit code from the user's authenticator
                              app, then every leg goes through core/orders/gateway.Gateway.place
                              (the checks on a fresh quote, then the journal)
POST /release/{id}/reject     drop a pending ticket
POST /release/kill            turn the kill switch ON (stops every new order). Turning it OFF
                              stays a deliberate step: scripts/enable-orders.ps1 from the PC.

Paper first: the page sends live only when BOTH `orders.live: true` and
`orders.release_page: live` are in agent/config.yaml; anything else journals paper orders.
Exits are not here: the position manager places them. The /release prefix must be in the VM's
nginx allowlist (deploy/nginx/quantos-locations.conf); the cockpit's basic auth covers it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.orders import tickets as tk
from core.orders.gateway import KILL_SWITCH, JOURNAL
from core.orders.totp import Verifier

router = APIRouter(prefix="/release", tags=["release"])

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "agent" / "config.yaml"
ACCOUNT = "icici-spouse"


def orders_cfg() -> dict:
    try:
        import yaml
        return (yaml.safe_load(CONFIG_PATH.read_text()) or {}).get("orders") or {}
    except Exception:
        return {}


def mode(cfg: Optional[dict] = None) -> str:
    cfg = orders_cfg() if cfg is None else cfg
    if KILL_SWITCH.exists():
        return "off"
    return "live" if cfg.get("live") and cfg.get("release_page") == "live" else "paper"


def make_gateway(live: bool):
    """The same gateway qorder uses; patched in tests."""
    from agent.auth import breeze_auth
    from core.orders.gateway import Gateway, limits_from
    return Gateway(breeze_auth.connect(), account=ACCOUNT, live=live, limits=limits_from(orders_cfg()))


store = tk.Store()
verifier = Verifier()


class ReleaseBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    qty_scale: Optional[float] = None


def _recent_journal(n: int = 10) -> list[dict]:
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text().splitlines()[-n:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        i = r.get("intent") or {}
        out.append(dict(ts=r.get("ts"), kind=r.get("kind"), live=r.get("live"), ok=r.get("ok"), sent=r.get("sent"),
                        code=i.get("code"), action=i.get("action"), qty=i.get("qty"), price=i.get("price"),
                        purpose=i.get("purpose"), reasons=r.get("reasons")))
    return out[::-1]


@router.get("")
def list_tickets():
    m = mode()
    ts = store.all()
    ts.sort(key=lambda t: (t["status"] != "pending", t["created"]), reverse=False)
    return dict(mode=m, kill_switch=KILL_SWITCH.exists(), codes_ready=verifier.configured(),
                tickets=ts, journal=_recent_journal())


@router.post("/{tid}/release")
def release(tid: str, body: ReleaseBody):
    m = mode()
    if m == "off":
        raise HTTPException(status_code=409, detail="the kill switch is on: no orders")
    t = store.get(tid)
    if t is None:
        raise HTTPException(status_code=404, detail="no such ticket")
    if t["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"ticket is {t['status']}")
    bad = verifier.check(body.code)
    if bad:
        raise HTTPException(status_code=403, detail=bad)
    g = make_gateway(live=(m == "live"))
    price = None
    try:
        q = g.quote(tk.intent_from(t["legs"][0]))
        if q.get("bid") and q.get("ask"):
            price = (q["bid"] + q["ask"]) / 2
    except Exception:
        price = None                      # the gateway's own checks still need a fresh quote
    try:
        return store.release(tid, g, qty_scale=body.qty_scale, price=price)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such ticket")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{tid}/reject")
def reject(tid: str):
    try:
        return store.reject(tid)
    except KeyError:
        raise HTTPException(status_code=404, detail="no such ticket")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/kill")
def kill_on():
    KILL_SWITCH.parent.mkdir(parents=True, exist_ok=True)
    KILL_SWITCH.write_text("on from the release page\n")
    return dict(kill_switch=True)
