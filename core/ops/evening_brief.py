"""The evening brief (docs/EXECUTION_PLAN_2026-11-19.md, E6): pure parts. Code-only, no model.

scripts/evening_brief.py does the I/O (L1 store, index bars, the call plans' state, the results
calendar, Telegram) and calls these:

  breadth_row  one stock's W and D structure state and the day's sweeps (structure only: no zones,
               so the top 500 take minutes, not the 80 of the full playbook scan)
  breadth      the counts over the universe
  trades       the reference trades a candidate is checked on (its own plan, and the map plan)
  vetoes       the four markers code flags on a trade. MARKERS, NOT ORDERS: the map is untested
               (definitions v3) and the brief decides nothing.
  text         the Telegram text

The vetoes, fixed here (2026-11-21) before any brief was read:
  V1 stop in a strong zone: the stop lies inside a strong HTF zone (low <= stop <= high).
  V2 R:R < 1 to the first obstacle: the first obstacle is the nearest edge of any HTF zone or D zone
     strictly beyond both the price and the entry in the trade's direction (a long's: the lowest
     zone low above both). R:R = (obstacle - entry) / (entry - stop) for a long, mirrored for a short. No stop or
     no obstacle: not checked.
  V3 into an opposing W/M zone: a long whose price is inside, or within 1 ATR(W) under, an HTF zone
     with a W or M supply / bear OB / bear FVG band; a short mirrors with demand / bull OB / bull FVG
     (the HDFCBANK lesson, 2026-11-02: a short into a 4-year weekly demand zone).
  V4 results within 5 sessions: the next NSE results board meeting is at most
     call_plan.RESULTS_BLACKOUT weekdays after the session.

The map plan's stop is not known before its sweep happens (call_plan.step sets it 0.1 ATR beyond the
sweep's extreme). The brief checks it at the SHALLOWEST sweep that qualifies:
level - (SWEEP_DEPTH_ATR + STOP_BUFFER_ATR) * ATR for a long, and says it is an estimate.
"""
from __future__ import annotations

from typing import Optional

from core.market_map import call_plan as cp

V3_ATR_W = 1.0
OPPOSING = {"long": ("supply", "bear_ob", "bear_fvg"), "short": ("demand", "bull_ob", "bull_fvg")}
SIDE = {"CE": "long", "PE": "short", "long": "long", "short": "short"}
N_SWEEPS_SHOWN = 12


def _sg(side: str) -> int:
    return 1 if SIDE[side] == "long" else -1


# ─── breadth ─────────────────────────────────────────────────────────────────

def breadth_row(sym: str, summaries: dict, last: str) -> dict:
    """`summaries`: {"W": structure.summary(...), "D": ...}. The day's sweeps: D sweeps dated `last`,
    and W sweeps on the week that closed on `last` (W bars carry their last session's date)."""
    row = dict(sym=sym, W=(summaries.get("W") or {}).get("state", "none"),
               D=(summaries.get("D") or {}).get("state", "none"), sweeps=[])
    for tf in ("D", "W"):
        for w in (summaries.get(tf) or {}).get("sweeps") or []:
            if w.get("date") == last:
                row["sweeps"].append(dict(tf=tf, side=w["side"], level=w["level"], extreme=w["extreme"]))
    return row


def breadth(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    count = lambda tf, s: sum(r[tf] == s for r in ok)                     # noqa: E731
    sweeps = [dict(sym=r["sym"], **w) for r in ok for w in r["sweeps"]]
    return dict(n=len(ok), errors=len(rows) - len(ok),
                W=dict(up=count("W", "up"), down=count("W", "down"), none=count("W", "none")),
                D=dict(up=count("D", "up"), down=count("D", "down"), none=count("D", "none")),
                sweeps=dict(low=[s for s in sweeps if s["side"] == "low"], high=[s for s in sweeps if s["side"] == "high"]))


# ─── candidates ──────────────────────────────────────────────────────────────

def trades(cand: dict, version: dict) -> list[dict]:
    """The reference trades for one candidate. `cand`: call_plans' call (sym, side CE/PE, spot, src)
    plus the Darvas plan's stop/target when src is Darvas. `version`: the map plan made on the call day."""
    side = SIDE[cand["side"]]
    out = []
    if cand.get("stop") is not None:
        out.append(dict(basis=f"{cand.get('src', 'F&O')} plan", entry=float(cand["spot"]), stop=float(cand["stop"]),
                        target=cand.get("target"), estimate=False))
    else:
        out.append(dict(basis="as sent (no stop)", entry=float(cand["spot"]), stop=None, target=None, estimate=False))
    sw, atr = (version or {}).get("sweep"), (version or {}).get("atr")
    if sw and atr:
        sg = _sg(side)
        stop = round(sw["level"] - sg * (cp.SWEEP_DEPTH_ATR + cp.STOP_BUFFER_ATR) * atr, 2)
        out.append(dict(basis="map plan (sweep)", entry=float(sw["level"]), stop=stop,
                        target=(sw.get("target") or {}).get("level"), estimate=True))
    return out


def first_obstacle(card: dict, side: str, entry: Optional[float] = None) -> Optional[float]:
    """The nearest zone edge beyond both the price and the entry in the trade's direction."""
    price, lg = card["price"], SIDE[side] == "long"
    ref = price if entry is None else (max(price, entry) if lg else min(price, entry))
    zs = (card.get("zones") or {}).get("above" if lg else "below", []) + \
         (card.get("zones_d") or {}).get("above" if lg else "below", [])
    edges = [z["lo"] if lg else z["hi"] for z in zs]
    edges = [e for e in edges if (e > ref if lg else e < ref)]
    return (min(edges) if lg else max(edges)) if edges else None


def opposing_zone(htf_zones: list[dict], price: float, atr_w: Optional[float], side: str) -> Optional[dict]:
    """The HTF zone a trade runs into (V3), or None. `htf_zones`: l1["htf"]["zones"] (htf.compact)."""
    lg, kinds = SIDE[side] == "long", OPPOSING[SIDE[side]]
    reach = V3_ATR_W * (atr_w or 0.0)
    for z in sorted(htf_zones, key=lambda z: abs(z["mid"] - price)):
        bands = [b for b in z.get("bands") or [] if b["tf"] in ("W", "M") and b["kind"] in kinds]
        if not bands:
            continue
        inside = z["low"] <= price <= z["high"]
        near = (0 < z["low"] - price <= reach) if lg else (0 < price - z["high"] <= reach)
        if inside or near:
            return dict(low=z["low"], high=z["high"], strong=z["strong"], inside=inside,
                        bands=[f"{b['tf']} {b['kind']} {b['lo']:g}-{b['hi']:g}" for b in bands][:3])
    return None


def vetoes(trade: dict, side: str, card: dict, htf_zones: list[dict], results_in: Optional[int]) -> list[dict]:
    out = []
    stop, entry, sg = trade.get("stop"), trade["entry"], _sg(side)
    est = " (estimated stop)" if trade.get("estimate") else ""
    if stop is not None:
        zs = [z for k in ("above", "below", "inside") for z in (card.get("zones") or {}).get(k, []) if z["strong"]]
        hit = next((z for z in zs if z["lo"] <= stop <= z["hi"]), None)
        if hit:
            out.append(dict(code="V1", text=f"stop {stop:g} inside strong zone {hit['lo']:g}-{hit['hi']:g}{est}"))
        ob = first_obstacle(card, side, entry)
        risk = sg * (entry - stop)
        if ob is not None and risk > 0:
            rr = sg * (ob - entry) / risk
            if rr < 1:
                out.append(dict(code="V2", text=f"R:R {rr:.2f} to the first obstacle {ob:g}{est}", rr=round(rr, 2)))
    oz = opposing_zone(htf_zones, card["price"], card.get("atr_w"), side)
    if oz:
        where = "inside" if oz["inside"] else "under" if SIDE[side] == "long" else "over"
        out.append(dict(code="V3", text=f"{SIDE[side]} {where} {oz['low']:g}-{oz['high']:g} ({'; '.join(oz['bands'])})"))
    if results_in is not None and results_in <= cp.RESULTS_BLACKOUT:
        out.append(dict(code="V4", text=f"results in {results_in} session{'s' if results_in != 1 else ''}"))
    return out


# ─── text ────────────────────────────────────────────────────────────────────

def _p(x) -> str:
    return "—" if x is None else f"{x:,.2f}".rstrip("0").rstrip(".")


def index_lines(sym: str, c: dict) -> list[str]:
    if not c or c.get("error"):
        return [f"{sym}: no read ({(c or {}).get('error', 'missing')})"]
    s = c.get("structure") or {}
    st = lambda tf: (s.get(tf) or {})                                     # noqa: E731
    lv = lambda d: _p((d or {}).get("px"))                                # noqa: E731
    strong = lambda k: next((z for z in (c.get("zones") or {}).get(k, []) if z["strong"]), None)   # noqa: E731
    zb, za = strong("below"), strong("above")
    zt = lambda z: f"{_p(z['lo'])}-{_p(z['hi'])} ({abs(z['edge_pct']):.1f}%)" if z else "none"  # noqa: E731
    return [f"{sym} {_p(c['price'])}: {c.get('alignment')}",
            f"  W {st('W').get('state')}: protected {lv(st('W').get('protected'))}, weak {lv(st('W').get('weak'))}"
            f" · D {st('D').get('state')}: protected {lv(st('D').get('protected'))}, weak {lv(st('D').get('weak'))}",
            f"  strong zone below {zt(zb)} · above {zt(za)}"]


def text(b: dict) -> str:
    L = [f"🌙 Evening brief {b['session']} (code only; map v3 UNTESTED: markers, never signals)", ""]
    for sym in ("NIFTY", "BANKNIFTY"):
        L += index_lines(sym, (b.get("index") or {}).get(sym))
    br = b.get("breadth") or {}
    if br:
        L += ["", f"Breadth (top {br['n']}): W up {br['W']['up']} / down {br['W']['down']} / none {br['W']['none']}"
                  f" · D up {br['D']['up']} / down {br['D']['down']}"]
        for side, name in (("low", "lows"), ("high", "highs")):
            sw = br["sweeps"][side]
            if sw:
                names = ", ".join(f"{s['sym']}{'(W)' if s['tf'] == 'W' else ''}" for s in sw[:N_SWEEPS_SHOWN])
                L.append(f"  swept {name} today: {len(sw)}: {names}{' …' if len(sw) > N_SWEEPS_SHOWN else ''}")
    cands = b.get("candidates") or []
    L += ["", f"Candidates: {len(cands)}" + ("" if cands else " (no screener or Darvas calls tonight)")]
    for c in cands:
        L.append(f"• {c['sym']} {c['side']} [{c['src']}] at {_p(c['spot'])}" + (f": {c['error']}" if c.get("error") else ""))
        for t in c.get("trades") or []:
            L.append(f"   {t['basis']}: entry {_p(t['entry'])}, stop {_p(t['stop'])}{' est.' if t['estimate'] else ''}"
                     f", target {_p(t['target'])}")
            for v in t.get("vetoes") or []:
                L.append(f"     ⚠ {v['code']} {v['text']}")
            if not t.get("vetoes"):
                L.append("     no veto flagged")
        if c.get("results"):
            L.append(f"   results {c['results']}")
    if b.get("warnings"):
        L += [""] + [f"⚠ {w}" for w in b["warnings"]]
    L += ["", "Turn this into ledger calls by docs/TRADE_REASONING.md (scripts/ledger.py add)."]
    return "\n".join(L)
