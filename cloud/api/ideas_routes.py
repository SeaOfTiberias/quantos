"""
QuantOS — Trade-idea log route
───────────────────────────────
GET  /ideas            every logged trade idea with its latest score (written
                        by scripts/trade_ideas.py evaluate), newest first, plus
                        the scoreboard by action (enter_if / enter_now / avoid).
POST /ideas/structure  run the structure selector (core/ideas/structure.py) on
                        the live Fyers chain for a view: {symbol, direction
                        ("bull"|"bear"), target, stop, days, p, intraday,
                        budget (0/null = research mode)} -> best of each family
                        and the top 10. Prices only; never an order.

Ideas are added and updated through the CLI on the VM. Same protection as
every cockpit route (nginx Basic auth).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from core.ideas.log import scoreboard
from core.ideas.structure import View, best_by_family, candidates

REPO = Path(__file__).resolve().parent.parent.parent

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


class StructureRequest(BaseModel):
    symbol: str
    direction: Literal["bull", "bear"]
    target: float = Field(gt=0)
    stop: float = Field(gt=0)
    days: int = Field(ge=1, le=60)
    p: float = Field(0.5, gt=0, lt=1)
    intraday: bool = False
    budget: Optional[float] = None


def _family(name: str) -> str:
    return ("future" if "future" in name else "credit" if "credit" in name
            else "single" if name.startswith("long ") else "debit")


def _row(c) -> dict:
    d = asdict(c)
    d["expiry"] = c.expiry.isoformat() if c.expiry else None
    d["family"] = _family(c.name)
    d.pop("legs", None)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def _run(req: StructureRequest) -> dict:
    from agent.main import load_config
    from core.brokers import get_broker
    from scripts.pick_structure import fetch_chain
    broker = get_broker(load_config(str(REPO / "agent" / "config.yaml")))
    if not broker.connect():
        raise HTTPException(status_code=503, detail="Fyers is not connected -- refresh the token")
    chain = fetch_chain(broker._client, req.symbol)
    d = 1 if req.direction == "bull" else -1
    if d * (req.target - chain.spot) <= 0 or d * (chain.spot - req.stop) <= 0:
        raise HTTPException(status_code=400, detail=f"for a {req.direction} view the target must be on the "
                            f"{'upper' if d > 0 else 'lower'} side of spot {chain.spot:g} and the stop on the other")
    view = View(direction=d, target=req.target, stop=req.stop, horizon_days=req.days,
                risk_budget=req.budget or None, overnight=not req.intraday)
    ranked = candidates(chain, view, p=req.p)
    return {"symbol": chain.symbol, "spot": chain.spot, "lot": chain.lot, "p": req.p,
            "research_mode": not req.budget, "count": len(ranked),
            "best": [_row(c) for c in best_by_family(ranked)], "top": [_row(c) for c in ranked[:10]]}


@router.post("/structure")
async def pick_structure(req: StructureRequest):
    sym = req.symbol.upper().strip()
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
        raise HTTPException(status_code=400, detail="symbol must be an NSE ticker")
    req.symbol = sym
    try:
        return await run_in_threadpool(_run, req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"could not price {sym}: {e}")
