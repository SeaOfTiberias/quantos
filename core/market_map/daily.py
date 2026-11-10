"""
L2, the stock's daily layer (sprint plan S5, slice 7b): daily pivots and session profiles
from the full 5-minute history (Fyers, from 2017-12-01), shown beside the higher-timeframe
map. Data only; untested.

Definitions v1 §8 puts daily CPR, daily Camarilla and daily virgin money-zone levels in
the intraday phase. So this layer is computed and SHOWN, but it is never clustered into the
HTF zones (§6) and never counted as a family: v1 is unchanged. The formulas are §4's.

  Daily pivots (from the last completed session's H, L, C; §4, Ch. 5-8):
    floor P, R1, R2, S1, S2 (R3/S3 shown); CPR BC/TC with its width % and Ochoa's absolute
    daily reading (narrow < 0.25%, wide > 0.75%, Pivot Range Histogram, Appendix B; §4
    says the absolute thresholds apply to the daily CPR as written); the two-day
    relationship against the previous session's CPR (Table 6.2); Camarilla H3/H4/L3/L4.
  Session profiles (one per session that has 5-minute bars), as §4's weekly profile:
    money zone from 30-minute brackets from 09:15 (TPOs), volume profile from 5-minute
    volume; POC, VAL and VAH of each kind.
  Virgin session levels (§4's rule, v2 G5): each session's POC, VAH and VAL of each kind is
    virgin once a later session has closed without trading it, until a later daily bar's
    range spans it. The last session's own levels are shown as its profile, not as virgin.
  VPOC tie (v2 G6): nearest the middle of the session's range, then the lower.

Choices v1 leaves open, fixed here before any golden-set chart:
  - Bucket size = step_for(ATR(D)) at the session (the weekly rule, per session).
  - No age cutoff (the old map kept the last 20 sessions only): every session since the
    5-minute history starts counts; the age in sessions is recorded.
  - A gap over a level doesn't retire it; only a daily bar that spans it does.
  - Shown: the VIRGIN_SHOWN nearest virgin levels on each side of the price.
  - Two-day "unchanged": §4's 10% tolerance (pivots.UNCHANGED_TOL).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from core.market_map import pivots as pv
from core.market_map import structure as st
from core.market_map.profiles import brackets, money_zone, spread
from core.price_map.build import step_for
from core.price_map.levels import bucket

UNTESTED = "untested"
NARROW, WIDE = 0.25, 0.75            # Ochoa's daily CPR width markers, % of the pivot
VIRGIN_SHOWN = 3
SOURCE = "L2: NSE bhavcopy daily (adjusted) for the pivots, Fyers 5-minute for the session profiles"
NOTE = "intraday layer (definitions v1 §8): shown beside the HTF zones, never clustered into them"


def _r(x):
    return round(float(x), 2)


def day_pivots(d: pd.DataFrame) -> Optional[dict]:
    """Pivots for the next session from the last completed one (`d` = completed daily bars)."""
    if len(d) < 2:
        return None
    last, prev = d.iloc[-1], d.iloc[-2]
    h, l, c = float(last["h"]), float(last["l"]), float(last["c"])
    f, cp, cam = pv.floor(h, l, c), pv.cpr(h, l, c), pv.camarilla(h, l, c)
    pc = pv.cpr(float(prev["h"]), float(prev["l"]), float(prev["c"]))
    w = cp["width_pct"]
    levels = [dict(name=n, price=_r(f[n]), kind="floor") for n in ("R3", "R2", "R1", "P", "S1", "S2", "S3")]
    levels += [dict(name=n, price=_r(cp[n]), kind="cpr") for n in ("TC", "BC")]
    levels += [dict(name=n, price=_r(cam[n]), kind="camarilla") for n in ("H4", "H3", "L3", "L4")]
    return dict(from_session=last["date"].date().isoformat(), H=h, L=l, C=c,
                cpr=dict(BC=_r(cp["BC"]), TC=_r(cp["TC"]), P=_r(cp["P"]), width_pct=round(w, 3),
                         reading="narrow" if w < NARROW else "wide" if w > WIDE else "average"),
                relationship=pv.relationship(cp["BC"], cp["TC"], pc["BC"], pc["TC"]),
                levels=sorted(levels, key=lambda x: -x["price"]))


def session_profiles(d: pd.DataFrame, m5: Optional[pd.DataFrame]) -> list[dict]:
    """A money zone and a volume profile for every completed session (rows of `d`) that has
    5-minute bars. `d` = completed daily bars; `m5` = adjusted 5-minute bars (dt, date, ...)."""
    if m5 is None or m5.empty or d.empty:
        return []
    last = d["date"].iat[-1]
    m5 = m5[m5["date"] <= last].sort_values("dt")
    if m5.empty:
        return []
    atr_d = st.atr(d)
    br = brackets(m5)
    md, bd = m5["date"].to_numpy(), br["date"].to_numpy()
    ml, mh, mv = (m5[x].to_numpy(float) for x in ("l", "h", "vol"))
    bl, bh = br["l"].to_numpy(float), br["h"].to_numpy(float)
    dd = d["date"].to_numpy()
    out = []
    for i, day in enumerate(dd):
        i0, i1 = np.searchsorted(md, day, "left"), np.searchsorted(md, day, "right")
        a = atr_d[i]
        if i1 <= i0 or np.isnan(a) or a <= 0:
            continue
        step = step_for(float(a))
        j0, j1 = np.searchsorted(bd, day, "left"), np.searchsorted(bd, day, "right")
        lo, hi = float(ml[i0:i1].min()), float(mh[i0:i1].max())
        t = spread(bl[j0:j1], bh[j0:j1], (bucket(bh[j0:j1], step) - bucket(bl[j0:j1], step) + 1).astype(float),
                   step)
        mz = money_zone({k: round(v) for k, v in t.items()}, (hi + lo) / 2, step)
        vp = money_zone(spread(ml[i0:i1], mh[i0:i1], mv[i0:i1], step), (hi + lo) / 2, step)   # v2 G6
        if not mz or not vp:
            continue
        out.append(dict(i=i, session=pd.Timestamp(day).date().isoformat(), step=step,
                        mz=dict(POC=mz[0], VAL=mz[1], VAH=mz[2]), vol=dict(POC=vp[0], VAL=vp[1], VAH=vp[2])))
    return out


def virgin(d: pd.DataFrame, profs: list[dict], price: Optional[float], atr_now: Optional[float]) -> list[dict]:
    """The session levels no later daily bar has spanned (§4's rule), with age and distance."""
    lo, hi = d["l"].to_numpy(float), d["h"].to_numpy(float)
    n = len(d)
    out = []
    for p in profs:
        s = p["i"] + 1
        for kind, label in (("mz", "money zone"), ("vol", "volume")):
            for name in ("POC", "VAH", "VAL"):
                x = p[kind][name]
                if s >= n or np.any((lo[s:] <= x) & (hi[s:] >= x)):
                    continue                           # v2 G5: needs a later session that left it untouched
                out.append(dict(session=p["session"], kind=label, name=name, price=x, age_sessions=n - p["i"] - 1,
                                distance_atr=round(abs(x - price) / atr_now, 2) if price and atr_now else None))
    return out


def read(daily: pd.DataFrame, as_of, price: Optional[float], m5: Optional[pd.DataFrame] = None) -> dict:
    """The L2 daily read for day `as_of` from completed daily bars and 5-minute bars."""
    d = daily[daily["date"] < pd.Timestamp(as_of)].reset_index(drop=True)
    out = dict(status=UNTESTED, source=SOURCE, note=NOTE, pivots=day_pivots(d))
    a = st.atr(d) if len(d) else np.array([])
    atr_now = float(a[-1]) if len(a) and not np.isnan(a[-1]) else None
    profs = session_profiles(d, m5)
    out["sessions"] = len(profs)
    out["history_from"] = profs[0]["session"] if profs else None
    out["last_session"] = ({k: profs[-1][k] for k in ("session", "mz", "vol")}
                           if profs and profs[-1]["i"] == len(d) - 1 else None)
    v = virgin(d, profs, price, atr_now)
    out["n_virgin"] = len(v)
    if price is not None:
        below = sorted([x for x in v if x["price"] < price], key=lambda x: -x["price"])
        above = sorted([x for x in v if x["price"] > price], key=lambda x: x["price"])
        out["virgin_below"], out["virgin_above"] = below[:VIRGIN_SHOWN], above[:VIRGIN_SHOWN]
    return out


def lines(l2: dict, price: Optional[float]) -> list[str]:
    if not l2:
        return []
    out = [f"L2   daily layer ({l2['status']}; {l2['note']})"]
    p = l2.get("pivots")
    if p:
        c = p["cpr"]
        lv = ", ".join(f"{x['name']} {x['price']:g}" for x in p["levels"])
        out.append(f"     pivots from {p['from_session']}: CPR {c['BC']:g}-{c['TC']:g} width {c['width_pct']:g}% "
                   f"({c['reading']}), {p['relationship']} vs the day before; {lv}")
    s = l2.get("last_session")
    if s:
        out.append(f"     session {s['session']}: money zone POC {s['mz']['POC']:g} VA {s['mz']['VAL']:g}-{s['mz']['VAH']:g}; "
                   f"volume POC {s['vol']['POC']:g} VA {s['vol']['VAL']:g}-{s['vol']['VAH']:g}")
    if l2.get("sessions"):
        f = (lambda xs: "; ".join(f"{x['kind']} {x['name']} {x['price']:g} ({x['session']}, {x['distance_atr']} ATR)"
                                  for x in xs) or "none")
        out.append(f"     virgin session levels ({l2['n_virgin']} from {l2['sessions']} sessions since "
                   f"{l2['history_from']}): below {f(l2.get('virgin_below', []))} | above {f(l2.get('virgin_above', []))}")
    else:
        out.append("     session profiles: no 5-minute bars")
    return out
