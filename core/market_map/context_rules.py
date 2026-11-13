"""Frozen context rules R1-R4 (docs/STEP2_CONTEXT_TEST_PREREG_2026-11-13.md, arm A1), read from
context cards (core/market_map/card.py). Pure functions; nothing here is fitted to an outcome.

For a long (CE) signal "opposing" is above the price and "same side" below; a short (PE) mirrors.
"""
from __future__ import annotations

from typing import Optional

ROOM_ATR = 1.5          # R1: the nearest strong opposing zone at least this far (ATR(D))
SWEEP_SESSIONS = 10     # R2/R3: an opposing D or W sweep within this many sessions blocks
NEAR_SAME_ATR = 1.0     # R4: within this distance of a strong same-side zone


def _long(side: str) -> bool:
    s = side.upper()
    if s in ("CE", "LONG", "CALL"):
        return True
    if s in ("PE", "SHORT", "PUT"):
        return False
    raise ValueError(f"unknown side {side!r}")


def r1_room(card: dict, side: str) -> bool:
    opp = card["zones"]["above" if _long(side) else "below"]
    strong = [z for z in opp if z["strong"]]
    if not strong:
        return True
    edge = strong[0].get("edge_atr")
    return edge is None or abs(edge) >= ROOM_ATR


def _opposing_sweep(card: dict, side: str) -> bool:
    bad = "high" if _long(side) else "low"
    return any(e["kind"] == "sweep" and e["tf"] in ("D", "W") and e["side"] == bad
               and e.get("ago") is not None and e["ago"] <= SWEEP_SESSIONS for e in card.get("events") or [])


def r2_no_sweep(card: dict, side: str) -> bool:
    return not _opposing_sweep(card, side)


def r3_index(index_card: Optional[dict], side: str) -> bool:
    """No index card (missing read): the rule cannot block."""
    if not index_card or "error" in index_card:
        return True
    return not _opposing_sweep(index_card, side)


def r4_structure_or_location(card: dict, side: str) -> bool:
    lg = _long(side)
    w = (card["structure"].get("W") or {}).get("state")
    if w == ("up" if lg else "down"):
        return True
    if any(z["strong"] for z in card["zones"]["inside"]):
        return True
    same = [z for z in card["zones"]["below" if lg else "above"] if z["strong"]]
    return bool(same) and same[0].get("edge_atr") is not None and abs(same[0]["edge_atr"]) <= NEAR_SAME_ATR


def evaluate(card: dict, index_card: Optional[dict], side: str) -> dict:
    """{R1..R4: bool, keep: all four}; None when the card has no read."""
    if not card or "error" in card:
        return None
    out = dict(R1=r1_room(card, side), R2=r2_no_sweep(card, side), R3=r3_index(index_card, side),
               R4=r4_structure_or_location(card, side))
    out["keep"] = all(out.values())
    return out
