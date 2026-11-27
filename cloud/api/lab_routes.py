"""
QuantOS — Strategy Lab routes (cockpit #/lab)
──────────────────────────────────────────────
Every strategy we tested, read from the registry in git (research/lab/strategies.json) and its
normalized trade file (research/lab/trades/<id>.csv, scripts/lab_build_trades.py):

  GET /lab/strategies                 the dropdown: id, name, family, status, tested, has_trades
  GET /lab/strategies/{id}            the entry, summary stats, equity curve(s) and the trades
  GET /lab/strategies/{id}/trades.csv the trade file as a download
  GET /lab/bars?symbol=&start=&end=   daily candles for the trade chart (index_bars for NIFTY /
                                      BANKNIFTY, else the L1 stock store), raw prices

Research records only: backtest trades, no account data, no orders. Stats are arithmetic on the
file (sum, mean, win share, profit factor, drawdown of the cumulative curve) in the strategy's own
P&L unit, never a model's estimate.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lab", tags=["lab"])

LAB = Path(__file__).resolve().parents[2] / "research" / "lab"
MAX_SERIES = 3                     # more distinct chart symbols than this -> one "All trades" curve


def _home() -> Path:
    o = os.getenv("QUANTOS_HOME_DIR")
    return Path(o) if o else Path.home() / ".quantos"


def registry(root: Path = LAB) -> list[dict]:
    with (root / "strategies.json").open(encoding="utf-8") as f:
        return json.load(f)["strategies"]


def _entry(sid: str, root: Path = LAB) -> dict:
    for s in registry(root):
        if s["id"] == sid:
            return s
    raise HTTPException(404, f"unknown strategy {sid}")


def _trades_path(s: dict, root: Path = LAB) -> Optional[Path]:
    if not s.get("trades"):
        return None
    p = root / "trades" / f"{s['trades']}.csv"
    return p if p.exists() else None


def read_trades(p: Path) -> list[dict]:
    with p.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("gross", "cost", "net"):
            r[k] = float(r[k]) if r.get(k) not in (None, "") else None
    return rows


def stats(rows: list[dict]) -> dict:
    net = [r["net"] for r in rows if r["net"] is not None]
    if not net:
        return {"n": len(rows)}
    pos, neg = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    cum, peak, dd = 0.0, 0.0, 0.0
    for x in net:
        cum += x
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return {"n": len(net), "total": round(sum(net), 2), "mean": round(sum(net) / len(net), 3),
            "win_rate": round(sum(x > 0 for x in net) / len(net), 4),
            "profit_factor": round(pos / neg, 3) if neg else None, "max_drawdown": round(dd, 2)}


def equity(rows: list[dict]) -> list[dict]:
    """Cumulative net by exit time; one curve per chart symbol when there are few, else one."""
    syms = sorted({r.get("chart_symbol") or "" for r in rows})
    groups = {s: [r for r in rows if (r.get("chart_symbol") or "") == s] for s in syms} \
        if 1 < len(syms) <= MAX_SERIES else {"All trades": rows}
    out = []
    for name, rs in groups.items():
        cum, pts = 0.0, []
        for r in sorted(rs, key=lambda r: r["exit_time"]):
            if r["net"] is None:
                continue
            cum += r["net"]
            pts.append({"t": r["exit_time"][:10], "v": round(cum, 2)})
        out.append({"name": name or "All trades", "points": pts})
    return out


@router.get("/strategies")
def list_strategies():
    out = []
    for s in registry():
        out.append({k: s.get(k) for k in ("id", "name", "family", "status", "tested")} |
                   {"has_trades": _trades_path(s) is not None})
    return {"strategies": out}


@router.get("/strategies/{sid}")
def strategy(sid: str):
    s = _entry(sid)
    p = _trades_path(s)
    if p is None:
        return {**s, "stats": None, "equity": [], "trade_rows": []}
    rows = read_trades(p)
    return {**s, "stats": stats(rows), "equity": equity(rows), "trade_rows": rows}


@router.get("/strategies/{sid}/trades.csv")
def trades_csv(sid: str):
    p = _trades_path(_entry(sid))
    if p is None:
        raise HTTPException(404, "no trade file for this strategy yet")
    return FileResponse(p, media_type="text/csv", filename=f"{sid}_trades.csv")


def daily_bars(symbol: str, start: date, end: date, home: Optional[Path] = None) -> list[dict]:
    home = home or _home()
    sym = symbol.strip().upper()
    idx = home / "index_bars" / f"{sym}.csv"
    p = idx if idx.exists() else home / "l1_store" / "bars" / f"{sym}.csv"
    if not p.exists():
        raise HTTPException(404, f"no daily bars for {sym}")
    out = []
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                d = date.fromisoformat(r["date"][:10])
            except ValueError:
                continue
            if start <= d <= end and r.get("series", "EQ") in ("EQ", "BE", ""):
                out.append({"time": d.isoformat(), "open": float(r["o"]), "high": float(r["h"]),
                            "low": float(r["l"]), "close": float(r["c"])})
    dedup = {b["time"]: b for b in out}
    return [dedup[k] for k in sorted(dedup)]


@router.get("/bars")
def bars(symbol: str, start: str, end: str):
    try:
        a, b = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
    except ValueError:
        raise HTTPException(400, "start/end must be YYYY-MM-DD")
    if (b - a).days > 3700:
        raise HTTPException(400, "range too long (max ~10 years)")
    return {"symbol": symbol.upper(), "bars": daily_bars(symbol, a, b)}
