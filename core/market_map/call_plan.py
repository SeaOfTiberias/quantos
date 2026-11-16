"""Map plans for the F&O screener's calls (user, 2026-11-14; docs/TRADE_REASONING.md lesson 9).

The screener picks the stock and the side. The map picks the entry and the exit:

  - no chase at the call's close;
  - SWEEP plan: wait for price to trade through the nearest STRUCTURAL liquidity on the
    trade's side (a D/W/M protected level, the card's liquidity pools, equal minor swing
    lows/highs, the edge of a strong or protected HTF zone), then a daily close back across
    it; enter at the next open, stop just beyond the sweep's extreme (0.1 ATR);
  - target: the nearest opposing level at least 1 ATR(D) from the CALL's price; no target,
    no entry; no entry if, at the next open, the target is less than 1R away;
  - 2026-11-15 (user: the code must follow lesson 9; replay of the 8 Darvas paper picks): the
    nearest-pool rule swept small daily FVGs, CPR lines and W weak highs (GLAND 3019 instead
    of D protected 2841.1); those no longer count on their own. A sweep can come in
    stages (GLAND poked 2841.1 by 1.5 points on 21 Oct before the 2769.8 flush) and the stop
    under the first poke is then hit; a 1 ATR stop was tried and every entry failed R:R >= 1,
    so the stop stays just under the sweep low, as lesson 9 says. Targets measured from the sweep level made the call day's own high the
    target on 6 of 8 picks. The BREAKOUT plan is gone: a breakout entry is the Darvas entry
    (breakout_level stays as a helper). Plans wait 20 sessions: HTF levels take weeks;
  - daily zones (2026-11-14, user: RELIANCE ran into the daily bear OB 1357-1371, SBIN into
    1075.7-1124.5, neither on the HTF card): their near edges are sweep levels and targets,
    their far edges targets only, and a breakout close must clear every daily zone its level
    sits in;
  - lapse: no trigger within EXPIRY sessions, or the target reached first (ran without us);
  - broke: swept and not reclaimed within RECLAIM_SESSIONS (watch the other side).
  - 2026-11-16 (user, GLAND chart; replay of the 8 Darvas picks against the lesson-9 hand reads):
    * the level is LOCKED at the first plan that has one; a later plan may move it only to a
      newer PROTECTED level nearer the price (structure trails), never to a zone edge or
      further away (GLAND's later D protected 2792.4 would have missed the 2769.8 sweep) (GLAND moved up to a newer
      W OB at 3042 and was stopped there; the hand read held D protected 2841.1; ZYDUSLIFE's
      new D protected 1105.4 is the level the hand read used);
    * a sweep must trade at least SWEEP_DEPTH_ATR through the level (GLAND poked 2841.1 by 1.5
      points on 21 Oct, the real sweep was 2769.8 on 23 Oct, entry 27 Oct open 2858.9; CYIENT's
      8-point poke of 1107.2 was stopped the same day). A 0.25 ATR reclaim margin was tried first
      the same day: it entered GLAND on the 1.5-point poke and was stopped;
    * no opposing level at least 1 ATR away (a breakout at highs): the target is
      NO_LEVEL_TARGET_R from the entry, not "no entry";
    * results (2026-11-16, review by a second model): no entry when the company's results are
      due within RESULTS_BLACKOUT sessions of the entry day, and an open trade exits at the close
      of the session before results (a results gap jumps any stop). The date comes from NSE's
      board-meetings feed (t["next_results"], set by the nightly job; replays have no history of
      it, so the rule only acts live);
    * one RE-SWEEP: after a stop, or an entry skipped at the open, the same level gets one more
      try (ZYDUSLIFE: the 22 Oct sweep failed R:R, the deeper 26 Oct sweep was the trade);
    * CONFIRM (Darvas breakouts; F&O calls too since 2026-11-16: 27 of 39 missed winners ran
      without a pullback; on the 194 calls the starter made +0.46R on calls, -0.74R on puts in a
      rising month, so it sits under the NIFTY guard): the session after the breakout must close green and
      beyond the breakout close (GLAND 8 Oct closed red and below 7 Oct; value moved down on
      the 15-min profile); then a STARTER enters at the next open, stop beyond the two
      sessions' extreme. No confirmation, no starter: the sweep plan is the entry.

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
STOP_BUFFER_ATR = 0.1    # just under the sweep low (lesson 9); 1 ATR was tried 2026-11-15: every entry failed R:R >= 1
EQL_ATR = 0.25           # two minor swing lows (highs) this close together are equal lows (highs)
SWING_LOOKBACK = 25      # sessions of daily bars searched for minor swing highs/lows
EXPIRY = 20              # sessions a plan waits for its trigger (2026-11-15: was 10)
RECLAIM_SESSIONS = 3     # sessions after a sweep to close back across the level
RECLAIM_ATR = 0.0        # the reclaim close only has to be back across the level
SWEEP_DEPTH_ATR = 0.25   # a sweep trades at least this far through the level (2026-11-16)
NO_LEVEL_TARGET_R = 2.0  # target when no opposing level is >= 1 ATR away (2026-11-16)
RESULTS_BLACKOUT = 5     # no entry with results due within this many sessions (2026-11-16)


def _sessions_until(day: str, d: str) -> int:
    """Weekdays after `day` up to and including `d` (holidays ignored)."""
    from datetime import date, timedelta
    x, end, n = date.fromisoformat(day[:10]), date.fromisoformat(d[:10]), 0
    while x < end:
        x += timedelta(days=1)
        n += x.weekday() < 5
    return n
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


_STRUCTURAL = ("protected", "multi-touch", "EQ", "equal")


def structural_levels(c: dict, bars: pd.DataFrame, side: str) -> list[tuple[float, str]]:
    """Structural liquidity on the trade's side of the price (lesson 9): D/W/M protected
    levels, the card's liquidity pools, the near edge of a strong or protected HTF zone, the
    far edge of a strong zone the price sits in, and equal minor swing lows (highs)."""
    px, atr, sg = c["price"], c.get("atr_d") or 0.0, _sg(side)
    where = "below" if sg == 1 else "above"
    out: list[tuple[float, str]] = []
    for tf in ("D", "W", "M"):
        v = ((c.get("structure") or {}).get(tf) or {}).get("protected") or {}
        if v.get("px") is not None:
            out.append((float(v["px"]), f"{tf} protected"))
    for x in (c.get("liquidity") or {}).get(where, []):
        out.append((float(x["px"]), x.get("kind") or "liquidity"))
    zs = c.get("zones") or {}
    for z in zs.get(where, []):
        why = str(z.get("why", ""))
        # the zone's own type only: "W bull FVG ...; W multi-touch x4" is an FVG with a multi-touch
        # level inside it (COFORGE 2026-11-06); the multi-touch level is its own point zone
        if z.get("strong") or any(k in why.split(";")[0] for k in _STRUCTURAL):
            out.append((float(z["hi"] if sg == 1 else z["lo"]),
                        ("STRONG " if z.get("strong") else "") + why.split(";")[0][:40]))
    for z in zs.get("inside", []):
        if z.get("strong"):
            out.append((float(z["lo"] if sg == 1 else z["hi"]),
                        "edge of STRONG " + str(z.get("why", "")).split(";")[0][:34]))
    sw = sorted(p for p, _ in swing_points(bars, side))
    for a, b in zip(sw, sw[1:]):
        if atr and b - a <= EQL_ATR * atr:
            out.append((a if sg == 1 else b, "D equal " + ("lows" if sg == 1 else "highs")))
    return [(p, k) for p, k in out if (p < px if sg == 1 else p > px)]


def sweep_level(c: dict, bars: pd.DataFrame, side: str) -> Optional[dict]:
    """The structural liquidity on the trade's side: the nearest level 0.2-4 ATR away, extended
    through every structural level within 0.5 ATR of the pool's far edge (the sweep must clear
    the pool)."""
    px, atr, sg = c["price"], c.get("atr_d"), _sg(side)
    if not atr:
        return None
    cands = structural_levels(c, bars, side)
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
    return dict(level=lvl, kinds=sorted({k for _, k in pool}), atr_away=round(sg * (px - lvl) / atr, 2),
                level_kinds=sorted({k for p, k in pool if p == lvl}))


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
    out["target"] = target(c, side)                                      # >= 1 ATR from the call's price
    sw = sweep_level(c, bars, side)
    if sw:
        out["sweep"] = dict(sw, target=out["target"])
    return out                                                           # no breakout track (2026-11-15)


# ─── walking a plan forward, one daily bar at a time ──────────────────────────


def new_track(kind: str, side: str, **kw) -> dict:
    return dict(dict(kind=kind, side=side, state="waiting", waited=0, events=[]), **kw)


def confirm_track(side: str, call_bar: dict) -> dict:
    """The starter (Darvas and F&O picks): waits one session for a close beyond the pick's close."""
    return new_track("confirm", side, ref_close=float(call_bar["c"]),
                     ref_ext=float(call_bar["l"] if _sg(side) == 1 else call_bar["h"]))


def re_sweep(t: dict) -> Optional[dict]:
    """One more try at the same level after the first sweep track was stopped, or skipped at
    the open (R:R, or opened beyond the stop). None if it does not qualify."""
    if t.get("kind") != "sweep" or t.get("level") is None:
        return None
    last = (t["events"] or [{}])[-1].get("what", "")
    tgt = None if t.get("target_2r") else t.get("target")              # a 2R target belongs to its entry
    if t["state"] == "stopped":
        # the stop-out took out the sweep low: that bar is the new sweep; wait for a reclaim
        return new_track("re-sweep", t["side"], state="swept", level=t["level"], target=tgt, kinds=t.get("kinds"),
                         atr=t.get("atr"), extreme=float(t["exit"]), since_sweep=-1)
    if t["state"] == "skipped" and ("R:R" in last or "beyond the stop" in last):
        # a fresh sweep must trade beyond the first sweep's extreme
        return new_track("re-sweep", t["side"], level=t["level"], target=tgt, kinds=t.get("kinds"),
                         atr=t.get("atr"), beyond=t.get("extreme"))
    return None


OPEN_STATES = ("waiting", "swept", "trigger_pending", "triggered")
SWEEP_KINDS = ("sweep", "re-sweep")


def step(tr: dict, version: dict, bar: dict, nxt: Optional[dict] = None) -> dict:
    """Advance one track by one daily bar (`bar`/`nxt`: date, o, h, l, c; `nxt` is the next
    bar if already known, for an entry at its open). `version` is the plan made the evening
    before `bar`. States: waiting -> swept -> trigger_pending -> triggered -> stopped | target |
    time; or lapsed / broke / skipped. Returns a new dict."""
    t = dict(tr, events=list(tr["events"]))
    if version.get("atr"):
        t["atr"] = version["atr"]
    sg, atr = _sg(t["side"]), t.get("atr") or 0.0          # an errored evening keeps the last ATR
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

    if t["kind"] == "confirm":
        tgt = (version.get("target") or {}).get("level")
        green = sg * (bar["c"] - bar["o"]) > 0 and sg * (bar["c"] - t["ref_close"]) > 0
        if not green:
            t["state"] = "unconfirmed"; ev("no follow-through the session after the breakout: no starter"); return t
        ext = float(min(t["ref_ext"], bar["l"]) if sg == 1 else max(t["ref_ext"], bar["h"]))
        t.update(target=tgt, stop=round(ext - sg * STOP_BUFFER_ATR * atr, 2), state="trigger_pending")
        ev("trigger: follow-through close after the breakout (starter)", stop=t["stop"])
        return open_trade(t, nxt) if nxt is not None else t

    if t["kind"] in SWEEP_KINDS and t["state"] == "waiting" and t.get("level") is None:   # lock the level
        plan = version.get("sweep")
        if not plan:
            t["waited"] += 1
            if t["waited"] >= EXPIRY:
                t["state"] = "lapsed"; ev("expired: no plan level")
            return t
        t.update(level=plan["level"], target=(plan.get("target") or {}).get("level"), kinds=plan.get("kinds"))
    elif t["kind"] == "sweep" and t["state"] == "waiting" and t.get("beyond") is None:
        plan = version.get("sweep") or {}                               # structure trails: a newer
        if plan.get("level") is not None and sg * (plan["level"] - t["level"]) > 0 \
                and any(k.split()[0] in ("D", "W", "M") and "protected" in k for k in plan.get("level_kinds", [])):
            t["level"] = plan["level"]                                  # protected, toward price only
    t["waited"] += 1
    if t["kind"] in SWEEP_KINDS:
        if t["state"] == "waiting":
            L, tgt = t["level"], t.get("target")
            trig = t["beyond"] if t.get("beyond") is not None else L - sg * SWEEP_DEPTH_ATR * atr
            if tgt is not None and sg * (bar["h" if sg == 1 else "l"] - tgt) >= 0 and sg * (trig - bar["l" if sg == 1 else "h"]) <= 0:
                t["state"] = "lapsed"; ev("target reached before any sweep: ran without us"); return t
            if sg * (trig - bar["l" if sg == 1 else "h"]) > 0:
                t.update(state="swept", extreme=float(bar["l" if sg == 1 else "h"]), since_sweep=0)
                ev("swept", level=L, extreme=t["extreme"])
            elif t["waited"] >= EXPIRY:
                t["state"] = "lapsed"; ev("expired: no sweep"); return t
        else:
            t["since_sweep"] += 1
            t["extreme"] = float(min(t["extreme"], bar["l"]) if sg == 1 else max(t["extreme"], bar["h"]))
        if t["state"] == "swept":
            if sg * (bar["c"] - t["level"]) > RECLAIM_ATR * atr:
                t["stop"] = round(t["extreme"] - sg * STOP_BUFFER_ATR * atr, 2)
                ev("trigger: daily close back across the level", level=t["level"], stop=t["stop"])
                t["state"] = "trigger_pending"
                return open_trade(t, nxt) if nxt is not None else t
            if t["since_sweep"] >= RECLAIM_SESSIONS:
                t["state"] = "broke"; ev("swept, no reclaim: the level broke (watch the other side)")
        return t
    # breakout (helper track; make_plan no longer writes one)
    plan = version.get("breakout") or {}
    if not plan:
        return t
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
    res = t.get("next_results")
    if res and res >= day and _sessions_until(day, res) <= RESULTS_BLACKOUT:
        t["state"] = "skipped"; t["events"].append(dict(date=day, what=f"results on {res}: no entry")); return t
    if sg * (e - t["stop"]) <= 0:
        t["state"] = "skipped"; t["events"].append(dict(date=day, what="opened beyond the stop: no entry")); return t
    if t.get("target") is None:                                         # nothing overhead: 2R
        t["target"], t["target_2r"] = round(e + sg * NO_LEVEL_TARGET_R * sg * (e - t["stop"]), 2), True
        t["events"].append(dict(date=day, what=f"no opposing level: target {NO_LEVEL_TARGET_R:g}R", target=t["target"]))
    if sg * (e - t["target"]) >= 0:
        t["state"] = "skipped"; t["events"].append(dict(date=day, what="opened at the target: no entry")); return t
    if sg * (t["target"] - e) < MIN_RR * sg * (e - t["stop"]):
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
    res = t.get("next_results")
    if res and res > day and _sessions_until(day, res) <= 1:
        return _exit(t, "results", bar["c"], day)
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


def plan_lines(sym: str, side: str, called_at: float, version: dict, expires: str, src: str = "F&O") -> list[str]:
    """The lines under one call (`src`: who picked it, F&O screener or Darvas)."""
    tag = "" if src == "F&O" else f" [{src}]"
    if version.get("error"):
        return [f"🗺 {sym} {side}{tag}: no map read ({version['error']})"]
    across = "above" if side == "CE" else "below"
    beyond = "under" if side == "CE" else "over"
    lines = [f"🗺 {sym} {side}{tag} (called {_p(called_at)}): don't chase the close."]
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
        lines.append("   no structural level within 0.2-4 ATR: no map plan, no entry")
    lines.append(f"   expires {expires} if nothing triggers. Paper plan, not an order.")
    return lines


def event_line(sym: str, side: str, kind: str, e: dict, src: str = "F&O") -> str:
    extra = ", ".join(f"{k} {_p(v) if isinstance(v, (int, float)) else v}" for k, v in e.items()
                      if k not in ("date", "what") and v is not None)
    tag = "" if src == "F&O" else f" {src}"
    return f"   {sym} {side}{tag} [{kind}] {e['date'][5:]}: {e['what']}" + (f" ({extra})" if extra else "")
