"""A ledger call: what was called, by whom, before the outcome (E5). Pure.

A call is written once and never edited (calls.jsonl is append-only); scores live elsewhere.

Fields the caller gives (`raw`):
  symbol, side ("long" | "short"), who (WHO),
  entry: {"kind": "open"} | {"kind": "limit", "price": p} | {"kind": "stop", "price": p}
         | {"kind": "close_above" | "close_below", "price": p} | {"kind": "close_between", "low": a, "high": b}
         ("open": the next session's open; "limit"/"stop": the first intraday fill within `window`
         sessions; "close_*": the next open after the first close that meets it, within `window`),
  stop (price), target (price, optional), max_hold (sessions, default 15), size_r (default 1),
  salvage (what to do if it goes wrong; required for user/claude calls),
  decision ("taken" | "avoided"), why (required), source_ref (optional: the screener/plan key).

Code adds: id, at (IST), as_of (the last session the call could see), ref_close (that session's
adjusted close, to rescale levels if a split lands later), atr, map_read (frozen v3 read; required),
map_plan (call_plan.make_plan's version on the call evening: the mechanical baseline).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

WHO = ("user", "claude", "model", "screener", "darvas", "book")   # model: another model's call (review, Gemini)
DISCRETIONARY = ("user", "claude")
ENTRY_KINDS = ("open", "limit", "stop", "close_above", "close_below", "close_between")
MAX_HOLD = 15            # = core.market_map.call_plan.MAX_HOLD
ENTRY_WINDOW = 5         # sessions a limit/stop entry may wait for its fill


class CallError(ValueError):
    pass


def _f(x, name: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise CallError(f"{name} must be a number, got {x!r}")
    if v <= 0:
        raise CallError(f"{name} must be > 0")
    return v


def make_call(raw: dict, *, now: datetime, as_of: str, ref_close: float, atr: Optional[float],
              map_read: dict, map_plan: Optional[dict], seq: int = 1) -> dict:
    """Validate `raw` and return the record to append. Raises CallError on anything missing."""
    sym = str(raw.get("symbol") or "").strip().upper()
    if not sym:
        raise CallError("symbol is required")
    side = str(raw.get("side") or "").lower()
    if side not in ("long", "short"):
        raise CallError("side must be long or short")
    who = str(raw.get("who") or "").lower()
    if who not in WHO:
        raise CallError(f"who must be one of {', '.join(WHO)}")
    if not map_read or map_read.get("error"):
        raise CallError(f"no map read for {sym}: {(map_read or {}).get('error', 'missing')}. No map read, no call")
    decision = str(raw.get("decision") or "").lower()
    if decision not in ("taken", "avoided"):
        raise CallError("decision must be taken or avoided")
    why = str(raw.get("why") or "").strip()
    if not why:
        raise CallError("why is required")
    salvage = str(raw.get("salvage") or "").strip()
    if who in DISCRETIONARY and not salvage:
        raise CallError("salvage plan is required for a user or Claude call (docs/TRADE_REASONING.md)")

    e = raw.get("entry") or {"kind": "open"}
    kind = str(e.get("kind") or "").lower()
    if kind not in ENTRY_KINDS:
        raise CallError(f"entry.kind must be one of {', '.join(ENTRY_KINDS)}")
    entry = dict(kind=kind)
    if kind == "close_between":
        entry["low"], entry["high"] = _f(e.get("low"), "entry.low"), _f(e.get("high"), "entry.high")
        if entry["low"] >= entry["high"]:
            raise CallError("entry.low must be below entry.high")
    elif kind != "open":
        entry["price"] = _f(e.get("price"), "entry.price")
    if kind != "open":
        entry["window"] = int(e.get("window") or ENTRY_WINDOW)
    sg = 1 if side == "long" else -1
    ref = entry.get("price", (entry["low"] + entry["high"]) / 2 if kind == "close_between" else float(ref_close))

    stop = raw.get("stop")
    if stop is None:
        if who in DISCRETIONARY:
            raise CallError("stop is required for a user or Claude call")
    else:
        stop = _f(stop, "stop")
        if sg * (ref - stop) <= 0:
            raise CallError(f"stop {stop} is on the wrong side of the entry {ref} for a {side}")
    target = raw.get("target")
    if target is not None:
        target = _f(target, "target")
        if sg * (target - ref) <= 0:
            raise CallError(f"target {target} is on the wrong side of the entry {ref} for a {side}")

    return dict(
        id=f"{as_of}-{who}-{sym}-{seq}", at=now.isoformat(timespec="seconds"), as_of=as_of,
        symbol=sym, side=side, who=who, entry=entry, stop=stop, target=target,
        max_hold=int(raw.get("max_hold") or MAX_HOLD), size_r=float(raw.get("size_r") or 1.0),
        salvage=salvage, decision=decision, why=why, source_ref=raw.get("source_ref"),
        ref_close=float(ref_close), atr=atr, map_read=map_read, map_plan=map_plan,
    )


MODEL_SOURCES = ("review-llm", "review-tool", "review-agree", "gemini")


def from_idea(idea: dict) -> Optional[dict]:
    """A trade idea (core/ideas/log.py) as a raw ledger call; None for a view-less idea.
    Ideas trigger and stop on closes; the ledger keeps the close trigger and scores the stop
    intraday (its own convention, the same for every call)."""
    side = {"bull": "long", "bear": "short"}.get(idea.get("view"))
    if not side:
        return None
    src = str(idea.get("source") or "claude").lower()
    who = src if src in WHO else ("model" if src in MODEL_SOURCES else "claude")
    if idea.get("action") == "enter_if":
        t = idea.get("trigger") or {}
        entry = ({"kind": "close_between", "low": t.get("low"), "high": t.get("high")} if t.get("kind") == "close_between"
                 else {"kind": t.get("kind"), "price": t.get("level")})
        entry["window"] = 10
    else:
        entry = {"kind": "open"}
    tgt = idea.get("target")
    return dict(symbol=idea["symbol"], side=side, who=who, entry=entry,
                stop=(idea.get("stop") or {}).get("level"),
                target=tgt.get("level") if isinstance(tgt, dict) else tgt,
                salvage=idea.get("salvage") or "", decision="avoided" if idea.get("action") == "avoid" else "taken",
                why=idea.get("note") or idea.get("why") or idea["id"], source_ref=f"idea:{idea['id']}")
