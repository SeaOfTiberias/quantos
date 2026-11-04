"""
QuantOS — Market Map routes (docs/MARKET_MAP_SCREENS.md, sprint S2b)
─────────────────────────────────────────────────────────────────────
GET  /map/{symbol}        map_read(symbol) plus the whole zone ladder and the
                           layers shown / still missing: the cockpit's #/map page.
POST /map/{symbol}/check  map_read(symbol, trade) for {side, entry, stop, target}:
                           R, the first strong zone in the way, stop placement, flags.

Read-only and advisory: every number comes from core/market_map/read.py, no
model feeds these routes, and nothing here places, sizes or moves an order.
The map is the saved file when it is younger than 7 days, else built from
Fyers bars on demand. Same protection as every cockpit route (nginx Basic auth);
the /map prefix must be in the VM's nginx allowlist (deploy doesn't sync it).
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from core.market_map import read as mr

router = APIRouter(prefix="/map", tags=["map"])


def _symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    if not re.fullmatch(r"[A-Z0-9&\-]{1,20}", sym):
        raise HTTPException(status_code=400, detail="symbol must be an NSE ticker")
    return sym


def _live(sym: str) -> tuple:
    """(Fyers market, last traded price), or (None, None) when Fyers is down: the page then reads at the map's close."""
    try:
        m = mr.live_market()
        q = m.quotes([f"NSE:{sym}-EQ"])
        lp = next(iter(q.values()), {}).get("lp")
        return m, (float(lp) if lp else None)
    except Exception:
        return None, None


def _read(sym: str, trade: Optional[dict] = None) -> dict:
    m, lp = (None, None) if trade else _live(sym)          # a trade check reads at its entry
    rd = mr.map_read(sym, trade, market=m, market_factory=mr.live_market, price=lp, zones=True)
    if "error" in rd:
        raise HTTPException(status_code=502, detail=f"no map for {sym}: {rd['error']}")
    rd["price_source"] = "entry" if trade else "live" if lp else "map close"
    return rd


@router.get("/{symbol}")
async def get_map(symbol: str):
    return await run_in_threadpool(_read, _symbol(symbol))


class CheckRequest(BaseModel):
    side: Literal["long", "short"]
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    target: Optional[float] = Field(None, gt=0)


@router.post("/{symbol}/check")
async def check_trade(symbol: str, req: CheckRequest):
    sym = _symbol(symbol)
    d = 1 if req.side == "long" else -1
    if d * (req.entry - req.stop) <= 0:
        raise HTTPException(status_code=400, detail=f"a {req.side}'s stop must be {'below' if d > 0 else 'above'} the entry")
    if req.target is not None and d * (req.target - req.entry) <= 0:
        raise HTTPException(status_code=400, detail=f"a {req.side}'s target must be {'above' if d > 0 else 'below'} the entry")
    return await run_in_threadpool(_read, sym, req.model_dump())
