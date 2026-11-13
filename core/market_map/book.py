"""Forward paper books: Claude's judgment layered on the playbook, tracked and scored by code
(docs/TRADE_REASONING.md, steps 4-8).

A book is a JSON document written before any outcome:

  id, made, first_session, by, why, index_read
  positions: [{id "SYM:p1|p2", sym, track, setup (the playbook plan), opp (strong opposing zones),
               group, priority}]
  rules:     {max_fills: {group: n}, guards: [{index, below|above, cancels "long"|"short", since, why}]}
  cancels:   [{id, date, why}]            judgment cancels: unfilled positions only, after that close
  baseline:  [{id, setup, opp}]           every actionable playbook setup that day, taken mechanically

`advance` walks every position with playbook.simulate, then applies the book rules on top:
  - a judgment cancel or an index guard cancels a position that had not filled by that date
    (a fill on the same day as the index breach counts as filled: the conservative reading,
    since the order of the two inside the day is unknown from daily bars);
  - a group stops filling once max_fills of its positions have filled; later fills are cancelled
    (same-day fills beyond the cap: by priority).
A filled position is never cancelled here: exits are rule-driven (playbook P3), never a model's.

`score_book` reports net R (stressed costs, unfilled = 0R; P2 at half weight) for the book and for
its baseline. The book's edge over its own baseline is the value of the judgment.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

import pandas as pd

from core.market_map import playbook as pb
from core.market_map.playbook_s8 import score

BOOK_CANCEL = "book"


def fill_date(res: dict) -> Optional[str]:
    for d, msg in res.get("log") or []:
        if str(msg).startswith("filled"):
            return d
    return None


def guard_date(guard: dict, index_daily: pd.DataFrame) -> Optional[str]:
    """First session on or after guard['since'] whose low (below) or high (above) breaches it."""
    if index_daily is None or not len(index_daily):
        return None
    df = index_daily[index_daily["date"] >= pd.Timestamp(guard["since"])]
    if "below" in guard:
        hit = df[df["l"] < float(guard["below"])]
    else:
        hit = df[df["h"] > float(guard["above"])]
    return hit["date"].iat[0].date().isoformat() if len(hit) else None


def weight(setup: dict) -> float:
    return 0.5 if setup.get("half_risk") else 1.0


def _walk(p: dict, daily_for: Callable[[str], pd.DataFrame], first: date) -> dict:
    daily = daily_for(p["sym"])
    if daily is None or not len(daily):
        return dict(outcome="no data", log=[])
    opp = [tuple(z) for z in (p.get("opp") or [])] if p["track"] == "p1" else None
    return pb.simulate(p["setup"], daily, first, opp_strong=opp)


def advance(book: dict, daily_for: Callable[[str], pd.DataFrame],
            index_for: Callable[[str], pd.DataFrame], walk=None) -> list[dict]:
    """Each position's status under the playbook plus the book's rules. `walk(position, daily_for,
    first_session)` -> a simulate result; tests inject one."""
    first = date.fromisoformat(book["first_session"])
    walk = walk or _walk
    rules = book.get("rules") or {}
    rows = []
    for p in book["positions"]:
        res = walk(p, daily_for, first)
        rows.append(dict(id=p["id"], sym=p["sym"], track=p["track"], side=p["setup"]["side"],
                         group=p.get("group") or p["id"], priority=int(p.get("priority") or 99),
                         setup=p["setup"], res=res, fill=fill_date(res), book_cancel=None))

    # 1. judgment cancels and index guards: a position unfilled by that date is cancelled
    stops = {}
    for c in book.get("cancels") or []:
        stops.setdefault(c["id"], []).append((c["date"], f"judgment: {c.get('why', '')}".strip()))
    for g in rules.get("guards") or []:
        gd = guard_date(g, index_for(g["index"]))
        if gd:
            lvl = f"below {g['below']:g}" if "below" in g else f"above {g['above']:g}"
            for r in rows:
                if r["side"] == g["cancels"]:
                    stops.setdefault(r["id"], []).append((gd, f"index guard: {g['index']} traded {lvl} on {gd}"))
    for r in rows:
        for d, why in sorted(stops.get(r["id"], [])):
            if r["fill"] is None or r["fill"] > d:
                r["book_cancel"] = dict(date=d, why=why)
                break

    # 2. group caps over the fills that survived step 1
    caps = rules.get("max_fills") or {}
    for g, cap in caps.items():
        members = [r for r in rows if r["group"] == g and not r["book_cancel"]]
        filled = sorted((r for r in members if r["fill"]), key=lambda r: (r["fill"], r["priority"]))
        if len(filled) < cap:
            continue
        full_on = filled[cap - 1]["fill"]
        keep = {r["id"] for r in filled[:cap]}
        for r in members:
            if r["id"] not in keep and (r["fill"] is None or r["fill"] >= full_on):
                r["book_cancel"] = dict(date=full_on, why=f"group {g} full ({cap} filled by {full_on})")

    for r in rows:
        if r["book_cancel"]:
            r["status"] = "cancelled"
            r["reason"] = r["book_cancel"]["why"]
            r["end"] = r["book_cancel"]["date"]
        else:
            r["status"] = r["res"].get("outcome")
            r["reason"] = r["res"].get("reason")
            r["end"] = r["res"].get("end")
    return rows


def _net(rows_or_setups: list[tuple[dict, dict]]) -> dict:
    n = len(rows_or_setups)
    tot, filled, live, closed = 0.0, 0, 0, 0
    per = []
    for setup, res in rows_or_setups:
        s = score(setup, res)
        r = weight(setup) * s["net_r"]
        tot += r
        per.append(round(r, 3))
        filled += s["filled"]
        live += res.get("outcome") in ("pending", "open")
        closed += res.get("outcome") == "closed"
    return dict(n=n, filled=filled, closed=closed, unresolved=live, net_r=round(tot, 3),
                net_r_per_position=round(tot / n, 3) if n else None)


def score_book(book: dict, rows: list[dict], daily_for: Callable[[str], pd.DataFrame], walk=None) -> dict:
    """Net R for the book (its rows after the book rules) and for its baseline (mechanical)."""
    mine = [(r["setup"], {"outcome": "cancelled"} if r["book_cancel"] else r["res"]) for r in rows]
    first = date.fromisoformat(book["first_session"])
    base = []
    for b in book.get("baseline") or []:
        p = dict(b, track=b["id"].split(":")[1], sym=b["id"].split(":")[0])
        base.append((b["setup"], (walk or _walk)(p, daily_for, first)))
    out = dict(book=_net(mine), baseline=_net(base))
    if out["book"]["n"] and out["baseline"]["n"]:
        out["judgment_edge_r_per_position"] = round(out["book"]["net_r_per_position"]
                                                    - out["baseline"]["net_r_per_position"], 3)
    out["resolved"] = out["book"]["unresolved"] == 0
    return out


def live_unfilled(rows: list[dict]) -> list[str]:
    """Ids a judgment cancel may still act on: not filled, not cancelled, not expired."""
    return [r["id"] for r in rows if r["status"] == "pending"]
