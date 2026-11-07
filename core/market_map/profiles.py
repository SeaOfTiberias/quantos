"""
L1 profiles from daily bars (sprint plan S5, slice 5a; docs/MARKET_MAP_DEFINITIONS.md v1
§4 "Two profiles per period" and "Virgin money-zone levels", and §5): month, quarter and
year profiles, their virgin levels, and the long 250/750-session composite. The weekly
profile (slice 5b) is built from 5-minute bars, as below.

Week (§4, Ochoa's own method): money-zone TPOs from 30-minute brackets (from 09:15 IST) of
5-minute bars, the VPOC from 5-minute volume. A week gets a profile only when every session
the daily store holds for it has 5-minute bars (v1's own rule: a partial week would give a
lopsided profile); Fyers' 5-minute history starts 2017-12-01.

Two profiles per period (§4):
  money zone (Ochoa's, price-based): one TPO per daily bar at every bucket it traded. This
      is v1's own adaptation for month, quarter and year (the book builds TPOs from
      30-minute brackets); quarterly and yearly money zones are v1's extension, not Ochoa's.
      POC = the bucket with the most TPOs, a tie going to the one nearest the middle of the
      period's range; value area grows from the POC toward the heavier neighbour to 70%.
  volume profile (VPOC): each bar's volume spread evenly over its buckets; POC and 70%
      value area by the existing `value_area` rule (core/price_map/levels.py).
Width and the two-period relationship use the money-zone value area; the same two figures
are recorded for the volume value area. The VPOC relationship is recorded for the month
(§4 names week and month; the week comes in 5b).

Virgin levels (§4): a period's POC, VAH and VAL, of each kind, are virgin from the period's
close until a later daily bar trades through them (its low-high range spans the level);
that bar retires the level and its date is recorded. Every virgin level carries its age in
periods and distance in ATR(D); the POC and whichever of VAH/VAL is nearest the price are
flagged `watch` (the two Ochoa watches).

Long composite (§5): the last 250 and 750 sessions, labelled "approximation (daily
bars)". HVN shelves by the existing `shelves` rule; LVN = runs of buckets below 0.5x the
median lying between two HVN shelves.

Choices v1 leaves open, fixed here before any golden-set chart:
  - Bucket size = step_for(ATR(D)) at each period's own last bar (the long profiles: at
    the read). A level is its bucket's floor, as in the existing map.
  - LVN: buckets inside the range with no trade count as zero; the median is the one the
    shelf rule uses (traded buckets).
  - A gap over a virgin level doesn't retire it; only a bar that spans it does.
  - Volume VPOC "unchanged": within 10% of the previous volume value-area width.

Families (§6): POC/VAL/VAH, virgin levels and HVN shelves are "volume"; LVN edges are
"imbalance". Untested; recorded and shown only.
"""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Optional

import numpy as np
import pandas as pd

from core.market_map import pivots as pv
from core.market_map import structure as st
from core.price_map.build import step_for
from core.price_map.levels import SHELF_X, VALUE_SHARE, profile, shelves, value_area

PERIODS = ("W", "M", "Q", "Y")
BRACKET_MIN = 30
LONG = (250, 750)
LVN_X = 0.5
APPROX = "approximation (daily bars)"


def _bars(d: pd.DataFrame) -> list:
    return [SimpleNamespace(low=r.l, high=r.h, volume=r.vol) for r in d.itertuples(index=False)]


def spread(lo: np.ndarray, hi: np.ndarray, w: np.ndarray, step: float) -> dict:
    """Bucket floor -> sum of each bar's weight spread evenly over the buckets it traded;
    the same buckets and split as core.price_map.levels.profile, without the Python loop."""
    if len(lo) == 0:
        return {}
    a = np.floor_divide(lo, step).astype(np.int64)
    b = np.floor_divide(hi, step).astype(np.int64)
    k0 = int(a.min())
    per = w / (b - a + 1)
    acc = np.zeros(int(b.max()) - k0 + 2)
    np.add.at(acc, a - k0, per)
    np.add.at(acc, b - k0 + 1, -per)
    vals = np.cumsum(acc)[:-1]
    cover = np.zeros(len(acc))
    np.add.at(cover, a - k0, 1)
    np.add.at(cover, b - k0 + 1, -1)
    hit = np.cumsum(cover)[:-1] > 0
    idx = np.nonzero(hit)[0]
    return dict(zip(np.round((k0 + idx) * step, 2).tolist(), vals[idx].tolist()))


def vol_profile(d: pd.DataFrame, step: float) -> dict:
    return spread(d["l"].to_numpy(float), d["h"].to_numpy(float), d["vol"].to_numpy(float), step)


def tpo(d: pd.DataFrame, step: float) -> dict:
    """One TPO per daily bar at every bucket it traded (bucket floor -> count)."""
    lo, hi = d["l"].to_numpy(float), d["h"].to_numpy(float)
    a = np.floor_divide(lo, step)
    b = np.floor_divide(hi, step)
    h = spread(lo, hi, (b - a + 1).astype(float), step)
    return dict(zip(h.keys(), np.rint(np.fromiter(h.values(), float, len(h))).tolist()))


def money_zone(h: dict, mid: float, step: float, share: float = VALUE_SHARE) -> Optional[tuple]:
    """(POC, VAL, VAH) of a TPO profile; a POC tie goes to the bucket nearest `mid`."""
    if not h:
        return None
    ks = sorted(h)
    top = max(h.values())
    poc = min((k for k in ks if h[k] == top), key=lambda k: (abs(k + step / 2 - mid), k))
    tot = sum(h.values())
    i = j = ks.index(poc)
    acc = h[poc]
    while acc < share * tot and (i > 0 or j < len(ks) - 1):
        up = h[ks[j + 1]] if j + 1 < len(ks) else -1
        dn = h[ks[i - 1]] if i > 0 else -1
        if up >= dn:
            j += 1
            acc += up
        else:
            i -= 1
            acc += dn
    return poc, ks[i], ks[j]


def period_profiles(daily: pd.DataFrame, tf: str, as_of) -> list[dict]:
    """Both profiles for every `tf` period completed before `as_of`, oldest first."""
    d = daily[daily["date"] < pd.Timestamp(as_of)].reset_index(drop=True)
    if d.empty:
        return []
    atr_d = st.atr(d)
    per = st._period(d["date"], tf)
    cur = st.period_of(as_of, tf)
    out = []
    for p, idx in d.groupby(per, sort=False).indices.items():
        if p == cur:
            continue
        g = d.iloc[idx]
        a = atr_d[idx[-1]]
        if np.isnan(a) or a <= 0:
            continue
        step = step_for(float(a))
        hi, lo = float(g["h"].max()), float(g["l"].min())
        mz = money_zone(tpo(g, step), (hi + lo) / 2, step)
        vp = value_area(vol_profile(g, step))
        if not mz or not vp:
            continue
        out.append(dict(tf=tf, period=p, end_i=int(idx[-1]), step=step,
                        mz=dict(POC=mz[0], VAL=mz[1], VAH=mz[2]), vol=dict(POC=vp[0], VAL=vp[1], VAH=vp[2])))
    return out


def brackets(m5: pd.DataFrame) -> pd.DataFrame:
    """30-minute brackets from 09:15 IST (Ochoa's TPO segments, Ch. 3): one row per
    session and bracket with its high and low."""
    mins = ((m5["dt"].dt.hour * 60 + m5["dt"].dt.minute - (9 * 60 + 15)) // BRACKET_MIN).rename("bracket")
    g = m5.groupby([m5["date"], mins], sort=True).agg(h=("h", "max"), l=("l", "min"))
    return g.reset_index()


def weekly_profiles(daily: pd.DataFrame, m5: Optional[pd.DataFrame], as_of) -> list[dict]:
    """§4 weekly money zone (TPOs from 30-minute brackets of 5-minute bars) and weekly VPOC
    (5-minute volume), for every completed week whose sessions all have 5-minute bars."""
    if m5 is None or m5.empty:
        return []
    d = daily[daily["date"] < pd.Timestamp(as_of)].reset_index(drop=True)
    if d.empty:
        return []
    atr_d = st.atr(d)
    cur = st.period_of(as_of, "W")
    m5 = m5[m5["date"] < pd.Timestamp(as_of)].sort_values("dt")
    br = brackets(m5)                                  # sorted by date, then bracket
    md, bd = m5["date"].to_numpy(), br["date"].to_numpy()
    ml, mh, mv = (m5[x].to_numpy(float) for x in ("l", "h", "vol"))
    bl, bh = br["l"].to_numpy(float), br["h"].to_numpy(float)
    have = set(np.unique(md).tolist())
    out = []
    for p, idx in d.groupby(st._period(d["date"], "W"), sort=False).indices.items():
        if p == cur:
            continue
        days = d["date"].to_numpy()[idx]
        if any(x not in have for x in days.tolist()):
            continue                                   # 5-minute bars missing for a session
        a = atr_d[idx[-1]]
        if np.isnan(a) or a <= 0:
            continue
        step = step_for(float(a))
        i0, i1 = np.searchsorted(md, days[0], "left"), np.searchsorted(md, days[-1], "right")
        j0, j1 = np.searchsorted(bd, days[0], "left"), np.searchsorted(bd, days[-1], "right")
        lo, hi = float(ml[i0:i1].min()), float(mh[i0:i1].max())
        t = spread(bl[j0:j1], bh[j0:j1], (np.floor_divide(bh[j0:j1], step) - np.floor_divide(bl[j0:j1], step) + 1),
                   step)
        mz = money_zone({k: round(v) for k, v in t.items()}, (hi + lo) / 2, step)
        vp = value_area(spread(ml[i0:i1], mh[i0:i1], mv[i0:i1], step))
        if not mz or not vp:
            continue
        out.append(dict(tf="W", period=p, end_i=int(idx[-1]), step=step,
                        mz=dict(POC=mz[0], VAL=mz[1], VAH=mz[2]), vol=dict(POC=vp[0], VAL=vp[1], VAH=vp[2])))
    return out


def _va_reading(profs: list[dict], kind: str) -> dict:
    cur = profs[-1][kind]
    w = np.array([(p[kind]["VAH"] - p[kind]["VAL"]) / p[kind]["POC"] * 100 if p[kind]["POC"] else np.nan
                  for p in profs])
    pc = pv.pctile(w[-1], w[:-1])
    out = dict(cur, width_pct=round(float(w[-1]), 3), width_pctile=None if pc is None else round(pc, 2),
               width=pv.reading(pc))
    if len(profs) >= 2:
        prev = profs[-2][kind]
        rel = pv.relationship(cur["VAL"], cur["VAH"], prev["VAL"], prev["VAH"])
        out.update(relationship=rel, bias=pv.BIAS[rel])
    return out


def vpoc_relationship(profs: list[dict]) -> Optional[dict]:
    """§4 VPOC relationship: unchanged (within 10% of the previous volume VA width), higher
    or lower, and the run of unchanged periods ending with the last one."""
    def rel(a, b):
        tol = pv.UNCHANGED_TOL * (b["VAH"] - b["VAL"])
        return "unchanged" if abs(a["POC"] - b["POC"]) <= tol else "higher" if a["POC"] > b["POC"] else "lower"
    if len(profs) < 2:
        return None
    rels = [rel(profs[j]["vol"], profs[j - 1]["vol"]) for j in range(1, len(profs))]
    run = 0
    for r in reversed(rels):
        if r != "unchanged":
            break
        run += 1
    return dict(relationship=rels[-1], unchanged_run=run)


def virgin_levels(daily: pd.DataFrame, profs: list[dict], as_of, price: Optional[float],
                  atr_now: Optional[float]) -> list[dict]:
    """Every period's POC/VAH/VAL of each kind with its fate: virgin, or filled on a date."""
    d = daily[daily["date"] < pd.Timestamp(as_of)].reset_index(drop=True)
    lo, hi = d["l"].to_numpy(float), d["h"].to_numpy(float)
    dates = d["date"]
    out = []
    n = len(profs)
    for k, p in enumerate(profs):
        s = p["end_i"] + 1
        for kind, label in (("mz", "money zone"), ("vol", "volume")):
            rows = []
            for name in ("POC", "VAH", "VAL"):
                x = p[kind][name]
                hit = np.nonzero((lo[s:] <= x) & (hi[s:] >= x))[0]
                rows.append(dict(tf=p["tf"], period=p["period"], kind=label, name=name, price=x,
                                 family="volume", age_periods=n - k,
                                 filled=dates.iat[s + int(hit[0])].date().isoformat() if len(hit) else None,
                                 distance_atr=round(abs(x - price) / atr_now, 2) if price and atr_now else None,
                                 watch=False))
            virgin = [r for r in rows if r["filled"] is None]
            for r in virgin:
                if r["name"] == "POC":
                    r["watch"] = True
            edges = [r for r in virgin if r["name"] != "POC"]
            if edges and price is not None:
                min(edges, key=lambda r: abs(r["price"] - price))["watch"] = True
            out += rows
    return out


def long_profile(daily: pd.DataFrame, as_of, n: int, atr_now: float) -> Optional[dict]:
    d = daily[daily["date"] < pd.Timestamp(as_of)].tail(n)
    if len(d) < n or not atr_now:
        return None
    step = step_for(atr_now)
    h = vol_profile(d, step)
    va = value_area(h)
    hvn = shelves(h, step, SHELF_X)
    vals = sorted(h.values())
    med = vals[len(vals) // 2]
    ks = [round(k * step, 2) for k in range(int(min(h) / step + 0.5), int(max(h) / step + 0.5) + 1)]
    lvn, run = [], []
    for k in ks:
        if h.get(k, 0.0) < LVN_X * med:
            run.append(k)
        elif run:
            lvn.append((run[0], run[-1] + step))
            run = []
    lvn = [(a, b) for a, b in lvn if any(s[1] <= a + 1e-9 for s in hvn) and any(s[0] >= b - 1e-9 for s in hvn)]
    return dict(sessions=n, label=APPROX, step=step, POC=va[0], VAL=va[1], VAH=va[2],
                from_date=d["date"].iat[0].date().isoformat(),
                hvn=[dict(lo=a, hi=b, family="volume") for a, b in hvn],
                lvn=[dict(lo=a, hi=b, family="imbalance") for a, b in lvn])


def read(daily: pd.DataFrame, as_of, price: Optional[float], m5: Optional[pd.DataFrame] = None) -> dict:
    """The profile part of the L1 read. `m5` = adjusted 5-minute bars (M5Store.adjusted);
    without them there is no weekly profile."""
    d = daily[daily["date"] < pd.Timestamp(as_of)].reset_index(drop=True)
    a = st.atr(d) if len(d) else np.array([])
    atr_now = float(a[-1]) if len(a) and not np.isnan(a[-1]) else None
    periods, virgins = {}, []
    for tf in PERIODS:
        profs = weekly_profiles(daily, m5, as_of) if tf == "W" else period_profiles(daily, tf, as_of)
        if not profs:
            continue
        last = profs[-1]
        note = ("TPOs from 30-minute brackets of 5-minute bars (Ochoa's method)" if tf == "W" else
                "v1's own adaptation (daily-bar TPOs)" + ("; not Ochoa" if tf in ("Q", "Y") else ""))
        periods[tf] = dict(tf=tf, from_period=last["period"], step=last["step"], note=note,
                           money_zone=_va_reading(profs, "mz"), volume=_va_reading(profs, "vol"))
        if tf in ("W", "M"):
            periods[tf]["vpoc"] = vpoc_relationship(profs)
        virgins += virgin_levels(daily, profs, as_of, price, atr_now)
    return dict(periods=periods, virgin=[v for v in virgins if v["filled"] is None],
                filled_recent=[v for v in virgins if v["filled"] and v["age_periods"] <= 12 and v["tf"] in ("W", "M")],
                long={str(n): long_profile(daily, as_of, n, atr_now) for n in LONG})


def lines(pr: dict, price: Optional[float]) -> list[str]:
    out = []
    parts = []
    for tf in PERIODS:
        p = pr["periods"].get(tf)
        if not p:
            continue
        m, v = p["money_zone"], p["volume"]
        rel = f", {m['relationship']}" if m.get("relationship") else ""
        w = f", {m['width']}" if m.get("width") else ""
        parts.append(f"{tf}{'*' if tf in ('Q', 'Y') else ''} MZ POC {m['POC']:g} VA {m['VAL']:g}-{m['VAH']:g}{w}{rel}"
                     f" / VPOC {v['POC']:g}")
    if parts:
        out.append("     profiles (untested; W from 5-min, M/Q/Y daily-bar TPOs, *not Ochoa): " + "; ".join(parts))
    w = [x for x in pr["virgin"] if x["watch"]]
    if w and price is not None:
        w.sort(key=lambda x: abs(x["price"] - price))
        out.append("     virgin (watch): " + "; ".join(
            f"{x['tf']} {x['period']} {'MZ' if x['kind'] == 'money zone' else 'vol'} {x['name']} {x['price']:g}"
            f" ({x['distance_atr']:g} ATR)" for x in w[:4]))
    lp = [p for p in pr["long"].values() if p]
    if lp:
        out.append(f"     long profile ({APPROX}): " + "; ".join(
            f"{p['sessions']}d POC {p['POC']:g} VA {p['VAL']:g}-{p['VAH']:g}, {len(p['hvn'])} HVN, {len(p['lvn'])} LVN"
            for p in lp))
    return out
