#!/usr/bin/env python3
"""
Playbook v1 S8 runner (docs/MARKET_PLAYBOOK_S8_PREREG_2026-11-13.md, frozen 1cebb0f).

    python scripts/playbook_s8.py --store ~/.quantos/l1_snap_20261113 --out <dir> --mode count
    python scripts/playbook_s8.py --store ~/.quantos/l1_snap_20261113 --out <dir> --mode full
    python scripts/playbook_s8.py --out <dir> --mode report

count   prereg §8 step 3: every fourth P1 read date and every P2 trigger; plans and placebo
        draws only. No forward walk, so no fill and no R is computed. Writes counts.json.
full    every P1 read date and P2 trigger, with the one-at-a-time rule; every setup walked
        forward. Writes rows/<SYM>.jsonl.
report  the §6 verdict and the §7 reported-only tables from rows/ (results.json, results.md).

Reads are cached per stock in reads/<SYM>.json (plans only, no outcomes), so the full run
reuses the count pass's reads. A stock whose output file exists is skipped (resumable).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core.market_map import playbook as pb  # noqa: E402
from core.market_map import playbook_s8 as s8  # noqa: E402
from core.market_map import structure as st  # noqa: E402
from core.market_map.l1_store import Store  # noqa: E402

G: dict = {}


def _init(store_root, sessions, prev, p1d, mode, out):
    G.update(store=Store(Path(store_root)), sessions=sessions, prev=prev, p1d=p1d, mode=mode, out=Path(out))
    G["cost"] = s8._cost_model()


def _reason(p: dict) -> str:
    r = p.get("reason") or ""
    for k in ("timeframes disagree", "W has no trend", "no fresh strong", "not in W", "zone too wide", "only ",
              "not beyond", "no price"):
        if r.startswith(k) or k in r:
            return k.strip()
    return r[:40]


def _clean(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and math.isinf(v) else v) for k, v in d.items() if k != "log"}


def _row(track, rid, match, sym, d, setup, res, excl, extra=None):
    sc = s8.score(setup, res, G["cost"])
    r = dict(track=track, id=rid, match=match, sym=sym, read=d.isoformat(), side=setup["side"],
             at_open=bool(setup.get("entry_at_open")), excluded=excl, band=setup.get("band"),
             entry=setup["entry"], stop=setup["stop"], target=setup["target"], risk=setup["risk"],
             rr=setup.get("rr"), **sc)
    r.update(extra or {})
    return r


def work(task):
    sym, member = task
    out = G["out"]
    mode = G["mode"]
    done = out / ("rows" if mode == "full" else "counts") / f"{sym}.json{'l' if mode == 'full' else ''}"
    if done.exists():
        return sym, None
    t0 = time.time()
    adj, _ = G["store"].adjusted(sym)
    cpath = out / "reads" / f"{sym}.json"
    cache = json.loads(cpath.read_text()) if cpath.exists() else {}
    dirty = False
    segs = {}
    cnt, rows = Counter(), []

    def seg_for(d):
        s = s8.segment_at(adj, d)
        key = int(s["seg"].iat[0]) if len(s) and "seg" in s else 0
        if key not in segs:
            segs[key] = (s, s8.SegBars(s) if len(s) else None)
        return segs[key]

    def full_read(seg, d):
        try:
            return st.l1_read(seg, d, None)
        except Exception as e:                     # counted, never silently dropped
            return {"error": f"{type(e).__name__}: {str(e)[:120]}"}

    if adj.empty:
        cnt["no_bars"] += 1
    # ── P1 ────────────────────────────────────────────────────────────────
    dates = G["p1d"] if mode == "full" else G["p1d"][::4]
    alive = None
    for d in ([] if adj.empty else dates):
        if G["prev"].get(d) not in member:
            continue
        cnt["p1_universe_reads"] += 1
        if mode == "full" and alive and d.isoformat() <= alive:
            cnt["p1_skipped_alive"] += 1
            continue
        seg, sb = seg_for(d)
        if sb is None or len(sb.completed("D", d)) < 30:
            cnt["p1_short_history"] += 1
            continue
        key = f"P1|{d}"
        if key not in cache:
            if not s8.p1_gate(sb, d):
                cache[key] = dict(gate=False)
            else:
                l1 = full_read(seg, d)
                cache[key] = dict(gate=True, error=l1["error"]) if "error" in l1 else \
                    dict(gate=True, p1=pb.plan_p1(l1), **s8.compact_read(l1))
            dirty = True
        rd = cache[key]
        if not rd["gate"]:
            cnt["p1_gate_fail"] += 1
            continue
        if rd.get("error"):
            cnt["p1_read_error"] += 1
            continue
        p = rd["p1"]
        cnt[f"p1_{p['status']}"] += 1
        if p["status"] != "SETUP":
            cnt[f"p1_reason|{_reason(p)}"] += 1
            continue
        excl = s8.excluded(sym, d, G["sessions"])
        plc = s8.placebo_setups(rd, p, s8.rng_for(sym, d))
        cnt[f"p1_setup_{p['side']}"] += 1
        cnt["p1_setup_at_open"] += bool(p.get("entry_at_open"))
        cnt["p1_setup_with_placebo"] += bool(plc)
        cnt["p1_placebos"] += len(plc)
        cnt["p1_setup_excluded"] += excl
        if mode != "full":
            continue
        opp = rd["opp_long"] if p["side"] == "long" else rd["opp_short"]
        rid = f"{sym}|P1|{d}"
        res = pb.simulate(p, seg, d, opp, sb)
        alive = res.get("end") or alive
        rows.append(_row("P1", rid, None, sym, d, p, res, excl, dict(m_state=rd["m_state"])))
        for j, q in enumerate(plc):
            rows.append(_row("P1-placebo", f"{rid}|{j}", rid, sym, d, q, pb.simulate(q, seg, d, opp, sb), excl))
        mq = s8.market_setup(rd, p)
        rows.append(_row("P1-market", f"{rid}|m", rid, sym, d, mq, pb.simulate(mq, seg, d, opp, sb), excl))
    # ── P2 ────────────────────────────────────────────────────────────────
    trig, seen_seg = [], set()
    for key_seg in ([] if adj.empty else sorted(set(adj["seg"]) if "seg" in adj else {0})):
        seg = adj[adj["seg"] == key_seg].reset_index(drop=True) if "seg" in adj else adj
        if len(seg) < 30:
            continue
        trig += s8.p2_triggers(seg)
    alive2 = {"P2": None, "P2C": None}
    for d, direction in sorted(trig):
        if not s8.READ_START <= d <= s8.READ_END or G["prev"].get(d) not in member:
            continue
        seg, sb = seg_for(d)
        if sb is None:
            continue
        w = sb.summary("W", d)["state"]
        if w != ("down" if direction == "up" else "up"):
            continue
        cnt["p2_triggers"] += 1
        if mode == "full" and all(a and d.isoformat() <= a for a in alive2.values()):
            cnt["p2_skipped_alive"] += 1
            continue
        key = f"P2|{d}"
        if key not in cache:
            l1 = full_read(seg, d)
            if "error" in l1:
                cache[key] = dict(error=l1["error"])
            else:
                p2 = pb.plan_p2(l1, seg, d)
                cache[key] = dict(p2=_clean(p2), p2c=_clean(s8.plan_p2_control(l1, seg, d, p2)), **s8.compact_read(l1))
            dirty = True
        rd = cache[key]
        if rd.get("error"):
            cnt["p2_read_error"] += 1
            continue
        excl = s8.excluded(sym, d, G["sessions"])
        for track, p in (("P2", rd["p2"]), ("P2C", rd["p2c"])):
            if p["status"] != "SETUP":
                cnt[f"{track.lower()}_no|{(p.get('reason') or '')[:40]}"] += 1
                continue
            cnt[f"{track.lower()}_setup_{p['side']}"] += 1
            if mode != "full":
                continue
            if alive2[track] and d.isoformat() <= alive2[track]:
                cnt[f"{track.lower()}_skipped_alive"] += 1
                continue
            p = dict(p, swept_level=p.get("swept_level") if p.get("swept_level") is not None else
                     (-math.inf if p["side"] == "long" else math.inf))
            opp = rd["opp_long"] if p["side"] == "long" else rd["opp_short"]
            rid = f"{sym}|{track}|{d}"
            res = pb.simulate(p, seg, d, opp, sb)
            alive2[track] = res.get("end") or alive2[track]
            rows.append(_row(track, rid, None, sym, d, p, res, excl))
            if track == "P2":
                q = s8.no_e3(p)
                rows.append(_row("P2-noE3", f"{rid}|noE3", rid, sym, d, q, pb.simulate(q, seg, d, opp, sb), excl))
    if dirty:
        cpath.write_text(json.dumps(cache, default=str))
    cnt["seconds"] = round(time.time() - t0, 1)
    if mode == "full":
        done.write_text("".join(json.dumps(_clean(r), default=str) + "\n" for r in rows))
    else:
        done.write_text(json.dumps(cnt))
    return sym, dict(cnt)


def setup_run(store_root: Path):
    store = Store(store_root)
    t = time.time()
    raw = {s: store.read_raw(s) for s in store.symbols()}
    sessions_all = Counter(d for g in raw.values() for d in g["date"].dt.date)
    sessions = sorted(d for d, n in sessions_all.items() if n >= 50)
    prev = {sessions[i]: sessions[i - 1] for i in range(1, len(sessions))}
    uni = s8.universe_table(raw, store.etfs())
    member = defaultdict(set)
    for d, syms in uni.items():
        for s in syms:
            member[s].add(d)
    p1d = s8.p1_read_dates(sessions)
    lo, hi = s8.READ_START, s8.READ_END
    tasks = sorted((s, frozenset(x for x in m if lo.replace(year=lo.year - 1) <= x <= hi)) for s, m in member.items())
    tasks = [(s, m) for s, m in tasks if m]
    print(f"setup {time.time() - t:.0f}s: {len(sessions)} sessions, {len(p1d)} P1 read dates, {len(tasks)} stocks "
          f"ever in the top 500", flush=True)
    return sessions, prev, p1d, tasks


def prefix_check(store_root: Path, syms: list[str]) -> dict:
    store = Store(store_root)
    out = {}
    for s in syms:
        adj, _ = store.adjusted(s)
        seg = st.latest_segment(adj)
        n = len(seg)
        out[s] = s8.events_prefix_ok(seg, range(250, n, max(1, n // 25)))
    return out


def report(out: Path):
    rows = [json.loads(x) for p in sorted((out / "rows").glob("*.jsonl")) for x in p.read_text().splitlines() if x]
    v = s8.verdict(rows)
    v["reported"] = reported(rows)
    (out / "results.json").write_text(json.dumps(v, indent=1, default=str))
    print(json.dumps(v, indent=1, default=str)[:6000])


def reported(rows: list[dict]) -> dict:
    """§7, no verdict depends on these."""
    sc = [r for r in rows if not r["excluded"]]
    by = defaultdict(list)
    for r in sc:
        by[r["track"]].append(r)

    def summ(xs):
        f = [r for r in xs if r["filled"]]
        mean = lambda k, ys: round(sum(y[k] for y in ys) / len(ys), 4) if ys else None
        return dict(setups=len(xs), filled=len(f), fill_rate=round(len(f) / len(xs), 3) if xs else None,
                    net_r=mean("net_r", xs), gross_r=mean("gross_r", xs), net_r_filled=mean("net_r", f),
                    cost_r_filled=mean("cost_r", f), seg_end=sum(r["seg_end"] for r in xs),
                    outcomes=Counter((r["reason"] or r["outcome"]).split(" ")[0] for r in xs).most_common(12))
    out = {t: summ(xs) for t, xs in by.items()}
    p1 = by.get("P1", [])
    out["P1_by_side"] = {s: summ([r for r in p1 if r["side"] == s]) for s in ("long", "short")}
    out["P1_at_open"] = summ([r for r in p1 if r["at_open"]])
    out["P1_by_band"] = {k: summ([r for r in p1 if (r["band"] or "").startswith(k)])
                         for k in ("W demand", "W bull_ob", "M demand", "M bull_ob", "W supply", "W bear_ob",
                                   "M supply", "M bear_ob")}
    out["P1_by_m_state"] = {k: summ([r for r in p1 if r.get("m_state") == k]) for k in ("up", "down", "range", "none")}
    f = sorted([r for r in p1 if r["filled"]], key=lambda r: r["risk_pct"])
    t = len(f) // 3
    out["P1_cost_by_risk_tercile"] = [dict(risk_pct_max=x[-1]["risk_pct"], **summ(x)) for x in (f[:t], f[t:2 * t], f[2 * t:]) if x]
    out["P1_giveback_after_2R"] = sum(1 for r in p1 if r["filled"] and (r.get("mfe") or 0) >= 2 and r["gross_r"] <= 0.1)
    out["excluded_setups"] = Counter(r["track"] for r in rows if r["excluded"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=Path.home() / ".quantos" / "l1_snap_20261113")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=["count", "full", "report", "prefix"], required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="first N stocks only (smoke test)")
    a = ap.parse_args()
    if a.mode == "report":
        report(a.out)
        return 0
    if a.mode == "prefix":
        print(json.dumps(prefix_check(a.store, ["HDFCBANK", "KEI", "DMART", "TCS", "YESBANK", "SUZLON", "IRCTC",
                                                 "TATAMOTORS", "ADANIENT", "PCJEWELLER"]), indent=1))
        return 0
    for sub in ("reads", "rows" if a.mode == "full" else "counts"):
        (a.out / sub).mkdir(parents=True, exist_ok=True)
    sessions, prev, p1d, tasks = setup_run(a.store)
    if a.limit:
        tasks = tasks[:a.limit]
    t0, agg, n = time.time(), Counter(), 0
    with Pool(a.workers, _init, (str(a.store), sessions, prev, p1d, a.mode, str(a.out))) as pool:
        for sym, c in pool.imap_unordered(work, tasks):
            n += 1
            if c:
                agg.update({k: v for k, v in c.items() if k != "seconds"})
            if n % 25 == 0 or n == len(tasks):
                el = time.time() - t0
                print(f"{n}/{len(tasks)} stocks, {el / 60:.0f} min, ~{el / n * (len(tasks) - n) / 60:.0f} min left",
                      flush=True)
    if a.mode == "count":
        tot = Counter()
        for p in (a.out / "counts").glob("*.json"):
            tot.update({k: v for k, v in json.loads(p.read_text()).items() if k != "seconds"})
        proj = tot["p1_SETUP"] * 4
        res = dict(counts=dict(sorted(tot.items())), projected_p1_setups_full=proj,
                   p1_cadence="every other week" if proj >= s8.P1_MIN_PROJECTED else "every week (§8 fallback)")
        (a.out / "counts.json").write_text(json.dumps(res, indent=1))
        print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
