"""Context card: a model-sized summary of one L1 read (docs/TRADE_REASONING.md, steps 1-6).

A full L1 read is ~130 KB per stock: every zone since 2010, every virgin level, every
profile. A model reasoning about a trade needs only what is near the price, with distances
already worked out. The card is that summary, built by deterministic code (CLAUDE.md: levels
and distances are code, never model arithmetic):

  - every distance is signed (+ above the price, - below), in ATR(D) and in %;
  - ages are in weekday sessions (an approximation: exchange holidays aren't removed);
  - only zones, levels and liquidity within reach are kept (nearest n each side, all strong
    zones within `reach_atr`), so the card stays ~2 KB;
  - every line keeps its test status: the L1 map (definitions v3) is UNTESTED; markers, not
    signals.

`card(l1, ...)` returns a dict; `text(card)` renders the lines a prompt carries. The same
card serves the book routine, the MCP `levels` tool and the step-2 context test.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import numpy as np
import pandas as pd

STATUS = "L1 map, definitions v3: UNTESTED. Markers, never signals."
N_ZONES = 3          # nearest zones each side
N_LEVELS = 3         # nearest pivot / virgin levels each side
REACH_ATR = 12.0     # zones, levels and liquidity beyond this many ATR(D) are left out
RECENT_SESSIONS = {"D": 30, "W": 65, "M": 130}  # sweeps / failed breaks older than this are left out
TFS = ("M", "W", "D")


def _f(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


def dist(level: Optional[float], price: float, atr: Optional[float]) -> dict:
    """Signed distance of a level from the price: ATR(D) multiples and %."""
    lv = _f(level)
    if lv is None or not price:
        return {}
    out = dict(px=round(lv, 2), pct=round((lv / price - 1) * 100, 2))
    if atr:
        out["atr"] = round((lv - price) / atr, 2)
    return out


def sessions_between(d0: Optional[str], d1: Optional[str]) -> Optional[int]:
    """Weekday sessions from d0 to d1 (0 = same day)."""
    if not d0 or not d1:
        return None
    try:
        return int(np.busday_count(str(d0)[:10], str(d1)[:10]))
    except ValueError:
        return None


def _event(e: Optional[dict]) -> Optional[str]:
    if not e:
        return None
    return f"{e.get('type')} {e.get('direction')} {e.get('level')} on {e.get('date') or e.get('period')}"


def _zone(z: dict, price: float, atr: Optional[float]) -> dict:
    lo, hi = float(z["low"]), float(z["high"])
    edge = lo if lo > price else hi if hi < price else price
    d = dist(edge, price, atr)
    return dict(lo=round(lo, 2), hi=round(hi, 2), strong=bool(z.get("strong")), edge_atr=d.get("atr"),
                edge_pct=d.get("pct"), why=str(z.get("why", ""))[:90])


def zones_near(zs: list[dict], price: float, atr: Optional[float], n: int = N_ZONES,
               reach: float = REACH_ATR) -> dict:
    """Nearest n zones above and below (plus any strong zone within reach) and the zone the
    price sits inside."""
    inside = [z for z in zs if z["low"] <= price <= z["high"]]
    above = sorted((z for z in zs if z["low"] > price), key=lambda z: z["low"])
    below = sorted((z for z in zs if z["high"] < price), key=lambda z: -z["high"])

    def pick(side: list[dict], edge) -> list[dict]:
        out = side[:n]
        if atr:
            out += [z for z in side[n:] if z.get("strong") and abs(edge(z) - price) / atr <= reach]
        return [_zone(z, price, atr) for z in out]

    return dict(above=pick(above, lambda z: z["low"]), below=pick(below, lambda z: z["high"]),
                inside=[_zone(z, price, atr) for z in inside])


def _tf(t: dict, price: float, atr_d: Optional[float]) -> dict:
    pd_ = t.get("premium_discount") or {}
    out = dict(state=t.get("state"), age_bars=t.get("age_bars"), last=_event(t.get("last_event")),
               protected=dist((t.get("protected") or {}).get("price"), price, atr_d),
               weak=dist((t.get("weak") or {}).get("price"), price, atr_d))
    if pd_:
        out["range"] = f"{pd_.get('side')} {pd_.get('position_pct')}% of {pd_.get('lo')}-{pd_.get('hi')}"
    return out


def _recent(items: list[dict], last_date: Optional[str], tf: str, kind: str) -> list[dict]:
    """The last two sweeps (kind 'sweep') or failed breaks ('failed') within RECENT_SESSIONS[tf]."""
    out = []
    for it in items or []:
        ago = sessions_between(it.get("date"), last_date)
        if ago is None or ago > RECENT_SESSIONS.get(tf, 30):
            continue
        e = dict(tf=tf, kind=kind, side=it.get("side"), level=it.get("level"), date=it.get("date"), ago=ago)
        e["extreme" if kind == "sweep" else "close"] = it.get("extreme" if kind == "sweep" else "close")
        out.append(e)
    return out[-2:]


def event_text(e: dict) -> str:
    if e["kind"] == "sweep":
        return (f"{e['tf']} swept {e['side']} {e['level']} (to {e.get('extreme')}) on {e['date']}, "
                f"{e['ago']} sessions ago")
    return (f"{e['tf']} failed break of {e['side']} {e['level']} (close {e.get('close')}) on {e['date']}, "
            f"{e['ago']} sessions ago")


def _liquidity(t: dict, price: float, atr: Optional[float], reach: float = REACH_ATR) -> dict:
    liq = t.get("liquidity") or {}
    out = {}
    for side in ("above", "below"):
        xs = [x for x in liq.get(side) or [] if x.get("status", "active") == "active"]
        xs = sorted(xs, key=lambda x: abs(float(x["level"]) - price))
        keep = []
        for x in xs[:2]:
            d = dist(x["level"], price, atr)
            if atr and abs(d.get("atr", 0)) > reach:
                continue
            keep.append(dict(kind=x.get("kind"), **d))
        out[side] = keep
    return out


def _pivots(pv: dict, price: float, atr: Optional[float], n: int = N_LEVELS) -> dict:
    out, levels = {}, []
    for tf in ("W", "M"):
        p = pv.get(tf) or {}
        c = p.get("cpr") or {}
        if c:
            out[tf] = dict(P=c.get("P"), BC=c.get("BC"), TC=c.get("TC"), width=c.get("width"),
                           relationship=c.get("relationship"), bias=c.get("bias"),
                           close_vs_cpr=p.get("close_vs_cpr_in_force"),
                           run=(p.get("cpr_trend") or {}).get("run"),
                           side=(p.get("cpr_trend") or {}).get("side"))
        for lv in p.get("levels") or []:
            if _f(lv.get("price")) is not None:
                levels.append((float(lv["price"]), f"{tf} {lv.get('kind', '')} {lv.get('name')}".replace("  ", " ")))
    above = sorted((x for x in levels if x[0] > price), key=lambda x: x[0])[:n]
    below = sorted((x for x in levels if x[0] < price), key=lambda x: -x[0])[:n]
    out["levels_above"] = [dict(name=nm, **dist(px, price, atr)) for px, nm in above]
    out["levels_below"] = [dict(name=nm, **dist(px, price, atr)) for px, nm in below]
    return out


def _value(pr: dict, price: float) -> dict:
    out = {}
    for tf, p in ((pr.get("periods") or {}).items()):
        mz = p.get("money_zone") or {}
        if not mz:
            continue
        val, poc, vah = _f(mz.get("VAL")), _f(mz.get("POC")), _f(mz.get("VAH"))
        where = (None if val is None or vah is None else
                 "above VAH" if price > vah else "below VAL" if price < val else "inside value")
        out[tf] = dict(period=p.get("from_period"), VAL=val, POC=poc, VAH=vah, price=where,
                       relationship=mz.get("relationship"), vpoc=(p.get("vpoc") or {}).get("relationship"))
    return out


def _virgin(pr: dict, price: float, atr: Optional[float], n: int = 2, reach: float = REACH_ATR) -> dict:
    vs = [v for v in pr.get("virgin") or [] if _f(v.get("price")) is not None]
    if atr:
        vs = [v for v in vs if abs(float(v["price"]) - price) / atr <= reach]
    lab = lambda v: f"{v.get('tf')} {v.get('kind')} {v.get('name')} {v.get('period')}"
    above = sorted((v for v in vs if v["price"] > price), key=lambda v: v["price"])[:n]
    below = sorted((v for v in vs if v["price"] < price), key=lambda v: -v["price"])[:n]
    return dict(above=[dict(name=lab(v), **dist(v["price"], price, atr)) for v in above],
                below=[dict(name=lab(v), **dist(v["price"], price, atr)) for v in below])


def action(daily: Optional[pd.DataFrame], as_of: date) -> dict:
    """Recent price action from daily bars dated before as_of (date, o, h, l, c)."""
    if daily is None or not len(daily):
        return {}
    d = daily[daily["date"] < pd.Timestamp(as_of)]
    if len(d) < 2:
        return {}
    c = d["c"].to_numpy(dtype=float)
    chg = lambda k: round((c[-1] / c[-1 - k] - 1) * 100, 2) if len(c) > k else None
    y = d.tail(250)
    hi20, lo20 = float(d["h"].tail(20).max()), float(d["l"].tail(20).min())
    return dict(chg_1d=chg(1), chg_5d=chg(5), chg_20d=chg(20),
                from_52w_high_pct=round((c[-1] / float(y["h"].max()) - 1) * 100, 2),
                from_52w_low_pct=round((c[-1] / float(y["l"].min()) - 1) * 100, 2),
                pos_in_20d_range_pct=round((c[-1] - lo20) / (hi20 - lo20) * 100, 1) if hi20 > lo20 else None)


def card(sym: str, l1: dict, daily: Optional[pd.DataFrame] = None, plans: Optional[list[dict]] = None,
         notes: Optional[list[str]] = None) -> dict:
    """The context card for one symbol from its L1 read. `plans`: playbook plans (or other
    candidate trades) to show beside the map; `notes`: dated facts code knows (results date, ...)."""
    if not l1 or "error" in l1:
        return dict(sym=sym, error=(l1 or {}).get("error", "no read"))
    price = float(l1["price"])
    tf = l1.get("tf") or {}
    atr_d = _f((tf.get("D") or {}).get("atr"))
    htf = l1.get("htf") or {}
    last = l1.get("last_date") or (tf.get("D") or {}).get("last_bar")
    as_of = date.fromisoformat(l1["as_of"])
    events = []
    for k in TFS:
        t = tf.get(k) or {}
        events += _recent(t.get("sweeps"), last, k, "sweep")
        events += _recent(t.get("failed_breaks"), last, k, "failed")
    l2 = (l1.get("l2") or {}).get("pivots") or {}
    out = dict(sym=sym, as_of=l1["as_of"], last_date=last, price=price, atr_d=atr_d, atr_w=_f(htf.get("atr_w")),
               status=STATUS, action=action(daily, as_of),
               structure={k: _tf(tf[k], price, atr_d) for k in TFS if tf.get(k)},
               alignment=(l1.get("alignment") or {}).get("text"),
               events=events,
               zones=zones_near(htf.get("zones") or [], price, atr_d),
               coverage=htf.get("coverage"),
               liquidity=_liquidity(tf.get("D") or {}, price, atr_d),
               pivots=_pivots(l1.get("pivots") or {}, price, atr_d),
               value=_value(l1.get("profiles") or {}, price),
               virgin=_virgin(l1.get("profiles") or {}, price, atr_d),
               daily_cpr=dict(l2.get("cpr") or {}, session=l2.get("from_session")) if l2 else None,
               plans=plans or [], notes=notes or [])
    return out


# ─── text ────────────────────────────────────────────────────────────────────

def _d(x: dict) -> str:
    if not x:
        return "-"
    a = f"{x['atr']:+.1f}ATR " if x.get("atr") is not None else ""
    return f"{x['px']:g} ({a}{x['pct']:+.1f}%)"


def _z(z: dict) -> str:
    s = "STRONG " if z["strong"] else ""
    e = f"{z['edge_atr']:+.1f}ATR {z['edge_pct']:+.1f}%" if z.get("edge_atr") is not None else f"{z['edge_pct']:+.1f}%"
    return f"{s}{z['lo']:g}-{z['hi']:g} [{e}] {z['why']}"


def text(c: dict) -> str:
    """The card as prompt lines (~2 KB)."""
    if "error" in c:
        return f"## {c['sym']}: no read ({c['error']})"
    a = c.get("action") or {}
    ln = [f"## {c['sym']}  close {c['price']:g} on {c['last_date']}  ATR(D) {c['atr_d']}  ATR(W) {c['atr_w']}",
          f"status: {c['status']}"]
    if a:
        ln.append(f"action: 1d {a.get('chg_1d')}%  5d {a.get('chg_5d')}%  20d {a.get('chg_20d')}%  "
                  f"from 52w high {a.get('from_52w_high_pct')}%  from 52w low +{a.get('from_52w_low_pct')}%  "
                  f"in 20d range {a.get('pos_in_20d_range_pct')}%")
    for k, t in c["structure"].items():
        ln.append(f"{k}: {t['state']} (age {t['age_bars']} bars; last {t['last']}); protected {_d(t['protected'])}; "
                  f"weak {_d(t['weak'])}; {t.get('range', '')}")
    if c.get("alignment"):
        ln.append(f"alignment: {c['alignment']}")
    for e in c["events"]:
        ln.append(f"event: {event_text(e)}")
    z = c["zones"]
    for x in z["inside"]:
        ln.append(f"INSIDE zone: {_z(x)}")
    for x in z["above"]:
        ln.append(f"zone above: {_z(x)}")
    for x in z["below"]:
        ln.append(f"zone below: {_z(x)}")
    liq = c["liquidity"]
    for side in ("above", "below"):
        for x in liq.get(side) or []:
            ln.append(f"liquidity {side}: {x['kind']} {_d(x)}")
    pv = c["pivots"]
    for tf in ("W", "M"):
        p = pv.get(tf)
        if p:
            ln.append(f"{tf} CPR {p['BC']}/{p['P']}/{p['TC']} {p['width']}, {p['relationship']}, {p['bias']}; "
                      f"last {tf} close {p['close_vs_cpr']} its CPR ({p['side']} {p['run']} periods)")
    if pv.get("levels_above") or pv.get("levels_below"):
        ln.append("pivots above: " + "; ".join(f"{x['name']} {_d(x)}" for x in pv["levels_above"]))
        ln.append("pivots below: " + "; ".join(f"{x['name']} {_d(x)}" for x in pv["levels_below"]))
    for tf, v in c["value"].items():
        ln.append(f"{tf} value {v['period']}: VAL {v['VAL']} POC {v['POC']} VAH {v['VAH']}; price {v['price']}; "
                  f"{v['relationship']}; VPOC {v['vpoc']}")
    vg = c["virgin"]
    if vg["above"] or vg["below"]:
        ln.append("virgin above: " + "; ".join(f"{x['name']} {_d(x)}" for x in vg["above"]))
        ln.append("virgin below: " + "; ".join(f"{x['name']} {_d(x)}" for x in vg["below"]))
    if c.get("daily_cpr"):
        d = c["daily_cpr"]
        ln.append(f"daily CPR (from {d.get('session')}): {d.get('BC')}/{d.get('P')}/{d.get('TC')} {d.get('reading')}")
    for p in c["plans"]:
        ln.append("plan: " + (p if isinstance(p, str) else ", ".join(f"{k} {v}" for k, v in p.items())))
    for n in c["notes"]:
        ln.append(f"note: {n}")
    return "\n".join(ln)
