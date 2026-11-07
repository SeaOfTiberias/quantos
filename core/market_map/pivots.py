"""
L1 period pivots: floor pivots, CPR, Camarilla and the previous period's range, for the
week, month, quarter and year (sprint plan S5, slice 4; docs/MARKET_MAP_DEFINITIONS.md v1
§4, Ochoa's *Secrets of a Pivot Boss*). Money zones, VPOCs and virgin levels need the
profiles and come in slice 5.

A read for day D uses the pivots of D's own period, which come from the last completed
period's H, L and C (structure.completed leaves D's period out). Pivot n applies to the
period after bar n; the CPR "in force during" period n is the one from bar n - 1.

Map levels (`in_map`, for clustering and the fidelity test), per §4:
  floor   Pivot, R1, R2, S1, S2 on every period; R3, R4, S3, S4 on month and year only
          (computed and shown on week and quarter, not in the map);
  CPR     TC and BC (the pivot is the floor pivot);
  Camarilla  H3, H4, L3, L4; H5/L5 shown, not in the map; H1, H2, L1, L2 shown only when
          the Camarilla width reads "wide", never in the map;
  range   the previous period's high and low.
All are family "pivot" (§6). The quarter is not Ochoa's (Ch. 9 has none): labelled so.

Choices v1 leaves open, fixed here before any golden-set chart:
  - Percentile rank = (previous widths below + half of those equal) / their count, over
    the previous up to 20 periods; at least 8 needed.
  - Camarilla width = (H3 - L3) / C x 100, so it compares across years like CPR width %.
  - A relationship none of the seven rules fits (an edge exactly equal to the previous
    one) is "unclassified".
  - CPR trend run: consecutive periods, ending with the last completed one, whose close
    was above TC (or below BC) of the CPR in force during them; 0 when the last closed
    inside.

Recorded and shown only: none of these is a signal, and none is tested yet.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

PERIODS = ("W", "M", "Q", "Y")
WINDOW, MIN_HIST = 20, 8
NARROW, WIDE = 0.25, 0.75
UNCHANGED_TOL = 0.10
BIAS = {"unchanged": "sideways or breakout", "higher value": "bullish", "lower value": "bearish",
        "outside": "sideways", "inside": "breakout", "overlapping higher": "moderately bullish",
        "overlapping lower": "moderately bearish", "unclassified": None}
OUTER_IN_MAP = ("M", "Y")


def floor(h, l, c) -> dict:
    p = (h + l + c) / 3
    r1, s1 = 2 * p - l, 2 * p - h
    r2, s2 = p + (h - l), p - (h - l)
    r3, s3 = r1 + (h - l), s1 - (h - l)
    return dict(P=p, R1=r1, R2=r2, R3=r3, R4=r3 + (r2 - r1), S1=s1, S2=s2, S3=s3, S4=s3 - (s1 - s2))


def cpr(h, l, c) -> dict:
    p, bc = (h + l + c) / 3, (h + l) / 2
    tc = (p - bc) + p
    lo, hi = min(bc, tc), max(bc, tc)
    return dict(P=p, BC=lo, TC=hi, width_pct=(hi - lo) / p * 100)


def camarilla(h, l, c) -> dict:
    r = h - l
    out = {}
    for n, f in ((1, 12), (2, 6), (3, 4), (4, 2)):
        out[f"H{n}"], out[f"L{n}"] = c + r * 1.1 / f, c - r * 1.1 / f
    out["H5"] = h / l * c
    out["L5"] = c - (out["H5"] - c)
    out["width_pct"] = (out["H3"] - out["L3"]) / c * 100
    return out


def pctile(cur: float, prev: np.ndarray) -> Optional[float]:
    prev = prev[~np.isnan(prev)][-WINDOW:]
    if len(prev) < MIN_HIST:
        return None
    return float(((prev < cur).sum() + 0.5 * (prev == cur).sum()) / len(prev))


def reading(p: Optional[float]) -> Optional[str]:
    if p is None:
        return None
    return "narrow" if p <= NARROW else "wide" if p >= WIDE else "average"


def relationship(lo, hi, plo, phi) -> str:
    """Ochoa's seven two-period relationships (Ch. 6, Table 6.2), the first that holds."""
    pw = phi - plo
    if abs(lo - plo) <= UNCHANGED_TOL * pw and abs(hi - phi) <= UNCHANGED_TOL * pw:
        return "unchanged"
    if lo > phi:
        return "higher value"
    if hi < plo:
        return "lower value"
    if hi > phi and lo < plo:
        return "outside"
    if hi < phi and lo > plo:
        return "inside"
    if hi > phi and plo <= lo <= phi:
        return "overlapping higher"
    if lo < plo and plo <= hi <= phi:
        return "overlapping lower"
    return "unclassified"


def _r(x):
    return None if x is None else round(float(x), 2)


def period_pivots(bars: pd.DataFrame, tf: str) -> Optional[dict]:
    """Pivots for the period after the last completed `tf` bar, with their readings."""
    n = len(bars)
    if n == 0:
        return None
    h, l, c = (bars[x].to_numpy(float) for x in ("h", "l", "c"))
    cprs = [cpr(h[j], l[j], c[j]) for j in range(n)]
    cams = [camarilla(h[j], l[j], c[j]) for j in range(n)]
    cw = np.array([x["width_pct"] for x in cprs])
    kw = np.array([x["width_pct"] for x in cams])
    j = n - 1
    fl, cp, cm = floor(h[j], l[j], c[j]), cprs[j], cams[j]
    cp_p, cm_p = pctile(cw[j], cw[:j]), pctile(kw[j], kw[:j])
    out = dict(tf=tf, from_period=bars["period"].iat[j], H=_r(h[j]), L=_r(l[j]), C=_r(c[j]),
               note="quarterly pivots are not Ochoa's (v1 backdrop)" if tf == "Q" else None,
               floor={k: _r(v) for k, v in fl.items()},
               cpr=dict(P=_r(cp["P"]), BC=_r(cp["BC"]), TC=_r(cp["TC"]), width_pct=round(cp["width_pct"], 3),
                        width_pctile=None if cp_p is None else round(cp_p, 2), width=reading(cp_p)),
               camarilla={**{k: _r(v) for k, v in cm.items() if k != "width_pct"},
                          "width_pct": round(cm["width_pct"], 3),
                          "width_pctile": None if cm_p is None else round(cm_p, 2), "width": reading(cm_p)},
               close_half="upper" if c[j] > (h[j] + l[j]) / 2 else "lower" if c[j] < (h[j] + l[j]) / 2 else "middle")
    if j >= 1:
        pc, pk = cprs[j - 1], cams[j - 1]
        rel = relationship(cp["BC"], cp["TC"], pc["BC"], pc["TC"])
        out["cpr"].update(relationship=rel, bias=BIAS[rel],
                          width_ratio_prev=round(cw[j] / cw[j - 1], 2) if cw[j - 1] > 0 else None)
        krel = relationship(cm["L3"], cm["H3"], pk["L3"], pk["H3"])
        out["camarilla"].update(relationship=krel, bias=BIAS[krel])
        out["close_vs_cpr_in_force"] = ("above TC" if c[j] > pc["TC"] else "below BC" if c[j] < pc["BC"]
                                        else "inside")
    if tf in ("W", "M"):
        out["cpr_trend"] = cpr_trend(bars, cprs)
    out["levels"] = levels(out, tf)
    return out


def cpr_trend(bars: pd.DataFrame, cprs: list[dict]) -> dict:
    c = bars["c"].to_numpy(float)
    st = [None] + ["above" if c[j] > cprs[j - 1]["TC"] else "below" if c[j] < cprs[j - 1]["BC"] else "inside"
                   for j in range(1, len(c))]
    last = st[-1]
    run = 0
    if last in ("above", "below"):
        for s in reversed(st):
            if s != last:
                break
            run += 1
    def last_of(x):
        idx = [j for j, s in enumerate(st) if s == x]
        return bars["period"].iat[idx[-1]] if idx else None
    return dict(side=last, run=run, last_above=last_of("above"), last_below=last_of("below"))


def levels(pv: dict, tf: str) -> list[dict]:
    """Every pivot price with its name and whether it is a map level (§4)."""
    out = []
    def add(name, price, in_map, kind):
        out.append(dict(name=name, price=price, tf=tf, kind=kind, family="pivot", in_map=in_map))
    for k in ("P", "R1", "R2", "S1", "S2"):
        add(k, pv["floor"][k], True, "floor")
    for k in ("R3", "R4", "S3", "S4"):
        add(k, pv["floor"][k], tf in OUTER_IN_MAP, "floor")
    add("TC", pv["cpr"]["TC"], True, "cpr")
    add("BC", pv["cpr"]["BC"], True, "cpr")
    cm = pv["camarilla"]
    for k in ("H3", "H4", "L3", "L4"):
        add(k, cm[k], True, "camarilla")
    for k in ("H5", "L5"):
        add(k, cm[k], False, "camarilla")
    if cm.get("width") == "wide":                       # Ochoa's hidden layers (Ch. 8)
        for k in ("H1", "H2", "L1", "L2"):
            add(k, cm[k], False, "camarilla")
    add("prev H", pv["H"], True, "range")
    add("prev L", pv["L"], True, "range")
    return out


def all_pivots(period_bars: dict[str, pd.DataFrame]) -> dict:
    return {tf: period_pivots(period_bars[tf], tf) for tf in PERIODS if tf in period_bars}


def nearest_levels(pivots: dict, price: float, n: int = 3) -> tuple[list[dict], list[dict]]:
    lv = [x for p in pivots.values() if p for x in p["levels"] if x["in_map"]]
    below = sorted([x for x in lv if x["price"] <= price], key=lambda x: price - x["price"])
    above = sorted([x for x in lv if x["price"] > price], key=lambda x: x["price"] - price)
    return below[:n], above[:n]


def lines(pivots: dict, price: Optional[float]) -> list[str]:
    out = []
    parts = []
    for tf in PERIODS:
        p = pivots.get(tf)
        if not p:
            continue
        c = p["cpr"]
        w = f", {c['width']}" if c.get("width") else ""
        rel = f", {c['relationship']}" + (f" ({c['bias']})" if c.get("bias") else "") if c.get("relationship") else ""
        tr = p.get("cpr_trend")
        trs = f", closes {tr['side']} x{tr['run']}" if tr and tr["run"] else ""
        parts.append(f"{tf}{'*' if tf == 'Q' else ''} P {c['P']:g} CPR {c['BC']:g}-{c['TC']:g}{w}{rel}{trs}")
    if parts:
        out.append("     pivots (untested; *Q not Ochoa): " + "; ".join(parts))
    if price is not None and pivots:
        below, above = nearest_levels(pivots, price)
        f = (lambda xs: "; ".join(f"{x['tf']} {x['name']} {x['price']:g}" for x in xs) or "none")
        out.append(f"     pivot levels below: {f(below)} | above: {f(above)}")
    return out
