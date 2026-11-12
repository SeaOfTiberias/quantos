"""
L1 zones and levels on weekly and monthly bars (sprint plan S5, slice 3;
docs/MARKET_MAP_DEFINITIONS.md v1 §3): demand and supply bases (§3.1), multi-touch levels
(§3.2), order blocks (§3.3), equal highs and lows with their sweeps (§3.4), premium and
discount (§3.5); v3 (docs/MARKET_MAP_DEFINITIONS_V3.md, 2026-11-13): fair-value gaps (H5),
daily mitigation of bands and gaps (H2, H5), and the "at a break" flag the strong rule
uses (H3.1).

Every function takes the bars a read may use (structure.completed), so a zone is what was
known before the read's day. Choices v1 leaves open, fixed here before any golden-set chart:

  §3.1  The ATR(TF) is the base's last bar's, for both the 1.0-ATR range test and the
        2.0-ATR departure. A base is a run of consecutive bars with range <= 1 ATR that the
        next bar does not extend (the next bar's range is wider); a run longer than 6 bars
        keeps its last 6, the bars nearest the departure. The departure window is the 3
        bars after the base; the first close 2 ATR beyond an edge decides the direction.
        Strength = the furthest close in the window beyond that edge, in ATR. "Tests" =
        every bar after the departure bar that trades into the zone.
  §3.2  Swing points are the §1 zig-zag swings. The band width uses ATR(W) of the last bar.
        Prices are sorted and grouped greedily from the lowest: the widest run within
        0.3 ATR starting at each price, kept if it qualifies, then the next run starts
        after it.
  §3.3  "Searching back at most 3 bars": the protected bar and up to 3 bars before it.
        Events that pick the same bar give one order block.
  §3.4  Swing highs are the §1 zig-zag swings; 0.1 ATR(TF) is the ATR at the later swing's
        confirmation bar; members of a level all lie within 0.1 ATR of each other. A swept
        or broken level is retired; a later match starts a new level.
  §3.5  Price = the last completed daily close.

v3 choices this file fixes (definitions v3 leaves them open):
  H2    A band's daily bars start the day after its "formed" bar: the departure bar for
        §3.1 (its close is already 2 ATR(TF) beyond the base, so price has left the zone
        by 2 ATR, v1's precondition for a test) and the break bar for an order block. A
        touch is a run of daily bars whose range meets the band; the run ends at the first
        daily bar wholly outside. When the daily close through the far edge and the start
        of the second touch fall on the same day, the reason is `broken`.
  H3.1  A §3.1 zone is "at a break" when a BOS or CHoCH on the same TF, in the departure's
        direction, falls on a bar from the base's first bar to 3 bars after its last.
        Order blocks are at a break by definition.
  H5    A gap forms on bar i; its daily bars start the day after bar i. Its ATR(TF) is bar
        i's. A daily bar that reaches the far edge fills it, whatever the close.

Untested: no fidelity test (§9) has run. Zones describe the chart; they are not signals.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from core.market_map import structure as st

BASE_ATR, DEPART_ATR, BASE_MAX, DEPART_BARS = 1.0, 2.0, 6, 3        # §3.1
MT_ATR, MT_MIN, MT_SPAN_W = 0.3, 3, 26                              # §3.2
OB_BACK = 3                                                         # §3.3
EQ_ATR, EQ_GAP = 0.1, 5                                             # §3.4
FVG_ATR = 0.1                                                       # v3 H5
BULL = ("demand", "bull_ob", "bull_fvg")                            # bands that hold below the price


def _arr(bars):
    return (bars[x].to_numpy(float) for x in ("o", "h", "l", "c"))


def _p(bars, i):
    return bars["period"].iat[i]


def _d(bars, i):
    """The last session of bar i (ISO date): a zone formed on bar i is checked on the daily
    bars after it (v3 H2, H5)."""
    return pd.Timestamp(bars["date"].iat[i]).date().isoformat()


# ─── §3.1 demand and supply ──────────────────────────────────────────────────

def bases(bars: pd.DataFrame, a: np.ndarray, events: Optional[list[dict]] = None) -> list[dict]:
    """Demand and supply zones still valid at the last bar (on TF closes; v3 H2 then
    applies the daily rules)."""
    o, h, l, c = _arr(bars)
    n = len(bars)
    rng = h - l
    out = []
    for e in range(n):
        if np.isnan(a[e]) or rng[e] > BASE_ATR * a[e]:
            continue
        if e + 1 < n and rng[e + 1] <= BASE_ATR * a[e]:
            continue                                         # the next bar extends the base
        s0 = e
        while s0 - 1 >= 0 and e - (s0 - 1) < BASE_MAX and rng[s0 - 1] <= BASE_ATR * a[e]:
            s0 -= 1
        top, bot = h[s0:e + 1].max(), l[s0:e + 1].min()
        body_hi = np.maximum(o, c)[s0:e + 1].max()
        body_lo = np.minimum(o, c)[s0:e + 1].min()
        w = slice(e + 1, min(e + 1 + DEPART_BARS, n))
        kind, dep = None, None
        for j in range(w.start, w.stop):
            if c[j] >= top + DEPART_ATR * a[e]:
                kind, dep = "demand", j
                break
            if c[j] <= bot - DEPART_ATR * a[e]:
                kind, dep = "supply", j
                break
        if kind is None:
            continue
        if kind == "demand":
            lo, hi = bot, body_hi
            strength = (c[w].max() - top) / a[e]
        else:
            lo, hi = body_lo, top
            strength = (bot - c[w].min()) / a[e]
        after = slice(dep + 1, n)
        bad = (c[after] < lo) if kind == "demand" else (c[after] > hi)
        if bad.any():
            continue                                         # invalidated: dropped (§3.1)
        touch = (l[after] <= hi) if kind == "demand" else (h[after] >= lo)
        want = "up" if kind == "demand" else "down"
        at_break = any(ev["direction"] == want and s0 <= ev["i"] <= e + DEPART_BARS for ev in events or [])
        out.append(dict(kind=kind, lo=float(lo), hi=float(hi), base=f"{_p(bars, s0)}..{_p(bars, e)}",
                        formed=_d(bars, dep), at_break=at_break,
                        base_bars=e - s0 + 1, departed=_p(bars, dep), strength_atr=round(float(strength), 2),
                        tests=int(touch.sum()),
                        last_test=_p(bars, dep + 1 + int(np.nonzero(touch)[0][-1])) if touch.any() else None))
    return out


# ─── §3.2 multi-touch levels ─────────────────────────────────────────────────

def multi_touch(bars: pd.DataFrame, swings: list, atr_w: float) -> list[dict]:
    if not swings or not atr_w or np.isnan(atr_w):
        return []
    pts = sorted(((s.price, s.i, s.kind) for s in swings))
    w = MT_ATR * atr_w
    out, i = [], 0
    while i < len(pts):
        j = i
        while j + 1 < len(pts) and pts[j + 1][0] - pts[i][0] <= w:
            j += 1
        grp = pts[i:j + 1]
        idx = [g[1] for g in grp]
        if len(grp) >= MT_MIN and max(idx) - min(idx) >= MT_SPAN_W:
            pr = [g[0] for g in grp]
            out.append(dict(kind="multi_touch", level=float(np.median(pr)), lo=float(min(pr)), hi=float(max(pr)),
                            touches=len(grp), first=_p(bars, min(idx)), last=_p(bars, max(idx))))
            i = j + 1
        else:
            i += 1
    return out


# ─── §3.3 order blocks ───────────────────────────────────────────────────────

def order_blocks(bars: pd.DataFrame, events: list[dict]) -> list[dict]:
    o, h, l, c = _arr(bars)
    n = len(bars)
    seen, out = set(), []
    for ev in events:
        p = ev.get("prot_i")
        if p is None:
            continue
        up = ev["direction"] == "up"
        b = p
        for j in range(p, max(p - OB_BACK, 0) - 1, -1):
            if (c[j] < o[j]) if up else (c[j] > o[j]):
                b = j
                break
        if b in seen:
            continue
        seen.add(b)
        after = slice(ev["i"] + 1, n)
        lo, hi = l[b], h[b]
        bad = (c[after] < lo) if up else (c[after] > hi)
        if bad.any():
            continue                                         # invalidated
        touch = (l[after] <= hi) if up else (h[after] >= lo)
        out.append(dict(kind="bull_ob" if up else "bear_ob", lo=float(lo), hi=float(hi), bar=_p(bars, b),
                        formed=_d(bars, ev["i"]), at_break=True,
                        event=f"{ev['type']} {ev['direction']} {_p(bars, ev['i'])}", mitigated=bool(touch.any())))
    return out


# ─── v3 H5 fair-value gaps ───────────────────────────────────────────────────

def fvgs(bars: pd.DataFrame, a: np.ndarray) -> list[dict]:
    """Three-bar gaps of at least 0.1 ATR(TF), every one found (v3 H5); `mitigate` then
    drops the filled ones and trims the partly filled."""
    o, h, l, c = _arr(bars)
    out = []
    for i in range(2, len(bars)):
        if np.isnan(a[i]):
            continue
        for kind, lo, hi in (("bull_fvg", h[i - 2], l[i]), ("bear_fvg", h[i], l[i - 2])):
            if hi - lo >= FVG_ATR * a[i] and hi > lo:
                out.append(dict(kind=kind, lo=float(lo), hi=float(hi), bar=_p(bars, i), formed=_d(bars, i),
                                at_break=False, size_atr=round(float((hi - lo) / a[i]), 2)))
    return out


# ─── v3 H2 / H5 daily mitigation ─────────────────────────────────────────────

def mitigate(zones: list[dict], daily: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Apply v3's daily rules to bands (demand, supply, order blocks) and gaps; other zones
    pass through unchanged. Returns (kept, removed); a removed zone carries `removed`
    (broken, spent or filled) and `removed_on`."""
    if not len(daily):
        return list(zones), []
    dates = pd.to_datetime(daily["date"]).to_numpy("datetime64[D]")
    dh, dl, dc = (daily[x].to_numpy(float) for x in ("h", "l", "c"))
    kept, removed = [], []
    for z in zones:
        if z["kind"] not in ("demand", "supply", "bull_ob", "bear_ob", "bull_fvg", "bear_fvg"):
            kept.append(z)
            continue
        z = dict(z)
        s = int(np.searchsorted(dates, np.datetime64(z["formed"], "D"), side="right"))
        h, l, c = dh[s:], dl[s:], dc[s:]
        bull = z["kind"] in BULL
        if z["kind"].endswith("_fvg"):                                  # H5: filled, or trimmed
            far = (l <= z["lo"]) if bull else (h >= z["hi"])
            if far.any():
                k = s + int(np.argmax(far))
                removed.append(dict(z, removed="filled", removed_on=str(dates[k])))
                continue
            if len(h):
                if bull:
                    z["hi"] = float(min(z["hi"], l.min()))
                else:
                    z["lo"] = float(max(z["lo"], h.max()))
            kept.append(z)
            continue
        brk = (c < z["lo"]) if bull else (c > z["hi"])                  # H2: a daily close through the far edge
        ins = (l <= z["hi"]) & (h >= z["lo"])
        starts = np.nonzero(ins & ~np.concatenate(([False], ins[:-1])))[0]
        b = int(np.argmax(brk)) if brk.any() else None
        sp = int(starts[1]) if len(starts) >= 2 else None
        if b is not None and (sp is None or b <= sp):
            removed.append(dict(z, removed="broken", removed_on=str(dates[s + b])))
            continue
        if sp is not None:
            removed.append(dict(z, removed="spent", removed_on=str(dates[s + sp])))
            continue
        z["touches"] = int(len(starts))
        z["tested_once"] = bool(len(starts) == 1)
        z["fresh"] = not len(starts)
        z["last_touch"] = str(dates[s + int(starts[0])]) if len(starts) else None
        kept.append(z)
    return kept, removed


# ─── §3.4 equal highs / lows ─────────────────────────────────────────────────

def _retired(h, l, c, level, start, hi_side) -> Optional[tuple[str, int]]:
    for t in range(start, len(c)):
        if hi_side and h[t] > level:
            return ("broken" if c[t] > level else "swept"), t
        if not hi_side and l[t] < level:
            return ("broken" if c[t] < level else "swept"), t
    return None


def equal_levels(bars: pd.DataFrame, swings: list, a: np.ndarray) -> list[dict]:
    """EQH / EQL levels with their fate: active, swept (a LIQUIDITY_SWEEP event) or broken."""
    o, h, l, c = _arr(bars)
    out = []
    for kind, hi_side in (("H", True), ("L", False)):
        sw = [s for s in swings if s.kind == kind]
        levels: list[dict] = []
        for s in sw:
            tol = EQ_ATR * a[s.confirm_i] if not np.isnan(a[s.confirm_i]) else 0.0
            joined = False
            for lv in levels:
                if lv["end"] is not None and lv["end"] < s.confirm_i:
                    continue                                 # retired before this swing was known
                prices = lv["prices"] + [s.price]
                lev = max(prices) if hi_side else min(prices)
                gap_ok = s.i - lv["last_i"] >= EQ_GAP
                between = c[lv["last_i"] + 1:s.i]
                clean = not len(between) or ((between.max() <= lev) if hi_side else (between.min() >= lev))
                if max(prices) - min(prices) <= tol and gap_ok and clean:
                    lv["prices"].append(s.price); lv["idx"].append(s.i)
                    lv["last_i"], lv["confirm_i"] = s.i, s.confirm_i
                    joined = True
                    break
            if joined:
                continue
            for p in [x for x in sw if x.confirm_i < s.confirm_i][::-1]:
                lev = max(p.price, s.price) if hi_side else min(p.price, s.price)
                between = c[p.i + 1:s.i]
                clean = not len(between) or ((between.max() <= lev) if hi_side else (between.min() >= lev))
                if abs(p.price - s.price) <= tol and s.i - p.i >= EQ_GAP and clean:
                    levels.append(dict(prices=[p.price, s.price], idx=[p.i, s.i], last_i=s.i,
                                       confirm_i=s.confirm_i, end=None))
                    break
            for lv in levels:                                # fate of every level up to now
                lev = max(lv["prices"]) if hi_side else min(lv["prices"])
                r = _retired(h, l, c, lev, lv["confirm_i"] + 1, hi_side)
                lv["end"] = r[1] if r else None
        for lv in levels:
            lev = max(lv["prices"]) if hi_side else min(lv["prices"])
            r = _retired(h, l, c, lev, lv["confirm_i"] + 1, hi_side)
            out.append(dict(kind="EQH" if hi_side else "EQL", level=float(lev), lo=float(min(lv["prices"])),
                            hi=float(max(lv["prices"])), swings=[_p(bars, i) for i in lv["idx"]],
                            status=r[0] if r else "active", at=_p(bars, r[1]) if r else None))
    return out


# ─── §3.5 premium / discount ─────────────────────────────────────────────────

def premium_discount(summary: dict, price: Optional[float]) -> Optional[dict]:
    if price is None or summary.get("state") not in ("up", "down"):
        return None
    p, w = summary["protected"]["price"], summary["weak"]["price"]
    lo, hi = (p, w) if summary["state"] == "up" else (w, p)
    if hi <= lo:
        return None
    pos = (price - lo) / (hi - lo)
    return dict(lo=lo, hi=hi, eq=round((lo + hi) / 2, 2), position_pct=round(100 * pos, 1),
                side="premium" if pos > 0.5 else "discount" if pos < 0.5 else "equilibrium")


# ─── per timeframe ───────────────────────────────────────────────────────────

def tf_zones(bars: pd.DataFrame, run: st.Structure, tf: str) -> dict:
    a = st.atr(bars)
    out = dict(demand_supply=bases(bars, a, run.events), order_blocks=order_blocks(bars, run.events),
               fvg=fvgs(bars, a), liquidity=equal_levels(bars, run.swings, a))
    if tf == "W":
        out["multi_touch"] = multi_touch(bars, run.swings, float(a[-1]) if len(a) else None)
    for v in out.values():
        for z in v:
            z["tf"] = tf
    return out
