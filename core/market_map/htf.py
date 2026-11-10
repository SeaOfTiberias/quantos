"""
HTF zones: L1 elements clustered by family (sprint plan S5, slice 6; definitions v1 §6 and
§6.1, as amended by v2 G2, docs/MARKET_MAP_DEFINITIONS_V2.md).

v2 G2 (2026-11-11): structure swings enter only while no close has gone beyond them;
virgin profile levels only when flagged `watch`; bands (demand, supply, order blocks,
HVN and LVN runs) keep their whole range and are never split; a strong zone needs 2+
families, at least one of them structure, imbalance or liquidity.

Elements (every one keeps its timeframe, family, kind and period, so the signal test can
score each family on its own):
  structure  zig-zag swing highs and lows (§1, W and M), protected and weak levels (§2),
             multi-touch levels (§3.2, W)
  imbalance  demand/supply zones (§3.1) and order blocks (§3.3) still valid, LVN edges (§5)
  liquidity  active EQH / EQL (§3.4)
  volume     money zone and VPOC POC/VAL/VAH of the current periods, virgin levels (§4),
             long-profile POC/VAL/VAH and HVN shelf edges (§5)
  pivot      every §4 pivot level marked in_map (week, month, quarter, year)

Choices v1 leaves open, fixed here before any golden-set chart:
  - §6's "levels and bands from M and W" is read as all L1 periods: §4 puts yearly R3/S3
    and the quarterly and yearly pivots into clustering explicitly.
  - Point levels cluster by the existing map's rule (core/price_map/levels.zones) at the
    weekly scale: a level within 0.3 ATR(W) of the cluster's last level joins it while the
    cluster stays within 1.5x that. (v1 entered bands as their two edges; v2 G2 replaced it.)
  - v2 G2 bands: overlapping bands merge into one zone (their union). A point cluster lying
    within 0.3 ATR(W) of a band zone joins the nearest such band zone (the one whose range
    is closest to the cluster's middle); band zones are never merged through a point
    cluster. A zone's range is the union of its members.
  - A strong zone has members from at least 2 families, one of them structure, imbalance
    or liquidity (v2 G2). Price-based and volume-based profile levels are one family.
  - Hot zones (§6.1): the same clustering over the §4 levels only (pivots, money zones,
    VPOCs and their virgin levels). A DPZ is a cluster with two members of different
    formulas (floor incl. CPR, Camarilla, range, money zone, VPOC) or different periods;
    it is also an MTZ when its members come from two or more periods. A GPZ is a
    Camarilla H3/L3 or money-zone/VPOC level inside its own period's CPR.

Untested: no fidelity test (§9) has run. Zones describe the chart; they are not signals.
"""

from __future__ import annotations

from typing import Optional

HTF_ATR = 0.3                 # §6 tolerance, in ATR(W)
CAP = 1.5                     # the existing map's no-chaining cap
FAMILIES = ("structure", "imbalance", "liquidity", "volume", "pivot")
PRICE_ACTION = ("structure", "imbalance", "liquidity")         # v2 G2: a strong zone needs one of these
RULE = "clustered at 0.3 ATR(W); point clusters at most 0.45 ATR(W); bands keep their full range"
SOURCE = "L1: NSE bhavcopy daily (adjusted), Fyers 5-minute for the weekly profile"


def _e(price, family, tf, kind, label, period=None, formula=None):
    return dict(price=round(float(price), 2), family=family, tf=tf, kind=kind, label=label,
                period=period, formula=formula)


def _band(lo, hi, family, tf, kind, label, period=None):
    """A band element (v2 G2): its whole range, never split."""
    e = _e(lo, family, tf, kind, label, period)
    e.update(lo=round(float(lo), 2), hi=round(float(hi), 2), band=True)
    return e


def elements(l1: dict, swings: dict) -> list[dict]:
    """Every L1 element, a point or a band. `swings` = {tf: [(kind, label, price, period)]}:
    the zig-zag swings of W and M that no close has gone beyond (v2 G2)."""
    out = []
    for tf, sw in swings.items():
        for kind, label, price, period in sw:
            out.append(_e(price, "structure", tf, "swing", f"{tf} swing {label or kind} {period}", period))
    for tf in ("M", "W"):
        s = l1["tf"].get(tf, {})
        for key in ("protected", "weak"):
            x = s.get(key)
            if x:
                out.append(_e(x["price"], "structure", tf, key, f"{tf} {key} {x['period']}", x["period"]))
    for z in l1.get("zones", []):
        tf = z["tf"]
        if z["kind"] == "multi_touch":
            out.append(_e(z["level"], "structure", tf, "multi_touch", f"{tf} multi-touch x{z['touches']}", z["last"]))
        elif z["kind"] in ("EQH", "EQL"):
            if z["status"] == "active":
                out.append(_e(z["level"], "liquidity", tf, z["kind"], f"{tf} {z['kind']}", z["swings"][-1]))
        else:                                           # demand / supply / order blocks: one band (v2 G2)
            name = {"demand": "demand", "supply": "supply", "bull_ob": "bull OB", "bear_ob": "bear OB"}[z["kind"]]
            per = z.get("departed") or z.get("bar")
            out.append(_band(z["lo"], z["hi"], "imbalance", tf, z["kind"],
                             f"{tf} {name} {z['lo']:g}-{z['hi']:g} ({per})", per))
    for tf, p in (l1.get("pivots") or {}).items():
        if not p:
            continue
        for lv in p["levels"]:
            if lv["in_map"]:
                formula = {"floor": "floor", "cpr": "floor", "camarilla": "camarilla", "range": "range"}[lv["kind"]]
                out.append(_e(lv["price"], "pivot", tf, lv["kind"], f"{tf} {lv['name']}", p["from_period"], formula))
    pr = l1.get("profiles") or {}
    for tf, p in (pr.get("periods") or {}).items():
        for kind, formula, tag in (("money_zone", "money zone", "MZ"), ("volume", "VPOC", "vol")):
            for n in ("POC", "VAL", "VAH"):
                out.append(_e(p[kind][n], "volume", tf, kind, f"{tf} {tag} {n} {p['from_period']}", p["from_period"],
                              formula))
    for v in [x for x in pr.get("virgin") or [] if x.get("watch")]:      # v2 G2: Ochoa's two watches only
        formula = "money zone" if v["kind"] == "money zone" else "VPOC"
        tag = "MZ" if formula == "money zone" else "vol"
        out.append(_e(v["price"], "volume", v["tf"], "virgin", f"{v['tf']} virgin {tag} {v['name']} {v['period']}",
                      v["period"], formula))
    for n, lp in (pr.get("long") or {}).items():
        if not lp:
            continue
        for k in ("POC", "VAL", "VAH"):
            out.append(_e(lp[k], "volume", f"{n}d", "long", f"{n}d {k} (approx.)"))
        for s in lp["hvn"]:
            out.append(_band(s["lo"], s["hi"], "volume", f"{n}d", "hvn", f"{n}d HVN {s['lo']:g}-{s['hi']:g} (approx.)"))
        for s in lp["lvn"]:
            out.append(_band(s["lo"], s["hi"], "imbalance", f"{n}d", "lvn",
                             f"{n}d LVN {s['lo']:g}-{s['hi']:g} (approx.)"))
    return out


def _finish(z: dict) -> dict:
    fams = sorted({m["family"] for m in z["members"]}, key=FAMILIES.index)
    z.update(families=fams, strong=len(fams) >= 2 and any(f in PRICE_ACTION for f in fams),
             mid=round((z["low"] + z["high"]) / 2, 2), tfs=sorted({m["tf"] for m in z["members"]}))
    return z


def cluster(els: list[dict], width: float) -> list[dict]:
    """v2 G2: point levels by the existing map's rule (price_map.levels.zones); bands keep
    their range, overlapping bands merge, and a point cluster within `width` of a band zone
    joins the nearest one."""
    pts: list[dict] = []
    for e in sorted((x for x in els if not x.get("band")), key=lambda x: x["price"]):
        if pts and e["price"] - pts[-1]["members"][-1]["price"] <= width and e["price"] - pts[-1]["low"] <= CAP * width:
            pts[-1]["members"].append(e)
            pts[-1]["high"] = e["price"]
        else:
            pts.append(dict(low=e["price"], high=e["price"], members=[e]))
    bands: list[dict] = []
    for e in sorted((x for x in els if x.get("band")), key=lambda x: (x["lo"], x["hi"])):
        if bands and e["lo"] <= bands[-1]["high"]:
            bands[-1]["members"].append(e)
            bands[-1]["high"] = max(bands[-1]["high"], e["hi"])
        else:
            bands.append(dict(low=e["lo"], high=e["hi"], members=[e]))
    core = [(b["low"], b["high"]) for b in bands]
    out = []
    for z in pts:
        mid = (z["low"] + z["high"]) / 2
        near = [j for j, (lo, hi) in enumerate(core) if z["low"] <= hi + width and z["high"] >= lo - width]
        if not near:
            out.append(z)
            continue
        j = min(near, key=lambda j: max(core[j][0] - mid, 0, mid - core[j][1]))
        bands[j]["members"] += z["members"]
        bands[j]["low"], bands[j]["high"] = min(bands[j]["low"], z["low"]), max(bands[j]["high"], z["high"])
    out += bands
    return [_finish(z) for z in sorted(out, key=lambda z: (z["low"], z["high"]))]


def htf_zones(els: list[dict], atr_w: Optional[float]) -> list[dict]:
    if not atr_w:
        return []
    return cluster(els, HTF_ATR * atr_w)


def hot_zones(els: list[dict], atr_w: Optional[float], l1: dict, strong: list[dict]) -> dict:
    """§6.1, recorded beside the families: DPZ / MTZ clusters of §4 levels, and GPZs."""
    out = dict(dpz=[], gpz=[])
    if atr_w:
        four = [e for e in els if e["formula"]]
        for z in cluster(four, HTF_ATR * atr_w):
            m = z["members"]
            if len(m) < 2 or (len({x["formula"] for x in m}) < 2 and len({(x["tf"], x["period"]) for x in m}) < 2):
                continue
            periods = sorted({x["tf"] for x in m})
            out["dpz"].append(dict(low=z["low"], high=z["high"], members=[x["label"] for x in m],
                                   mtz=len(periods) >= 2, periods=periods,
                                   q_not_ochoa="Q" in periods,
                                   strong_zone=any(s["low"] <= z["high"] and z["low"] <= s["high"] for s in strong)))
    pivots, prof = l1.get("pivots") or {}, (l1.get("profiles") or {}).get("periods") or {}
    for tf, p in pivots.items():
        if not p:
            continue
        bc, tc = p["cpr"]["BC"], p["cpr"]["TC"]
        cands = [("H3", p["camarilla"]["H3"], "bearish"), ("L3", p["camarilla"]["L3"], "bullish")]
        if tf in prof:
            cands += [(f"MZ {n}", prof[tf]["money_zone"][n], None) for n in ("POC", "VAL", "VAH")]
            cands += [("VPOC", prof[tf]["volume"]["POC"], None)]
        for name, px, direction in cands:
            if bc <= px <= tc:
                out["gpz"].append(dict(tf=tf, period=p["from_period"], member=name, price=px, cpr=[bc, tc],
                                       direction=direction, note="direction from the trend" if direction is None else
                                       "H3/L3 inside the CPR = a close in the outer 22.5% of the range"))
    return out


def compact(z: dict) -> dict:
    return dict(low=z["low"], high=z["high"], mid=z["mid"], strong=z["strong"], families=z["families"], tfs=z["tfs"],
                n=len(z["members"]), why=why(z))


def why(z: dict, n: int = 4) -> str:
    """The zone's members, one per family first."""
    seen, first, rest = set(), [], []
    for m in z["members"]:
        (rest if m["family"] in seen else first).append(m["label"])
        seen.add(m["family"])
    lab = first + rest
    return "; ".join(lab[:n]) + (f" +{len(lab) - n}" if len(lab) > n else "")


def nearest_strong(zs: list[dict], price: float) -> dict:
    s = [z for z in zs if z["strong"]]
    below = [z for z in s if z["high"] < price]
    above = [z for z in s if z["low"] > price]
    return dict(below=max(below, key=lambda z: z["high"]) if below else None,
                above=min(above, key=lambda z: z["low"]) if above else None,
                inside=next((z for z in s if z["low"] <= price <= z["high"]), None))
