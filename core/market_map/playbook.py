"""
Market playbook v1 (docs/MARKET_PLAYBOOK_V1.md, committed c00010e before this code): a v3 map
read turned into orders, and the rules that manage them, cancel them, and get out when the
read is wrong.

  plan(l1, daily, as_of)              P1 continuation and P2 reversal setups for one read
  simulate(setup, daily, as_of)       the setup walked forward on daily bars under P1-P3

UNTESTED and paper only. Real orders still go through core/orders/gateway.py and the user's
release. Every price and R here is computed by this module (unit-tested), never by a model.

Choices the playbook leaves open, fixed here before any read was run through it:
  P1.2  "Nearest strong zone below the price whose strong band is bullish": among the
        bands of the read's strong zones that are at a break, fresh and bullish (demand,
        bull OB), the one the price is inside (entry at the next open), else the one with
        the highest top below the price. FVGs are never at a break (v3 H5), so never entry
        bands. Shorts mirror.
  P1.3  Discount is tested on the entry price, against the W dealing range at the read.
  P1.6  The W weak level at the read; it must lie beyond the entry in the trade's direction.
  P2.1  W down at the read, and the sweep bar's low at or below the W weak low at the read.
  P2.2  HTF liquidity below: the W and M weak low (when that TF is down), unbroken W and M
        swing lows, and W and M EQLs that were active or were retired within the 31 days
        before the read. The sweep bar's ATR(D) sets the 0.1 ATR depth.
  P2.3  The shift is the read's last D event: a CHoCH up within 10 sessions of the read,
        with the sweep at most 10 sessions before it.
  P2.4  The D order block of that CHoCH (zones.order_blocks on D bars); none -> no setup.
  Ticks  Prices round to NSE's 0.05 tick, always away from the trade's favour for stops and
        entries' fills (long entry and stop down, short entry and stop up) and toward the
        entry for targets.
  Fills  A limit fills at the open when the open is through it, else at the limit. A stop
        gapped through fills at the open. Stop and target on one bar: the stop. On the fill
        bar only the stop is checked.
  Exits  Thesis exits (E1-E3) and cancels (C1, C2) are judged at a daily close and executed
        at the next open; the time exit is at the close of session 40 after the fill.
  C2     With the entry at the band's near edge, price crosses the entry before it can close
        beyond the far edge, so such a bar fills and then stops out; C2 stays in the code for
        completeness and can fire only on data that skips the entry (none on daily bars).
  States After each close, M/W/D are re-read from the completed bars (structure.run), so
        nothing after that close is used.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from core.market_map import structure as st
from core.market_map import zones as zn

TICK = 0.05
BUF_ATR_D = 0.25            # stop buffer
MIN_RR = 2.0
RISK_CAP_ATR_W = 1.5
VALID = 10                  # sessions a resting order lives
TIME_EXIT = 40              # sessions after the fill
SWEEP_ATR_D = 0.1
SHIFT_WINDOW = 10
EQL_RECENT_DAYS = 31
BULL, BEAR = ("demand", "bull_ob"), ("supply", "bear_ob")
STATUS = "untested (playbook v1, paper only)"


def _down(x: float) -> float:
    return round(math.floor(round(x / TICK, 6)) * TICK, 2)


def _up(x: float) -> float:
    return round(math.ceil(round(x / TICK, 6)) * TICK, 2)


def _no(setup: str, reason: str, wait_for: Optional[str] = None, **kw) -> dict:
    return dict(setup=setup, status="WAIT" if wait_for else "NO TRADE", reason=reason, wait_for=wait_for, **kw)


# ─── P1 continuation ─────────────────────────────────────────────────────────

def plan_p1(l1: dict) -> dict:
    tf, px = l1["tf"], l1.get("price")
    w, m = tf["W"], tf["M"]
    atr_d, atr_w = (tf.get("D") or {}).get("atr"), (l1.get("htf") or {}).get("atr_w")
    if px is None or not atr_d or not atr_w:
        return _no("P1", "no price or ATR")
    if w["state"] not in ("up", "down"):
        return _no("P1", "W has no trend", "a W break of structure")
    long = w["state"] == "up"
    side = "long" if long else "short"
    if m["state"] == ("down" if long else "up"):
        mp = m["protected"]["price"]
        return _no("P1", f"timeframes disagree: W {w['state']}, M {m['state']}",
                   f"a monthly close {'above' if long else 'below'} the M protected "
                   f"{'high' if long else 'low'} {mp:g} (M CHoCH {'up' if long else 'down'})", side=side)
    kinds = BULL if long else BEAR
    bands = [b for z in l1["htf"]["zones"] if z["strong"] for b in z.get("bands", [])
             if b["at_break"] and b["fresh"] and b["kind"] in kinds]
    inside = [b for b in bands if b["lo"] <= px <= b["hi"]]
    if inside:
        band = min(inside, key=lambda b: b["hi"] - b["lo"])
        entry, at_open = px, True
    else:
        cand = [b for b in bands if (b["hi"] < px if long else b["lo"] > px)]
        if not cand:
            return _no("P1", f"no fresh strong {'bullish' if long else 'bearish'} zone "
                             f"{'below' if long else 'above'} the price", side=side)
        band = max(cand, key=lambda b: b["hi"]) if long else min(cand, key=lambda b: b["lo"])
        entry, at_open = (_down(band["hi"]) if long else _up(band["lo"])), False
    prot, weak = w["protected"]["price"], w["weak"]["price"]
    eq = (prot + weak) / 2
    zone_txt = f"{band['tf']} {band['kind']} {band['lo']:g}-{band['hi']:g} ({band['period']})"
    if (entry >= eq) if long else (entry <= eq):
        return _no("P1", f"entry {entry:g} is not in W {'discount' if long else 'premium'} (equilibrium {eq:g})",
                   side=side, band=zone_txt)
    stop = _down(band["lo"] - BUF_ATR_D * atr_d) if long else _up(band["hi"] + BUF_ATR_D * atr_d)
    target = _down(weak) if long else _up(weak)
    risk = (entry - stop) if long else (stop - entry)
    reward = (target - entry) if long else (entry - target)
    base = dict(side=side, band=zone_txt, entry=entry, stop=stop, target=target, risk=round(risk, 2))
    if reward <= 0:
        return _no("P1", f"the W weak level {weak:g} is not beyond the entry", **base)
    rr = round(reward / risk, 2)
    base["rr"] = rr
    if risk > RISK_CAP_ATR_W * atr_w:
        return _no("P1", f"zone too wide: risk {risk:.2f} > {RISK_CAP_ATR_W} ATR(W) = {RISK_CAP_ATR_W * atr_w:.2f}", **base)
    if rr < MIN_RR:
        return _no("P1", f"only {rr:g}R to the W weak level (needs {MIN_RR:g}R)", **base)
    return dict(setup="P1", status="SETUP", reason="continuation with M and W", entry_at_open=at_open,
                far=band["lo"] if long else band["hi"], valid=VALID, half_risk=False,
                cancel=["C1 W or M flips against", "C2 daily close beyond the band's far edge",
                        "C3 target trades first", f"C4 {VALID} sessions without a fill"],
                **base)


# ─── P2 reversal: sweep then shift ───────────────────────────────────────────

def _pstart(p: str) -> Optional[date]:
    p = str(p or "")
    if "-W" in p:
        y, w = p.split("-W")
        return date.fromisocalendar(int(y), int(w), 1)
    if len(p) == 7:
        return date(int(p[:4]), int(p[5:7]), 1)
    return None


def liquidity(l1: dict, long: bool, as_of: date) -> list[tuple[float, str]]:
    """P2.2's HTF liquidity on the side that would be swept (below for a long)."""
    side, kind, eq = ("down", "L", "EQL") if long else ("up", "H", "EQH")
    out = []
    for tf in ("W", "M"):
        s = l1["tf"].get(tf) or {}
        if s.get("state") == side and s.get("weak"):
            out.append((s["weak"]["price"], f"{tf} weak {'low' if long else 'high'}"))
        for w in (l1.get("swings") or {}).get(tf, []):
            if w["kind"] == kind:
                out.append((w["price"], f"{tf} swing {w['label'] or kind} {w['period']}"))
    for z in l1.get("zones", []):
        if z["kind"] != eq:
            continue
        at = _pstart(z.get("at")) if z.get("at") else None
        if z["status"] == "active" or (at and at >= as_of - timedelta(days=EQL_RECENT_DAYS)):
            out.append((z["level"], f"{z['tf']} {eq} {z['level']:g}"))
    return out


def plan_p2(l1: dict, daily: pd.DataFrame, as_of: date) -> dict:
    tf, px = l1["tf"], l1.get("price")
    w = tf["W"]
    atr_d, atr_w = (tf.get("D") or {}).get("atr"), (l1.get("htf") or {}).get("atr_w")
    if w["state"] not in ("up", "down") or px is None or not atr_d or not atr_w:
        return _no("P2", "W has no trend")
    long = w["state"] == "down"
    side = "long" if long else "short"
    d = st.completed(st.latest_segment(daily), "D", as_of)
    if len(d) < 30:
        return _no("P2", "too few daily bars", side=side)
    r = st.run(d, st.TF_K["D"])
    if not r.events:
        return _no("P2", "no D event", side=side)
    ev = r.events[-1]
    n = len(d)
    if ev["type"] != "CHoCH" or ev["direction"] != ("up" if long else "down") or n - 1 - ev["i"] >= SHIFT_WINDOW:
        return _no("P2", f"no recent D CHoCH {'up' if long else 'down'} (shift)", side=side)
    a = st.atr(d)
    h, l, c = (d[x].to_numpy(float) for x in ("h", "l", "c"))
    weak = w["weak"]["price"]
    levels = liquidity(l1, long, as_of)
    sweep = None
    for t in range(ev["i"] - 1, max(ev["i"] - SHIFT_WINDOW, 0) - 1, -1):
        if np.isnan(a[t]):
            continue
        for lv, lab in levels:
            if long and l[t] <= weak and l[t] < lv - SWEEP_ATR_D * a[t] and c[t] > lv:
                sweep = sweep or (t, lv, lab, l[t])
            if not long and h[t] >= weak and h[t] > lv + SWEEP_ATR_D * a[t] and c[t] < lv:
                sweep = sweep or (t, lv, lab, h[t])
        if sweep:
            break
    if not sweep:
        return _no("P2", "no sweep of HTF liquidity before the shift", side=side)
    t, lv, lab, ext = sweep
    lv, ext = float(lv), float(ext)
    obs = zn.order_blocks(d, [ev])
    if not obs:
        return _no("P2", "the shift's D order block is already broken", side=side)
    ob = obs[0]
    entry = _down(ob["hi"]) if long else _up(ob["lo"])
    stop = _down(ext - BUF_ATR_D * atr_d) if long else _up(ext + BUF_ATR_D * atr_d)
    tgt = w["protected"]["price"]
    opp = [b for z in l1["htf"]["zones"] if z["strong"] for b in z.get("bands", [])
           if b["at_break"] and b["fresh"] and b["kind"] in (BEAR if long else BULL)]
    beyond = [(b["lo"] if long else b["hi"]) for b in opp if ((b["lo"] > entry) if long else (b["hi"] < entry))]
    if beyond:
        tgt = min(tgt, min(beyond)) if long else max(tgt, max(beyond))
    target = _down(tgt) if long else _up(tgt)
    risk = (entry - stop) if long else (stop - entry)
    reward = (target - entry) if long else (entry - target)
    swept = f"{lab} {lv:g} swept to {ext:g} on {d['date'].iat[t].date().isoformat()}"
    base = dict(side=side, band=f"D {ob['kind']} {ob['lo']:g}-{ob['hi']:g} ({ob['bar']})", entry=entry, stop=stop,
                target=target, risk=round(risk, 2), swept=swept, swept_level=lv,
                shift=f"D CHoCH {ev['direction']} at {ev['level']:g} on {d['date'].iat[ev['i']].date().isoformat()}")
    if risk <= 0 or reward <= 0:
        return _no("P2", "entry, stop and target out of order", **base)
    base["rr"] = rr = round(reward / risk, 2)
    if risk > RISK_CAP_ATR_W * atr_w:
        return _no("P2", f"sweep low too far: risk {risk:.2f} > {RISK_CAP_ATR_W} ATR(W) = {RISK_CAP_ATR_W * atr_w:.2f}",
                   **base)
    if rr < MIN_RR:
        return _no("P2", f"only {rr:g}R to the target (needs {MIN_RR:g}R)", **base)
    return dict(setup="P2", status="SETUP", reason="sweep then shift (reversal; not for use until its S8 test passes)",
                entry_at_open=False, far=ext, valid=VALID, half_risk=True,
                cancel=["C2 daily close beyond the sweep extreme", "C3 target trades first",
                        f"C4 {VALID} sessions without a fill"], **base)


def plan(l1: dict, daily: pd.DataFrame, as_of: date) -> dict:
    """P4: both setups for one read."""
    return dict(status=STATUS, as_of=as_of.isoformat(), price=l1.get("price"),
                p1=plan_p1(l1), p2=plan_p2(l1, daily, as_of))


# ─── P3 forward walk ─────────────────────────────────────────────────────────

class _States:
    """M/W/D summaries after a day's close, from completed bars only."""

    def __init__(self, seg: pd.DataFrame):
        self.seg, self.cache = seg, {}

    def at(self, nxt: date) -> dict:
        """After the close of the session before `nxt` (the next session's date, so a week or
        month that closed with that session counts as completed)."""
        out = {}
        for tf in ("M", "W", "D"):
            bars = st.completed(self.seg, tf, nxt)
            key = (tf, len(bars))
            if key not in self.cache:
                self.cache[key] = st.summary(bars, st.run(bars, st.TF_K[tf]), tf) if len(bars) else dict(state="none")
            out[tf] = self.cache[key]
        return out


def simulate(setup: dict, daily: pd.DataFrame, as_of: date, opp_strong: Optional[list] = None,
             states=None) -> dict:
    """Walk a SETUP forward from `as_of` (its first session) under P1-P3. `opp_strong`: the
    read's strong zones opposing the trade (low, high) for E2. `states`: anything with
    .at(next_session_date) -> {M, W, D summaries}; tests inject one. Returns the outcome with
    an event log; R is on the planned risk."""
    if setup.get("status") != "SETUP":
        return dict(outcome="no setup")
    seg = st.latest_segment(daily)
    fwd = seg[seg["date"] >= pd.Timestamp(as_of)].reset_index(drop=True)
    states = states or _States(seg)
    long = setup["side"] == "long"
    sgn = 1 if long else -1
    entry, stop, target, risk = setup["entry"], setup["stop"], setup["target"], setup["risk"]
    p1 = setup["setup"] == "P1"
    against = "down" if long else "up"
    log, fill, fill_k, exit_px, reason = [], None, None, None, None
    be, pending_exit, armed = False, None, None
    mfe = mae = 0.0
    for k in range(len(fwd)):
        o, h, l, c = (float(fwd[x].iat[k]) for x in ("o", "h", "l", "c"))
        day = fwd["date"].iat[k].date()
        nxt = fwd["date"].iat[k + 1].date() if k + 1 < len(fwd) else day + timedelta(days=1)
        if fill is None:                                             # resting order
            if k >= setup["valid"]:
                return dict(outcome="expired", reason="C4 no fill", log=log)
            if setup.get("entry_at_open") and k == 0:
                fill = o
            elif (o <= entry) if long else (o >= entry):
                fill = o
            elif (l <= entry) if long else (h >= entry):
                fill = entry
            if fill is not None:
                fill_k = k
                log.append((day.isoformat(), f"filled {fill:g}"))
                if (l <= stop) if long else (h >= stop):
                    exit_px, reason = ((min(o, stop) if long else max(o, stop)), "stop on the fill bar")
                    break
            else:
                if (c < setup["far"]) if long else (c > setup["far"]):
                    return dict(outcome="cancelled", reason=f"C2 close {c:g} beyond {setup['far']:g} on {day}", log=log)
                if (h >= target) if long else (l <= target):
                    return dict(outcome="cancelled", reason=f"C3 target traded on {day} before a fill", log=log)
                if p1:
                    s = states.at(nxt)
                    if s["W"]["state"] == against or s["M"]["state"] == against:
                        return dict(outcome="cancelled", reason=f"C1 {'W' if s['W']['state'] == against else 'M'} "
                                                                f"turned {against} at the close of {day}", log=log)
                continue
        else:                                                        # open trade
            if pending_exit:
                exit_px, reason = o, pending_exit
                break
            if (o <= stop) if long else (o >= stop):
                exit_px, reason = o, "stop (gap)"
                break
            if (l <= stop) if long else (h >= stop):
                exit_px, reason = stop, "break-even stop" if be and stop == entry else ("trailing stop" if be else "stop")
                break
            if (o >= target) if long else (o <= target):
                exit_px, reason = o, "target (gap)"
                break
            if (h >= target) if long else (l <= target):
                exit_px, reason = target, "target"
                break
        mfe = max(mfe, sgn * ((h if long else l) - entry) / risk)
        mae = min(mae, sgn * ((l if long else h) - entry) / risk)
        if k - fill_k >= TIME_EXIT:
            exit_px, reason = c, f"time ({TIME_EXIT} sessions)"
            break
        s = states.at(nxt)
        if not be and sgn * (c - entry) >= risk:
            be, stop = True, entry
            log.append((day.isoformat(), f"close {c:g} at +1R: stop to break-even {entry:g}"))
        if be and s["D"]["state"] == setup["side"].replace("long", "up").replace("short", "down") and s["D"].get("protected"):
            dp = s["D"]["protected"]["price"]
            buf = BUF_ATR_D * (s["D"].get("atr") or 0)
            new = _down(dp - buf) if long else _up(dp + buf)
            if (new > stop) if long else (new < stop):
                log.append((day.isoformat(), f"trail stop {stop:g} -> {new:g} (D protected {dp:g})"))
                stop = new
        if p1 and (s["W"]["state"] == against or s["M"]["state"] == against):
            pending_exit = f"E1 {'W' if s['W']['state'] == against else 'M'} turned {against} at the close of {day}"
        if p1 and opp_strong and armed is None and any(lo <= c <= hi for lo, hi in opp_strong):
            armed = day
            log.append((day.isoformat(), f"close {c:g} inside an opposing strong zone: E2 armed"))
        if p1 and armed and s["D"]["state"] == against:
            ev = s["D"].get("last_event") or {}
            if ev.get("type") == "CHoCH" and ev.get("date") and date.fromisoformat(ev["date"]) >= armed:
                pending_exit = pending_exit or f"E2 D CHoCH {against} after stalling in an opposing strong zone ({day})"
        if not p1 and ((c < setup["swept_level"]) if long else (c > setup["swept_level"])):
            pending_exit = pending_exit or f"E3 close {c:g} back beyond the swept level {setup['swept_level']:g} ({day})"
    if fill is None:
        return dict(outcome="pending", reason="no fill yet (data ends)", log=log)
    if exit_px is None:
        last = float(fwd["c"].iat[-1])
        return dict(outcome="open", fill=fill, stop=stop, mark=last, r=round(sgn * (last - fill) / risk, 2),
                    mfe=round(mfe, 2), mae=round(mae, 2), log=log)
    log.append((fwd["date"].iat[min(k, len(fwd) - 1)].date().isoformat(), f"exit {exit_px:g}: {reason}"))
    return dict(outcome="closed", fill=fill, exit=exit_px, reason=reason, r=round(sgn * (exit_px - fill) / risk, 2),
                sessions=k - fill_k, mfe=round(mfe, 2), mae=round(mae, 2), log=log)


def opposing_strong(l1: dict, long: bool) -> list[tuple[float, float]]:
    """The read's strong zones whose strong band opposes a trade (for E2)."""
    kinds = BEAR if long else BULL
    return [(z["low"], z["high"]) for z in l1["htf"]["zones"] if z["strong"]
            and any(b["at_break"] and b["fresh"] and b["kind"] in kinds for b in z.get("bands", []))]


def lines(p: dict) -> list[str]:
    """P4 text for a read's plan."""
    out = [f"PLAY {p['as_of']} at {p['price']:g} ({p['status']})"]
    for key in ("p1", "p2"):
        s = p[key]
        if s["status"] == "SETUP":
            out.append(f"     {s['setup']} SETUP {s['side']}: {'next open' if s['entry_at_open'] else 'limit'} "
                       f"{s['entry']:g}, stop {s['stop']:g}, target {s['target']:g}, risk {s['risk']:g}, {s['rr']:g}R"
                       f"{', half risk' if s['half_risk'] else ''}; band {s['band']}"
                       + (f"; {s['swept']}; {s['shift']}" if s.get("swept") else "")
                       + f"; cancel: {', '.join(s['cancel'])}")
        else:
            out.append(f"     {s['setup']} {s['status']}: {s['reason']}" + (f" -- wait for {s['wait_for']}" if s.get("wait_for") else ""))
    return out
