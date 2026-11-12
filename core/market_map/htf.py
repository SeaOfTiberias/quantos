"""
HTF zones: L1 elements clustered by family (sprint plan S5, slice 6; definitions v1 §6 and
§6.1, as amended by v2 G2 rev 1, docs/MARKET_MAP_DEFINITIONS_V2.md).

v2 G2 (2026-11-11): structure swings enter only while no close has gone beyond them;
virgin profile levels only when flagged `watch`; demand, supply and order-block bands keep
their whole range, are never split and never merge with each other; a strong zone needs 2+
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
  - v2 G2 rev 1 bands: demand, supply and order-block zones enter whole and are never
    split; bands never merge with each other (overlapping bands stay separate zones, as on
    a chart). A point cluster lying within 0.3 ATR(W) of a band joins the nearest band (the
    one whose range is closest to the cluster's middle); when several are equally near (the
    cluster's middle lies inside overlapping bands), it joins each of them. A zone's range
    is the union of its members. HVN and LVN shelves enter as their two edges, as in v1.
  - A strong zone has members from at least 2 families, one of them structure, imbalance
    or liquidity (v2 G2). Price-based and volume-based profile levels are one family.
  - Hot zones (§6.1): the same clustering over the §4 levels only (pivots, money zones,
    VPOCs and their virgin levels). A DPZ is a cluster with two members of different
    formulas (floor incl. CPR, Camarilla, range, money zone, VPOC) or different periods;
    it is also an MTZ when its members come from two or more periods. A GPZ is a
    Camarilla H3/L3 or money-zone/VPOC level inside its own period's CPR.

v3 (docs/MARKET_MAP_DEFINITIONS_V3.md, 2026-11-13) supersedes the v2 strong rule above:
  H1  Only structure, imbalance and liquidity elements form zones. Pivot and volume
      elements are the levels layer: they never create or widen a zone, and they serve the
      confluence check. LVN edges move from imbalance to volume.
  H2  Bands arrive here already mitigated on daily bars (zones.mitigate); a band touched
      once is labelled "tested once".
  H3  A zone is strong when one of its bands is at a break (an order block, or a §3.1
      zone with a same-direction BOS/CHoCH in its departure window) AND fresh (no touch),
      AND a levels-layer element lies inside it or within 0.3 ATR(W) of an edge. If several
      bands qualify only one is needed.
  H4  coverage(): the share of price +/- 3 ATR(W) inside at least one zone (and strong
      zone); reported, never used to set a parameter.
  H5  Fair-value gaps enter as imbalance bands (zones.fvgs, trimmed by zones.mitigate);
      they are never "at a break".

Untested: no fidelity test (§9) has run. Zones describe the chart; they are not signals.
"""

from __future__ import annotations

from typing import Optional

HTF_ATR = 0.3                 # §6 tolerance, in ATR(W)
CAP = 1.5                     # the existing map's no-chaining cap
FAMILIES = ("structure", "imbalance", "liquidity", "volume", "pivot")
PRICE_ACTION = ("structure", "imbalance", "liquidity")         # v3 H1: only these form zones
LEVELS = ("volume", "pivot")                                    # v3 H1: the levels layer
COVER_ATR = 3.0                                                 # v3 H4: window, in ATR(W) each side
RULE = ("price-action zones only (pivots and volume are levels); clustered at 0.3 ATR(W); point clusters at most "
        "0.45 ATR(W); bands keep their full range; used bands removed (v3)")
STRONG_RULE = "strong = a fresh order block or base at a BOS/CHoCH, with a pivot or volume level within 0.3 ATR(W)"
BAND_NAMES = {"demand": "demand", "supply": "supply", "bull_ob": "bull OB", "bear_ob": "bear OB",
              "bull_fvg": "bull FVG", "bear_fvg": "bear FVG"}
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
        else:                                           # demand / supply / order blocks / FVGs: one band
            per = z.get("departed") or z.get("bar")
            tag = " tested once" if z.get("tested_once") else ""
            e = _band(z["lo"], z["hi"], "imbalance", tf, z["kind"],
                      f"{tf} {BAND_NAMES[z['kind']]} {z['lo']:g}-{z['hi']:g} ({per}{tag})", per)
            e.update(at_break=bool(z.get("at_break")), fresh=bool(z.get("fresh", True)))
            out.append(e)
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
        for s in lp["hvn"]:                              # shelves: their edges (v2 G2 rev 1, as v1)
            for edge, px in (("low", s["lo"]), ("high", s["hi"])):
                out.append(_e(px, "volume", f"{n}d", "hvn", f"{n}d HVN {edge} (approx.)"))
        for s in lp["lvn"]:
            for edge, px in (("low", s["lo"]), ("high", s["hi"])):
                out.append(_e(px, "volume", f"{n}d", "lvn", f"{n}d LVN {edge} (approx.)"))   # v3 H1
    return out


def _finish(z: dict) -> dict:
    fams = sorted({m["family"] for m in z["members"]}, key=FAMILIES.index)
    z.update(families=fams, strong=False, confluence=[],
             mid=round((z["low"] + z["high"]) / 2, 2), tfs=sorted({m["tf"] for m in z["members"]}))
    return z


def cluster(els: list[dict], width: float) -> list[dict]:
    """v2 G2 rev 1: point levels by the existing map's rule (price_map.levels.zones); bands
    keep their range and never merge with each other; a point cluster within `width` of a
    band joins the nearest one."""
    pts: list[dict] = []
    for e in sorted((x for x in els if not x.get("band")), key=lambda x: x["price"]):
        if pts and e["price"] - pts[-1]["members"][-1]["price"] <= width and e["price"] - pts[-1]["low"] <= CAP * width:
            pts[-1]["members"].append(e)
            pts[-1]["high"] = e["price"]
        else:
            pts.append(dict(low=e["price"], high=e["price"], members=[e]))
    bands = [dict(low=e["lo"], high=e["hi"], members=[e])
             for e in sorted((x for x in els if x.get("band")), key=lambda x: (x["lo"], x["hi"]))]
    core = [(b["low"], b["high"]) for b in bands]
    out = []
    for z in pts:
        mid = (z["low"] + z["high"]) / 2
        near = [j for j, (lo, hi) in enumerate(core) if z["low"] <= hi + width and z["high"] >= lo - width]
        if not near:
            out.append(z)
            continue
        gap = {j: max(core[j][0] - mid, 0, mid - core[j][1]) for j in near}
        for j in [j for j in near if gap[j] == min(gap.values())]:     # a tie (inside overlapping bands): each
            bands[j]["members"] = bands[j]["members"] + z["members"]
            bands[j]["low"], bands[j]["high"] = min(bands[j]["low"], z["low"]), max(bands[j]["high"], z["high"])
    out += bands
    return [_finish(z) for z in sorted(out, key=lambda z: (z["low"], z["high"]))]


def htf_zones(els: list[dict], atr_w: Optional[float]) -> list[dict]:
    """v3: zones from price-action elements only (H1), strong by H3."""
    if not atr_w:
        return []
    w = HTF_ATR * atr_w
    zs = cluster([e for e in els if e["family"] in PRICE_ACTION], w)
    lv = [e for e in els if e["family"] in LEVELS]
    for z in zs:
        z["confluence"] = [e["label"] for e in lv if z["low"] - w <= e["price"] <= z["high"] + w]
        z["strong"] = bool(z["confluence"]) and any(m.get("band") and m.get("at_break") and m.get("fresh")
                                                for m in z["members"])
    return zs


def coverage(zs: list[dict], price: Optional[float], atr_w: Optional[float]) -> Optional[dict]:
    """v3 H4: the share of [price - 3 ATR(W), price + 3 ATR(W)] inside at least one zone,
    and inside at least one strong zone. A description, never a target."""
    if price is None or not atr_w:
        return None
    lo, hi = price - COVER_ATR * atr_w, price + COVER_ATR * atr_w

    def share(sel):
        iv = sorted((max(z["low"], lo), min(z["high"], hi)) for z in sel if z["high"] >= lo and z["low"] <= hi)
        tot, cur = 0.0, None
        for a, b in iv:
            if cur and a <= cur[1]:
                cur[1] = max(cur[1], b)
            else:
                if cur:
                    tot += cur[1] - cur[0]
                cur = [a, b]
        if cur:
            tot += cur[1] - cur[0]
        return round(100 * tot / (hi - lo), 1)

    near = [z for z in zs if z["high"] >= lo and z["low"] <= hi]
    return dict(window=[round(lo, 2), round(hi, 2)], pct=share(zs), strong_pct=share([z for z in zs if z["strong"]]),
                zones=len(near), strong=sum(z["strong"] for z in near))


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
                n=len(z["members"]), why=why(z),
                bands=[dict(kind=m["kind"], tf=m["tf"], lo=m["lo"], hi=m["hi"], at_break=bool(m.get("at_break")),
                            fresh=bool(m.get("fresh", True)), period=m["period"]) for m in z["members"] if m.get("band")],
                confluence=z.get("confluence", [])[:4], n_confluence=len(z.get("confluence", [])))


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
