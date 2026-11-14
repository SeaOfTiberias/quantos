"""Map plans for the F&O screener's calls (user, 2026-11-14; docs/TRADE_REASONING.md lesson 9).

The screener picks the stock and the side. The map picks the entry and the exit:

  - no chase at the call's close;
  - SWEEP plan: wait for price to trade through the nearest liquidity on the trade's side
    (equal or minor swing lows, a CPR edge, the D/W protected level, a zone edge), then a
    daily close back across it; enter at the next open, stop beyond the sweep's extreme;
  - BREAKOUT plan (only when the call sits right under an opposing level): a daily close
    beyond that level; enter at the next open, stop beyond the last 3 sessions' extreme;
  - target: the nearest opposing level at least 1 ATR(D) away; no entry if, at the next open,
    the target is less than 1R away (added 2026-11-14 after the replay: ZYDUSLIFE 8 pts vs 32 risk);
  - daily zones (2026-11-14, user: RELIANCE ran into the daily bear OB 1357-1371, SBIN into
    1075.7-1124.5, neither on the HTF card): their near edges are sweep levels and targets,
    their far edges targets only, and a breakout close must clear every daily zone its level
    sits in;
  - lapse: no trigger within EXPIRY sessions, or the target reached first (ran without us);
  - broke: swept and not reclaimed within RECLAIM_SESSIONS (watch the other side).

While a plan waits, it is re-planned every evening from the new card, so liquidity that forms
after the call counts (KOTAKBANK, 2026-10-23). Each evening's version only applies to the bars
after it: no lookahead.

Every level, stop and target is computed here, by code, with unit tests (CLAUDE.md). The rule
is a reading aid, not a tested edge: plans are recorded before the outcome and scored against
the calls as sent after 4-6 weeks. Paper only; nothing here places an order.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

MIN_ATR = 0.2            # a level closer than this is "at the price", not liquidity to sweep
MAX_ATR = 4.0            # beyond this the plan would wait for a different trade
CLUSTER_ATR = 0.5        # levels this close together are one pool; the sweep must clear all of them
BREAKOUT_ATR = 0.6       # a call this close under an opposing level gets a breakout plan too
TARGET_MIN_ATR = 1.0     # a target nearer than this is not worth the trade
STOP_BUFFER_ATR = 0.1
SWING_LOOKBACK = 25      # sessions of daily bars searched for minor swing highs/lows
EXPIRY = 10              # sessions a plan waits for its trigger
RECLAIM_SESSIONS = 3     # sessions after a sweep to close back across the level
MAX_HOLD = 15            # sessions in the trade before a time exit at the close
MIN_RR = 1.0             # at the entry open, the target must be at least this many R away


def _sg(side: str) -> int:
    return 1 if side == "CE" else -1


def swing_points(bars: pd.DataFrame, side: str, lookback: int = SWING_LOOKBACK) -> list[tuple[float, str]]:
    """Minor swing lows (CE) or highs (PE) in the last `lookback` sessions: a bar whose low is
    below the two bars on each side (mirror for highs). Only confirmed points (two bars after)."""
    b = bars.tail(lookback).reset_index(drop=True)
    col = "l" if side == "CE" else "h"
    out = []
    for i in range(2, len(b) - 2):
        x = b[col].iat[i]
        nb = [b[col].iat[j] for j in (i - 2, i - 1, i + 1, i + 2)]
        if (side == "CE" and x < min(nb)) or (side == "PE" and x > max(nb)):
            out.append((float(x), f"D swing {'low' if side == 'CE' else 'high'} {pd.Timestamp(b['date'].iat[i]):%d %b}"))
    return out


def _card_levels(c: dict, where: str) -> list[tuple[float, str]]:
    """Card levels on one side of the price ('below' or 'above')."""
    px = c["price"]
    out: list[tuple[float, str]] = []
    for tf in ("D", "W"):
        for k in ("protected", "weak"):
            v = ((c.get("structure") or {}).get(tf) or {}).get(k) or {}
            if v.get("px") is not None:
                out.append((float(v["px"]), f"{tf} {k}"))
    for x in (c.get("liquidity") or {}).get(where, []):
        out.append((float(x["px"]), x.get("kind") or "liquidity"))
    zs = c.get("zones") or {}
    for z in zs.get(where, []):
        edge = z["hi"] if where == "below" else z["lo"]
        out.append((float(edge), ("STRONG " if z.get("strong") else "") + str(z.get("why", "")).split(";")[0][:40]))
    for z in zs.get("inside", []):                      # the far edges of a zone the price sits in
        out.append((float(z["lo"] if where == "below" else z["hi"]), "edge of " + str(z.get("why", "")).split(";")[0][:34]))
    for tf in ("W", "M"):
        cp = (c.get("pivots") or {}).get(tf) or {}
        for k in ("BC", "P", "TC"):
            if cp.get(k) is not None:
                out.append((float(cp[k]), f"{tf} CPR {k}"))
    out += _d_zone_levels(c, where)
    return [(p, k) for p, k in out if (p < px if where == "below" else p > px)]


def _d_zone_levels(c: dict, where: str) -> list[tuple[float, str]]:
    """Daily zone edges (2026-11-14): a zone wholly on this side gives its near edge (the zone's
    name) and its far edge ('far edge of ...', a target, never a sweep level); a zone the price
    sits in gives the edge on this side."""
    zd = c.get("zones_d") or {}
    out: list[tuple[float, str]] = []
    for z in zd.get(where) or []:
        near, far = (z["lo"], z["hi"]) if where == "above" else (z["hi"], z["lo"])
        out += [(float(near), z["name"]), (float(far), "far edge of " + z["name"])]
    for z in zd.get("inside") or []:
        out.append((float(z["hi"] if where == "above" else z["lo"]),
                    ("top of " if where == "above" else "bottom of ") + z["name"]))
    return out


def sweep_level(c: dict, bars: pd.DataFrame, side: str) -> Optional[dict]:
    """The pool of liquidity on the trade's side: the nearest level 0.2-4 ATR away, extended
    through every level within 0.5 ATR of the pool's far edge (the sweep must clear the pool)."""
    px, atr, sg = c["price"], c.get("atr_d"), _sg(side)
    if not atr:
        return None
    where = "below" if sg == 1 else "above"
    cands = [(p, k) for p, k in _card_levels(c, where) if not k.startswith("far edge")] \
        + [(p, k) for p, k in swing_points(bars, side) if (p < px) == (sg == 1)]
    cands = sorted({(round(p, 2), k) for p, k in cands if MIN_ATR <= sg * (px - p) / atr <= MAX_ATR},
                   key=lambda x: sg * (px - x[0]))
    if not cands:
        return None
    pool = [cands[0]]
    for p, k in cands[1:]:
        if sg * (pool[-1][0] - p) / atr <= CLUSTER_ATR:
            pool.append((p, k))
        else:
            break
    lvl = pool[-1][0]
    return dict(level=lvl, kinds=sorted({k for _, k in pool}), atr_away=round(sg * (px - lvl) / atr, 2))


def target(c: dict, side: str, entry_ref: Optional[float] = None) -> Optional[dict]:
    """The nearest opposing level at least 1 ATR beyond the reference price."""
    px, atr, sg = c["price"], c.get("atr_d"), _sg(side)
    ref = entry_ref if entry_ref is not None else px
    if not atr:
        return None
    cands = [(p, k) for p, k in _card_levels(c, "above" if sg == 1 else "below")
             if sg * (p - ref) / atr >= TARGET_MIN_ATR]
    if not cands:
        return None
    p, k = min(cands, key=lambda x: sg * (x[0] - ref))
    return dict(level=round(p, 2), kind=k)


def breakout_level(c: dict, bars: pd.DataFrame, side: str) -> Optional[dict]:
    """An opposing level within 0.6 ATR of the price (the call sits right under it): its
    highest point across a pool of nearby levels, including the last 5 sessions' extreme."""
    px, atr, sg = c["price"], c.get("atr_d"), _sg(side)
    if not atr:
        return None
    where = "above" if sg == 1 else "below"
    recent = bars.tail(5)
    ext = float(recent["h"].max() if sg == 1 else recent["l"].min())
    cands = _card_levels(c, where) + [(ext, "5-session " + ("high" if sg == 1 else "low"))]
    near = sorted({(round(p, 2), k) for p, k in cands if 0 < sg * (p - px) / atr <= BREAKOUT_ATR},
                  key=lambda x: sg * (x[0] - px))
    structural = [k for _, k in near if "protected" in k or "weak" in k or "EQ" in k or "edge" in k
                  or "OB" in k or "FVG" in k or "supply" in k or "demand" in k]
    if not structural:
        return None
    lvl, kinds = near[-1][0], sorted({k for _, k in near})
    # the close must clear every daily zone the level sits in (2026-11-14: a close above 1350.7
    # put RELIANCE inside the daily bear OB 1357-1371.1; SBIN's 1090.7 is inside 1075.7-1124.5)
    zd = c.get("zones_d") or {}
    zs = (zd.get("inside") or []) + (zd.get(where) or [])
    moved = True
    while moved:
        moved = False
        for z in zs:
            lo, hi = (z["lo"], z["hi"]) if sg == 1 else (-z["hi"], -z["lo"])
            if lo <= sg * lvl < hi:
                lvl, moved = (hi if sg == 1 else -hi), True
                kinds.insert(0, ("top of " if sg == 1 else "bottom of ") + z["name"])
    if sg * (lvl - px) / atr > MAX_ATR:
        return None
    return dict(level=round(lvl, 2), kinds=kinds)


def make_plan(c: dict, bars: pd.DataFrame, side: str) -> dict:
    """One evening's plan version for a call (pure: card + bars through the card's last session)."""
    out: dict[str, Any] = dict(as_of=c.get("last_date"), price=c.get("price"), atr=c.get("atr_d"))
    if not c or c.get("error") or not c.get("atr_d"):
        out["error"] = (c or {}).get("error") or "no ATR"
        return out
    sw = sweep_level(c, bars, side)
    if sw:
        out["sweep"] = dict(sw, target=target(c, side, sw["level"]))
    bo = breakout_level(c, bars, side)
    if bo:
        last3 = bars.tail(3)
        ref = float(last3["l"].min() if side == "CE" else last3["h"].max())
        out["breakout"] = dict(bo, target=target(c, side, bo["level"]), stop_ref=ref)
    return out


# ─── walking a plan forward, one daily bar at a time ──────────────────────────


def new_track(kind: str, side: str) -> dict:
    return dict(kind=kind, side=side, state="waiting", waited=0, events=[])


OPEN_STATES = ("waiting", "swept", "trigger_pending", "triggered")


def step(tr: dict, version: dict, bar: dict, nxt: Optional[dict] = None) -> dict:
    """Advance one track by one daily bar (`bar`/`nxt`: date, o, h, l, c; `nxt` is the next
    bar if already known, for an entry at its open). `version` is the plan made the evening
    before `bar`. States: waiting -> swept -> trigger_pending -> triggered -> stopped | target |
    time; or lapsed / broke / skipped. Returns a new dict."""
    t = dict(tr, events=list(tr["events"]))
    sg, atr = _sg(t["side"]), version.get("atr") or 0.0
    day = str(bar["date"])[:10]

    def ev(what: str, **kw):
        t["events"].append(dict(date=day, what=what, **kw))

    if t["state"] == "trigger_pending":
        t = open_trade(t, bar)
        if t["state"] != "triggered":
            return t
        return _manage(t, bar, day)
    if t["state"] == "triggered":
        return _manage(t, bar, day)
    if t["state"] not in ("waiting", "swept"):
        return t

    plan = version.get(t["kind"]) if t["state"] == "waiting" else None
    if t["state"] == "waiting" and not plan:
        t["waited"] += 1
        if t["waited"] >= EXPIRY:
            t["state"] = "lapsed"; ev("expired: no plan level")
        return t
    t["waited"] += 1
    if t["kind"] == "sweep":
        if t["state"] == "waiting":
            L, tgt = plan["level"], (plan.get("target") or {}).get("level")
            if tgt is not None and sg * (bar["h" if sg == 1 else "l"] - tgt) >= 0 and sg * (L - bar["l" if sg == 1 else "h"]) <= 0:
                t["state"] = "lapsed"; ev("target reached before any sweep: ran without us"); return t
            if sg * (L - bar["l" if sg == 1 else "h"]) > 0:
                t.update(state="swept", level=L, target=tgt, extreme=float(bar["l" if sg == 1 else "h"]), since_sweep=0)
                ev("swept", level=L, extreme=t["extreme"])
            elif t["waited"] >= EXPIRY:
                t["state"] = "lapsed"; ev("expired: no sweep"); return t
        else:
            t["since_sweep"] += 1
            t["extreme"] = float(min(t["extreme"], bar["l"]) if sg == 1 else max(t["extreme"], bar["h"]))
        if t["state"] == "swept":
            if sg * (bar["c"] - t["level"]) > 0:
                t["stop"] = round(t["extreme"] - sg * STOP_BUFFER_ATR * atr, 2)
                ev("trigger: daily close back across the level", level=t["level"], stop=t["stop"])
                t["state"] = "trigger_pending"
                return open_trade(t, nxt) if nxt is not None else t
            if t["since_sweep"] >= RECLAIM_SESSIONS:
                t["state"] = "broke"; ev("swept, no reclaim: the level broke (watch the other side)")
        return t
    # breakout
    L, tgt = plan["level"], (plan.get("target") or {}).get("level")
    if sg * (bar["c"] - L) > 0:
        ref = plan.get("stop_ref")
        ext = float(bar["l"] if sg == 1 else bar["h"])
        ext = ext if ref is None else (min(ext, ref) if sg == 1 else max(ext, ref))
        t.update(level=L, target=tgt, stop=round(ext - sg * STOP_BUFFER_ATR * atr, 2), state="trigger_pending")
        ev("trigger: breakout close", level=L, stop=t["stop"])
        return open_trade(t, nxt) if nxt is not None else t
    if t["waited"] >= EXPIRY:
        t["state"] = "lapsed"; ev("expired: no breakout close")
    return t


def open_trade(t: dict, nxt: dict) -> dict:
    """Enter at `nxt`'s open, unless it opens beyond the stop or at the target."""
    t = dict(t, events=list(t["events"]))
    sg = _sg(t["side"])
    e = float(nxt["o"])
    day = str(nxt["date"])[:10]
    if sg * (e - t["stop"]) <= 0:
        t["state"] = "skipped"; t["events"].append(dict(date=day, what="opened beyond the stop: no entry")); return t
    if t.get("target") is not None and sg * (e - t["target"]) >= 0:
        t["state"] = "skipped"; t["events"].append(dict(date=day, what="opened at the target: no entry")); return t
    if t.get("target") is not None and sg * (t["target"] - e) < MIN_RR * sg * (e - t["stop"]):
        t["state"] = "skipped"
        t["events"].append(dict(date=day, what=f"R:R under {MIN_RR:g} at the open: no entry", entry=e,
                                stop=t["stop"], target=t["target"]))
        return t
    t.update(state="triggered", entry=e, entry_date=day, held=0, risk=round(sg * (e - t["stop"]), 4))
    t["events"].append(dict(date=day, what="entered at the open", entry=e, stop=t["stop"], target=t.get("target")))
    return t


def _manage(t: dict, bar: dict, day: str) -> dict:
    sg = _sg(t["side"])
    t["held"] = t.get("held", 0) + 1
    stop, tgt = t["stop"], t.get("target")
    if sg * (stop - bar["l" if sg == 1 else "h"]) >= 0:     # stop and target on one bar: assume the stop
        return _exit(t, "stopped", min(bar["o"], stop) if sg == 1 else max(bar["o"], stop), day)
    if tgt is not None and sg * (bar["h" if sg == 1 else "l"] - tgt) >= 0:
        return _exit(t, "target", max(bar["o"], tgt) if sg == 1 else min(bar["o"], tgt), day)
    if t["held"] >= MAX_HOLD:
        return _exit(t, "time", bar["c"], day)
    return t


def _exit(t: dict, why: str, px: float, day: str) -> dict:
    sg = _sg(t["side"])
    px = float(px)
    return dict(t, state=why, exit=px, exit_date=day,
                r=round(sg * (px - t["entry"]) / t["risk"], 2) if t.get("risk") else None,
                pct=round(sg * (px / t["entry"] - 1) * 100, 2),
                events=t["events"] + [dict(date=day, what=f"exit: {why}", price=px)])


def mark(t: dict, last_close: float) -> dict:
    """Open-trade mark at the last close (R and %), for reports."""
    if t.get("state") != "triggered":
        return {}
    sg = _sg(t["side"])
    return dict(r=round(sg * (last_close - t["entry"]) / t["risk"], 2), pct=round(sg * (last_close / t["entry"] - 1) * 100, 2))


# ─── Telegram text ────────────────────────────────────────────────────────────


def _p(x: Optional[float]) -> str:
    return "?" if x is None else (f"{x:,.2f}".rstrip("0").rstrip(".") if x < 1000 else f"{x:,.1f}".rstrip("0").rstrip("."))


def plan_lines(sym: str, side: str, called_at: float, version: dict, expires: str) -> list[str]:
    """The lines under one call."""
    if version.get("error"):
        return [f"🗺 {sym} {side}: no map read ({version['error']})"]
    across = "above" if side == "CE" else "below"
    beyond = "under" if side == "CE" else "over"
    lines = [f"🗺 {sym} {side} (called {_p(called_at)}): don't chase the close."]
    sw, bo = version.get("sweep"), version.get("breakout")
    if sw:
        t = sw.get("target") or {}
        lines.append(f"   sweep: {_p(sw['level'])} ({', '.join(sw['kinds'][:3])}; {sw['atr_away']} ATR) -> enter after "
                     f"a daily close back {across} it, stop {beyond} the sweep extreme"
                     + (f"; target {_p(t.get('level'))} ({t.get('kind')})" if t else "; no target within reach"))
    if bo:
        t = bo.get("target") or {}
        lines.append(f"   breakout: daily close {across} {_p(bo['level'])} ({', '.join(bo['kinds'][:2])})"
                     + (f"; target {_p(t.get('level'))}" if t else ""))
    if not sw and not bo:
        lines.append("   no level within 0.2-4 ATR: no map plan, the call stands alone")
    lines.append(f"   expires {expires} if nothing triggers. Paper plan, not an order.")
    return lines


def event_line(sym: str, side: str, kind: str, e: dict) -> str:
    extra = ", ".join(f"{k} {_p(v) if isinstance(v, (int, float)) else v}" for k, v in e.items()
                      if k not in ("date", "what") and v is not None)
    return f"   {sym} {side} [{kind}] {e['date'][5:]}: {e['what']}" + (f" ({extra})" if extra else "")
