"""
QuantOS — Dual logging: the reviewer's pick and the tool's top pick, side by side
──────────────────────────────────────────────────────────────────────────────────
Every structure review is written to the trade-idea log (core/ideas/log.py) so
the daily scorer marks both choices against the market:

  the model and the tool agree  -> one idea, source "review-agree"
  they differ                    -> two ideas, "review-llm" and "review-tool",
                                    linked by review.pair
  the model said "none"          -> the tool's pick as "review-tool", plus an
                                    "avoid" idea as "review-llm" (skipping is a
                                    result too)

After a few dozen reviews, scoreboard_by_source() answers the question the
reviewer exists for: does the model's judgement beat the arithmetic alone?
Pure: scripts/review_structure.py does the I/O.
"""

from __future__ import annotations

import re
from typing import Optional

_NAME = re.compile(r"^(bull call|bear put|bear call|bull put) (\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)")


def structure_of(row: dict, lot: int) -> Optional[dict]:
    """A candidate row -> the idea log's structure, or None for a single option or a future.
    Debit names are long/short ("bear put 690/660"); credit names are short/long
    ("bear call 710/730 (credit)")."""
    m = _NAME.match(row.get("structure") or "")
    if not m or not row.get("expiry"):
        return None
    kind, a, b = m.group(1).replace(" ", "_"), float(m.group(2)), float(m.group(3))
    long_k, short_k = (b, a) if kind in ("bear_call", "bull_put") else (a, b)
    return {"kind": kind, "expiry": row["expiry"], "long_strike": long_k, "short_strike": short_k, "lot": lot}


def _base(ps: dict, view: str, stop: float) -> dict:
    return {"symbol": ps["symbol"], "view": view, "spot": ps.get("spot"),
            "stop": {"kind": "close_above" if view == "bear" else "close_below", "level": stop}}


def ideas_for_review(review, ps: dict, model: str, pair: str) -> list[dict]:
    """Raw ideas (for core.ideas.log.make_idea) for one Review of a pick_structure result."""
    v = ps.get("view") or {}
    view = "bull" if str(v.get("direction", "")).lower().startswith("bu") else "bear"
    lot = int(ps.get("lot") or 0)
    meta = {"pair": pair, "verdict": review.verdict, "model": model, "thesis": v.get("thesis"),
            "target": v.get("target"), "days": v.get("days"),
            "tool_top": (review.tool_top or {}).get("id"), "llm_pick": (review.pick or {}).get("id"),
            "why": review.why, "risks": review.risks, "event": review.event,
            "accepted_flags": review.accepted_flags, "error": review.error}

    def idea(row: dict, source: str) -> dict:
        d = {**_base(ps, view, float(v.get("stop"))), "action": "enter_now", "source": source,
             "review": meta, "note": f"{row['id']}: needs_p {row.get('needs_p')}, flags {row.get('flags') or 'none'}. "
                                     f"{review.why}".strip()}
        s = structure_of(row, lot)
        if s:
            d["structure"] = s
            d["debit"] = row.get("entry")
        return d

    out = []
    top = review.tool_top
    if review.verdict == "agree" and top:
        out.append(idea(top, "review-agree"))
    elif review.verdict == "differ" and top and review.pick:
        out += [idea(review.pick, "review-llm"), idea(top, "review-tool")]
    elif review.verdict == "none":
        if top:
            out.append(idea(top, "review-tool"))
        out.append({**_base(ps, view, float(v.get("stop"))), "action": "avoid", "source": "review-llm",
                    "review": meta, "note": f"Reviewer passed: {review.why or review.risks}".strip()})
    elif top:                                   # invalid / error: the tool's pick stands, logged as such
        out.append(idea(top, "review-tool"))
    return out


def scoreboard_by_source(evals: list[tuple[dict, dict]], prefix: str = "review-") -> dict:
    """Paper results per review source: ideas, scored, wins, P&L, and P&L on risk."""
    out: dict = {}
    for idea, ev in evals:
        src = idea.get("source", "")
        if not src.startswith(prefix):
            continue
        a = out.setdefault(src, {"ideas": 0, "scored": 0, "wins": 0, "pnl": 0.0, "pnl_pct_sum": 0.0})
        a["ideas"] += 1
        if ev.get("pnl") is not None:
            a["scored"] += 1
            a["pnl"] += ev["pnl"]
            a["wins"] += ev["pnl"] > 0
            a["pnl_pct_sum"] += ev.get("pnl_pct") or 0.0
    for a in out.values():
        a["mean_pnl_pct"] = round(a["pnl_pct_sum"] / a["scored"], 1) if a["scored"] else None
        del a["pnl_pct_sum"]
    return out
