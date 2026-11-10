#!/usr/bin/env python3
"""
Market map review, round 1: draw the 15 random reads and write the review pack
(protocol: docs/MARKET_MAP_REVIEW_ROUND1.md, pre-registered before this ran).

Runs on the VM, against the L1 store and the 5-minute store. For each sample it writes:
  R##.json        the read (map_read zones=True, with its l1 part), its text lines, and
                  the review items (id, kind, text) for the form
  R##_D.csv, R##_W.csv, R##_M.csv   adjusted bars the read used (completed before as_of)
  R##_m5.csv      the last 10 sessions of adjusted 5-minute bars before as_of
and sample.json (the draw, with every skip and its reason).

    PYTHONPATH=~/quantos ~/quantos/.venv/bin/python review_pack.py --out ~/review_round1

--from-sample PATH regenerates the reads of an earlier draw (its sample.json: the same
symbols and as-of dates, same ids) under the current code, e.g. after the v2 change
(2026-11-11). Nothing is redrawn.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_map import read as mr  # noqa: E402
from core.market_map import structure as s  # noqa: E402
from core.market_map.l1_store import Store  # noqa: E402
from core.market_map.m5_store import M5Store  # noqa: E402

SEED = 20261108
N = 15
EXCLUDE = {"HDFCBANK", "SUPREMEIND"}
WINDOW = (date(2024, 11, 8), date(2026, 11, 6))
MIN_DAILY = 756
M5_DAYS = 30
M5_SESSIONS = 10
N_NEAR = 3


def _r(x):
    return None if x is None else round(float(x), 2)


def items(rid: str, rd: dict) -> list[dict]:
    """The review items of one read, each with an id the form refers to."""
    l1, out = rd["l1"], []

    def add(key, kind, text):
        out.append(dict(id=f"{rid}.{key}", kind=kind, text=text))

    for tf in s.TFS:
        t = l1["tf"][tf]
        if t["state"] == "none":
            add(f"{tf}.state", "state", f"{tf}: no trend state ({t['bars']} bars)")
            continue
        e, p, w = t["last_event"], t["protected"], t["weak"]
        pk, wk = ("low", "high") if t["state"] == "up" else ("high", "low")
        add(f"{tf}.state", "state", f"{tf}: {t['state']} for {t['age_bars']} bars")
        add(f"{tf}.event", "event", f"{tf}: last {e['type']} {e['direction']} in {e['period']} at {e['level']:g}")
        add(f"{tf}.protected", "protected", f"{tf}: protected {pk} {p['price']:g} ({p['period']})")
        add(f"{tf}.weak", "weak", f"{tf}: weak {wk} {w['price']:g} ({w['period']})")
        if t.get("premium_discount"):
            q = t["premium_discount"]
            add(f"{tf}.pd", "premium_discount",
                f"{tf}: price in {q['side']} ({q['position_pct']:g}% of {q['lo']:g}-{q['hi']:g}, eq {q['eq']:g})")
        if t.get("sweeps"):
            x = t["sweeps"][-1]
            src = f"swing {x['side']} {x['level']:g} ({x['swing']})" if "swing" in x else f"weak {x['side']} {x['level']:g}"
            add(f"{tf}.sweep", "sweep", f"{tf}: {src} swept to {x['extreme']:g} on {x['date']}, closed back inside "
                                        f"({x['status']})")
        if t.get("failed_breaks"):
            x = t["failed_breaks"][-1]
            add(f"{tf}.failed", "sweep", f"{tf}: swing {x['side']} {x['level']:g} closed beyond in {x['broke']}, back inside "
                                         f"on {x['date']} at {x['close']:g} ({x['status']})")
        if t.get("liquidity"):
            q = t["liquidity"]
            f = (lambda zs: "; ".join(f"{z['kind']} {z['level']:g} ({', '.join(z['swings'])})" for z in zs) or "none")
            add(f"{tf}.liq", "liquidity", f"{tf} equal highs/lows (shown, not in the HTF zones): above {f(q['above'])} | "
                                          f"below {f(q['below'])}")
    lad = rd.get("zones") or []
    zf = (lambda z: f"{z['range']} [{'+'.join(z['families'])}]{' STRONG' if z['strong'] else ''} "
                    f"{z['distance_atr']} ATR(D) away; {z['why']}")
    for i, z in enumerate([z for z in lad if z["where"] == "inside"], 1):     # v2: bands may overlap
        add("Z.inside" if i == 1 else f"Z.inside{i}", "zone", f"price inside zone {zf(z)}")
    below = sorted([z for z in lad if z["where"] == "below"], key=lambda z: z["distance"])[:N_NEAR]
    above = sorted([z for z in lad if z["where"] == "above"], key=lambda z: z["distance"])[:N_NEAR]
    for i, z in enumerate(below, 1):
        add(f"Z.b{i}", "zone", f"zone below #{i}: {zf(z)}")
    for i, z in enumerate(above, 1):
        add(f"Z.a{i}", "zone", f"zone above #{i}: {zf(z)}")
    hot = l1["htf"]["hot"]
    add("H.hot", "hot_zone", f"Ochoa hot zones: {len(hot['dpz'])} DPZ ({sum(x['mtz'] for x in hot['dpz'])} multi-timeframe); "
                             f"GPZ: " + ("; ".join(f"{x['tf']} {x['member']} {x['price']:g}" for x in hot["gpz"]) or "none"))
    from core.market_map import daily as dl, pivots as pv, profiles as pf
    pl = pv.lines(l1["pivots"], l1["price"]) if l1.get("pivots") else []
    for k, ln in zip(("P.cpr", "P.levels"), pl):
        add(k, "pivot", ln.strip())
    fl = pf.lines(l1["profiles"], l1["price"]) if l1.get("profiles") else []
    for k, ln in zip(("V.periods", "V.virgin", "V.long"), fl):
        add(k, "profile", ln.strip())
    ll = dl.lines(l1["l2"], l1["price"]) if l1.get("l2") else []
    for k, ln in zip(("L2.pivots", "L2.session", "L2.virgin"), ll[1:]):
        add(k, "daily_layer", ln.strip())
    b, a = rd.get("below"), rd.get("above")
    room = (lambda z, w: f"first zone {w} {z['range']}, {z['distance_atr']} ATR(D) away" if z else f"no zone {w}")
    add("X.watch", "watch", f"{l1['alignment']['text']}; {room(b, 'below')}; {room(a, 'above')}"
                            + (f"; inside {rd['inside']['range']}" if rd.get("inside") else ""))
    return out


def bars_out(df: pd.DataFrame, cols=("date", "period", "o", "h", "l", "c", "vol")) -> pd.DataFrame:
    df = df[[c for c in cols if c in df.columns]].copy()
    for c in ("o", "h", "l", "c"):
        df[c] = df[c].astype(float).round(2)
    if "date" in df:
        df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--from-sample", type=Path, help="regenerate this sample.json's picks; no new draw")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    st = Store()
    m5s = M5Store(st.root)
    uni = json.loads(st.universe_path.read_text(encoding="utf-8"))
    syms = [r["sym"] for r in uni["rows"] if r["sym"] not in EXCLUDE]
    rng = np.random.default_rng(SEED)
    fixed = json.loads(a.from_sample.read_text(encoding="utf-8"))["picked"] if a.from_sample else None
    order = [x["sym"] for x in fixed] if fixed else list(rng.permutation(syms))
    picked, skipped = [], []
    for j, sym in enumerate(order):
        if len(picked) == N:
            break
        if fixed:
            as_of = date.fromisoformat(fixed[j]["as_of"])
        else:
            raw = st.read_raw(sym)
            days = raw["date"][(raw["date"] >= pd.Timestamp(WINDOW[0])) & (raw["date"] <= pd.Timestamp(WINDOW[1]))]
            if days.empty:
                skipped.append(dict(sym=sym, reason="no sessions in the window"))
                continue
            as_of = days.iat[int(rng.integers(len(days)))].date()
        adj, _ = st.adjusted(sym)
        seg = s.latest_segment(adj)
        nd = int((seg["date"] < pd.Timestamp(as_of)).sum())
        if nd < MIN_DAILY:
            skipped.append(dict(sym=sym, as_of=as_of.isoformat(), reason=f"{nd} daily bars before as_of in the latest segment"))
            continue
        m5 = m5s.adjusted(sym, adj, st.actions().get(sym, []))
        lo = pd.Timestamp(as_of - timedelta(days=M5_DAYS))
        m5 = m5[(m5["date"] >= lo) & (m5["date"] < pd.Timestamp(as_of))] if len(m5) else m5
        if not len(m5):
            skipped.append(dict(sym=sym, as_of=as_of.isoformat(), reason=f"no 5-minute bars in the {M5_DAYS} days before"))
            continue
        rd = mr.map_read(sym, as_of=as_of, zones=True, l1_store=st)
        if "error" in rd or rd.get("source") != "l1":
            skipped.append(dict(sym=sym, as_of=as_of.isoformat(), reason=rd.get("error") or rd.get("fallback")))
            continue
        rid = fixed[j]["id"] if fixed else f"R{len(picked) + 1:02d}"
        txt = mr.lines(rd)                                    # includes the L1 and L2 lines
        doc = dict(id=rid, symbol=sym, as_of=as_of.isoformat(), last_bar=rd["l1"]["last_date"],
                   price=rd["price"], atr_d=rd["atr"], lines=txt, items=items(rid, rd), read=rd)
        ids = [x["id"] for x in doc["items"]]
        assert len(ids) == len(set(ids)), f"duplicate item ids in {rid}"
        (a.out / f"{rid}.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        for tf in s.TFS:
            bars_out(s.completed(seg, tf, as_of)).to_csv(a.out / f"{rid}_{tf}.csv", index=False)
        sess = sorted(m5["date"].unique())[-M5_SESSIONS:]
        mm = m5[m5["date"].isin(sess)].copy()
        mm["dt"] = mm["dt"].dt.strftime("%Y-%m-%d %H:%M")
        mm[["dt", "o", "h", "l", "c", "vol"]].round(2).to_csv(a.out / f"{rid}_m5.csv", index=False)
        picked.append(dict(id=rid, sym=sym, as_of=as_of.isoformat(), n_items=len(doc["items"])))
        print(rid, sym, as_of, len(doc["items"]), "items", flush=True)
    (a.out / "sample.json").write_text(json.dumps(dict(
        seed=SEED, n=N, window=[d.isoformat() for d in WINDOW], universe_as_of=uni["as_of"], exclude=sorted(EXCLUDE),
        regenerated_from=str(a.from_sample) if a.from_sample else None,
        picked=picked, skipped=skipped), indent=1), encoding="utf-8")
    print(f"{len(picked)} picked, {len(skipped)} skipped")
    return 0 if len(picked) == N else 1


if __name__ == "__main__":
    raise SystemExit(main())
