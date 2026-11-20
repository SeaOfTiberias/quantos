"""Score a ledger call in R from daily bars, with two mechanical baselines (E5). Pure.

`bars`: the daily bars AFTER the call's as_of session, oldest first, as dicts (date, o, h, l, c),
from the adjusted L1 store. `scale`: today's adjusted close of the as_of session / the call's
ref_close, so a split or bonus after the call rescales its levels onto the bars (1.0 normally).

Conventions (as core/market_map/call_plan.py's walk):
- stop and target on one bar: the stop. A bar that gaps beyond the stop or target fills at its open.
- a limit/stop entry fills on the first bar within `window` sessions that trades through its price
  (at the price, or at the open if it opened beyond it); on the fill bar only the stop is checked.
- an "open" entry fills at the next session's open; it is skipped if that open is beyond the stop.
- time exit at the close of the max_hold-th session in the trade; still in it: marked at the last close.

Three scores per call:
- **call:** the call's own entry, stop and target. R = side * (exit - entry) / (side * (entry - stop)).
- **as_sent:** enter at the next open, exit at the close max_hold sessions later; R on the call's
  own risk (|entry ref - stop|), or 1 ATR when the call has no stop. The "do nothing clever" baseline.
- **map_plan:** the frozen call-evening map plan (call_plan.make_plan), walked by call_plan.step
  with that one version (the live job re-plans each evening; the ledger doesn't).

Headline R for comparisons: a trade that never happened (unfilled, skipped, lapsed, no plan,
avoided) counts 0R. An avoided call's would-have-been R is reported apart (what avoiding saved).
"""
from __future__ import annotations

from typing import Optional

from core.market_map import call_plan as cp

DONE = ("stopped", "target", "time")
CP_SIDE = {"long": "CE", "short": "PE"}      # call_plan's side convention (CE = long, PE = short)


def _sg(side: str) -> int:
    return 1 if side == "long" else -1


def _exit(sg: int, entry: float, risk: float, px: float, why: str, day: str, held: int) -> dict:
    return dict(state=why, entry=round(entry, 4), exit=round(px, 4), exit_date=day, held=held,
                r=round(sg * (px - entry) / risk, 3) if risk else None, pct=round(sg * (px / entry - 1) * 100, 3))


def _walk(sg: int, entry: float, stop: Optional[float], target: Optional[float], risk: float,
          bars: list[dict], i0: int, max_hold: int, entry_bar_full: bool) -> dict:
    """Manage a filled trade from bar i0 (the fill bar)."""
    held = 0
    for i in range(i0, len(bars)):
        b = bars[i]
        held += 1
        lo, hi = (b["l"], b["h"]) if sg == 1 else (-b["h"], -b["l"])
        o = sg * b["o"]
        if stop is not None and lo <= sg * stop:
            px = sg * min(o, sg * stop) if (i > i0 or entry_bar_full) else stop
            return _exit(sg, entry, risk, px, "stopped", b["date"], held)
        if target is not None and (i > i0 or entry_bar_full) and hi >= sg * target:
            return _exit(sg, entry, risk, sg * max(o, sg * target), "target", b["date"], held)
        if held >= max_hold:
            return _exit(sg, entry, risk, b["c"], "time", b["date"], held)
    last = bars[-1]
    out = _exit(sg, entry, risk, last["c"], "open", last["date"], held)
    out["exit_date"] = None
    return out


def score_call(call: dict, bars: list[dict], scale: float = 1.0) -> dict:
    sg = _sg(call["side"])
    stop = call["stop"] * scale if call.get("stop") is not None else None
    target = call["target"] * scale if call.get("target") is not None else None
    e = call["entry"]
    if not bars:
        return dict(state="pending")
    if e["kind"] == "open":
        b = bars[0]
        entry = float(b["o"])
        if stop is not None and sg * (entry - stop) <= 0:
            return dict(state="skipped", note="opened beyond the stop", date=b["date"])
        risk = sg * (entry - stop) if stop is not None else (call.get("atr") or 0) * scale
        out = _walk(sg, entry, stop, target, risk, bars, 0, call["max_hold"], True)
        return dict(out, entry_date=b["date"])
    window = e.get("window", 5)
    if e["kind"].startswith("close_"):
        for i, b in enumerate(bars[:window]):
            c = b["c"]
            met = (c > e["price"] * scale if e["kind"] == "close_above" else
                   c < e["price"] * scale if e["kind"] == "close_below" else
                   e["low"] * scale <= c <= e["high"] * scale)
            if not met:
                continue
            if i + 1 >= len(bars):
                return dict(state="pending", note=f"triggered on the close of {b['date']}")
            nb = bars[i + 1]
            fill = float(nb["o"])
            if stop is not None and sg * (fill - stop) <= 0:
                return dict(state="skipped", note="opened beyond the stop", date=nb["date"])
            risk = sg * (fill - stop) if stop is not None else (call.get("atr") or 0) * scale
            return dict(_walk(sg, fill, stop, target, risk, bars, i + 1, call["max_hold"], True), entry_date=nb["date"])
        return dict(state="unfilled") if len(bars) >= window else dict(state="pending")
    p = e["price"] * scale
    for i, b in enumerate(bars[:window]):
        lo, hi = (b["l"], b["h"]) if sg == 1 else (-b["h"], -b["l"])
        o = sg * b["o"]
        hit = (lo <= sg * p) if e["kind"] == "limit" else (hi >= sg * p)
        if not hit:
            continue
        fill = sg * (min(o, sg * p) if e["kind"] == "limit" else max(o, sg * p))
        if stop is not None and sg * (fill - stop) <= 0:
            return dict(state="skipped", note="filled beyond the stop", date=b["date"])
        risk = sg * (fill - stop) if stop is not None else (call.get("atr") or 0) * scale
        out = _walk(sg, fill, stop, target, risk, bars, i, call["max_hold"], False)
        return dict(out, entry_date=b["date"])
    if len(bars) >= window:
        return dict(state="unfilled")
    return dict(state="pending")


def score_as_sent(call: dict, bars: list[dict], scale: float = 1.0) -> dict:
    if not bars:
        return dict(state="pending")
    sg = _sg(call["side"])
    ref = (call["entry"].get("price") or call["ref_close"]) * scale
    risk = abs(ref - call["stop"] * scale) if call.get("stop") is not None else (call.get("atr") or 0) * scale
    entry = float(bars[0]["o"])
    n = call["max_hold"]
    if len(bars) >= n:
        out = _exit(sg, entry, risk, bars[n - 1]["c"], "time", bars[n - 1]["date"], n)
    else:
        out = _exit(sg, entry, risk, bars[-1]["c"], "open", bars[-1]["date"], len(bars))
        out["exit_date"] = None
    return dict(out, entry_date=bars[0]["date"])


def _scaled_version(v: dict, scale: float) -> dict:
    v = dict(v)
    if v.get("atr"):
        v["atr"] = v["atr"] * scale
    if v.get("target"):
        v["target"] = dict(v["target"], level=v["target"]["level"] * scale)
    if v.get("sweep"):
        sw = dict(v["sweep"], level=v["sweep"]["level"] * scale)
        if sw.get("target"):
            sw["target"] = dict(sw["target"], level=sw["target"]["level"] * scale)
        v["sweep"] = sw
    return v


def score_map_plan(call: dict, bars: list[dict], scale: float = 1.0) -> dict:
    v = call.get("map_plan") or {}
    if not v.get("sweep"):
        return dict(state="no plan", note=v.get("error") or "no sweep level on the call evening")
    v = _scaled_version(v, scale)
    t = cp.new_track("sweep", CP_SIDE[call["side"]])
    for b in bars:
        t = cp.step(t, v, b)
        if t["state"] not in cp.OPEN_STATES:
            break
    if not bars:
        return dict(state="pending")
    out = dict(state=t["state"], events=t["events"][-3:])
    if t.get("entry") is not None:
        out.update(entry=t["entry"], entry_date=t.get("entry_date"))
    if t["state"] in DONE:
        out.update(exit=t["exit"], exit_date=t["exit_date"], r=t.get("r"), pct=t.get("pct"))
    elif t["state"] == "triggered":
        out.update(cp.mark(t, bars[-1]["c"]))
    return out


def headline_r(s: dict) -> float:
    """R for comparisons: a finished or open trade's R; anything that didn't trade is 0."""
    r = s.get("r")
    return float(r) if r is not None and s.get("state") in (*DONE, "open", "triggered") else 0.0


def is_final(s: dict) -> bool:
    return s.get("state") in (*DONE, "skipped", "unfilled", "no plan", "lapsed", "broke", "unconfirmed")


def score(call: dict, bars: list[dict], scale: float = 1.0) -> dict:
    c, a, m = score_call(call, bars, scale), score_as_sent(call, bars, scale), score_map_plan(call, bars, scale)
    final = is_final(c) and a.get("state") == "time" and is_final(m)
    return dict(id=call["id"], call=c, as_sent=a, map_plan=m, final=final,
                r_call=0.0 if call["decision"] == "avoided" else headline_r(c),
                r_if_taken=headline_r(c), r_as_sent=headline_r(a), r_map_plan=headline_r(m))


def summary(calls: list[dict], scores: dict[str, dict]) -> dict:
    """Running comparison by group: discretionary (user, claude, each) and mechanical."""
    def grp(cs):
        ss = [scores[c["id"]] for c in cs if c["id"] in scores]
        if not ss:
            return dict(n=0)
        mean = lambda k: round(sum(s[k] for s in ss) / len(ss), 3)        # noqa: E731
        av = [s for c, s in zip(cs, ss) if c["decision"] == "avoided"]
        return dict(n=len(ss), final=sum(s["final"] for s in ss), mean_r=mean("r_call"),
                    as_sent=mean("r_as_sent"), map_plan=mean("r_map_plan"),
                    avoided=len(av), avoided_if_taken=round(sum(s["r_if_taken"] for s in av) / len(av), 3) if av else None)
    disc = [c for c in calls if c["who"] in ("user", "claude")]
    return dict(discretionary=grp(disc), user=grp([c for c in disc if c["who"] == "user"]),
                claude=grp([c for c in disc if c["who"] == "claude"]),
                mechanical=grp([c for c in calls if c["who"] not in ("user", "claude")]))
