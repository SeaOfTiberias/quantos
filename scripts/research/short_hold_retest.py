"""Failed daily signals re-tested at 15/30/60-minute holds, as pre-registered in
docs/SHORT_HOLD_RETEST_PREREG_2026-11-17.md (1559b28).
  python q13.py cases   worked cases for each set (no outcome statistics)
  python q13.py run     the test"""
import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, r"d:\Exodus_14_14\QuantOS\quantos")
sys.path.insert(0, str(Path(__file__).parent))
from core.market_map.l1_store import Store
from core.backtest import cci_cpr as ccp
import pivot_compression_breakout as pcb

HERE = Path(__file__).parent
SNAP = Path.home() / ".quantos/l1_snap_20261113"
M5 = SNAP / "m5"
HOLDS = (3, 6, 12)
COST = 0.0010
SETS = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "DARVAS"]
NAMES = {"E1": "daily close > R3", "E2": "daily close < S3", "E3": "5-min close > R3", "E4": "5-min close < S3",
         "E5": "Pivot Compression long", "E6": "Pivot Compression mirrored", "E7": "CCI/CPR long", "E8": "CCI/CPR short",
         "E9": "55d breakout + follow-through", "E10": "55d breakdown + follow-through", "E11": "55d breakout, no follow-through",
         "E12": "F&O screener CE", "E13": "F&O screener PE", "DARVAS": "Darvas Bucket B (2017-23 only)"}


def load_m5(sym):
    fs = sorted((M5 / sym).glob("*.csv.gz"))
    if not fs:
        return None
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True).drop_duplicates("ts").sort_values("ts")
    d["t"] = pd.to_datetime(d.ts, unit="s") + pd.Timedelta(hours=5, minutes=30)
    tod = d.t.dt.strftime("%H:%M")
    d = d[(tod >= "09:15") & (tod <= "15:25")].reset_index(drop=True)
    d["day"] = d.t.dt.normalize()
    d["hhmm"] = d.t.dt.strftime("%H:%M")
    return d


def daily_adj(sym):
    try:
        a, _ = Store(SNAP).adjusted(sym)
    except Exception:
        return None
    a = a.reset_index(drop=True)
    a["date"] = pd.to_datetime(a["date"])
    return a


def ext_side(sg):
    return lambda x: x


def signal_days(sym, a, d5, extra):
    """{set: [(signal_date or None, intraday_bar_index or None)]}; dates are the signal session."""
    out = {k: [] for k in SETS}
    # E1/E2 from the 5-minute session
    day = d5.groupby("day").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    P = (day.h + day.l + day.c) / 3
    R = day.h - day.l
    r3, s3 = (P + 2 * R).shift(1), (P - 2 * R).shift(1)
    for k, sig in (("E1", day.c > r3), ("E2", day.c < s3)):
        f = sig & ~sig.shift(1, fill_value=False)
        out[k] = [(x, None) for x in day.index[f]]
    # E3/E4 intraday: first 5-minute close beyond the day's level, 09:30-14:30
    lv = pd.DataFrame(dict(r3=r3, s3=s3))
    x = d5.join(lv, on="day")
    win = (x.hhmm >= "09:30") & (x.hhmm <= "14:30")
    for k, cond in (("E3", x.c > x.r3), ("E4", x.c < x.s3)):
        hit = x[cond & win].groupby("day").head(1)
        out[k] = [(None, int(i) + 1) for i in hit.index]          # entry = the next bar
    if a is not None and len(a) > 300:
        # E5/E6 Pivot Compression and its mirror
        p = pcb.signals(a)
        out["E5"] = [(dt, None) for dt in p.date[p.day1]]
        xd = lambda u, v: (u < v) & (u.shift(1) >= v.shift(1))
        ema, sma, cc, ccm, piv = p["ema5"], p["sma40"], p["cci"], p["cci_ma"], p["pivot"]
        ss = (p["tight"].astype(bool) & (ema < piv) & (ema.rolling(5).max() >= piv) & (ema < sma)
              & (pcb.barssince(xd(ema, sma)) <= 5) & (cc < ccm) & (pcb.barssince(xd(cc, ccm)) <= 5)
              & (a.vol > a.vol.rolling(50).mean() * 1.2) & (a.c < a.o)).fillna(False)
        out["E6"] = [(dt, None) for dt in p.date[ss & ~ss.shift(1, fill_value=False)]]
        # E7/E8 the 11-07 rule (full arm + 10-session skip)
        cd = ccp.candidate_days(a.h.values, a.l.values, a.c.values, a.date.dt.date.values)
        out["E7"] = [(a.date[i], None) for i in ccp.apply_skip(list(cd[("full", 1)]))]
        out["E8"] = [(a.date[i], None) for i in ccp.apply_skip(list(cd[("full", -1)]))]
        # E9/E10/E11 55-day breakouts (as in the 11-16 tests); the signal session is B+1
        for k, sg in (("E9", 1), ("E10", -1)):
            xx = sg * a.c
            e55 = xx.shift(1).rolling(55).max()
            e252 = xx.rolling(252).max()
            near = (a.c >= 0.95 * e252) if sg > 0 else (a.c <= -e252 / 0.95)
            brk = (xx > e55) & ~(xx.shift(1) > e55.shift(1)) & near
            for i in a.index[brk]:
                if i + 1 >= len(a):
                    continue
                ft = sg * (a.c[i + 1] - a.o[i + 1]) > 0 and sg * (a.c[i + 1] - a.c[i]) > 0
                if ft:
                    out[k].append((a.date[i + 1], None))
                elif sg > 0 and a.c[i + 1] < a.o[i + 1] and a.c[i + 1] < a.c[i]:
                    out["E11"].append((a.date[i + 1], None))
    for k in ("E12", "E13", "DARVAS"):
        out[k] = [(pd.Timestamp(dt), None) for dt in extra.get((k, sym), [])]
    return out


def trades(sym, d5, sig):
    """Rows: set, hold, entry variant, start ts, end ts, stock return."""
    rows = []
    days = d5.day.values
    first_bar = d5.groupby("day").head(1).set_index("day")
    day_index = pd.Index(first_bar.index)
    o, c, ts, hh = d5.o.values, d5.c.values, d5.ts.values, d5.hhmm.values
    for k, evs in sig.items():
        for dt, bar in evs:
            starts = []
            if bar is None:
                pos = day_index.searchsorted(pd.Timestamp(dt).normalize(), side="right")   # next session
                if pos >= len(day_index):
                    continue
                i0 = d5.index.get_loc(first_bar.index[pos]) if False else int(np.searchsorted(days, day_index[pos].to_datetime64()))
                if hh[i0] != "09:15":
                    continue
                starts = [("09:20", i0 + 1), ("09:15", i0)]
            else:
                if bar >= len(d5):
                    continue
                starts = [("next bar", bar)]
            for var, s in starts:
                for n in HOLDS:
                    e = s + n - 1
                    if e >= len(d5) or days[e] != days[s] or hh[e] > "15:25":
                        continue
                    rows.append((k, n, var, int(ts[s]), int(ts[e]), c[e] / o[s] - 1, str(days[s])[:10]))
    return rows


def extra_events():
    ex = {}
    for line in open(Path.home() / ".quantos/bt_fno/outcomes.jsonl"):
        r = json.loads(line)
        k = "E12" if r["side"] == "CE" else "E13"
        ex.setdefault((k, r["symbol"]), []).append(r["date"])
    for f in ("calls_dA.json", "calls_dB.json"):
        for v in json.loads((HERE.parent / "hist" / f).read_text()).values():
            ex.setdefault(("DARVAS", v["symbol"]), []).append(v["trade_date"])
    return ex


EXTRA = None


def worker(sym):
    global EXTRA
    if EXTRA is None:
        EXTRA = extra_events()
    d5 = load_m5(sym)
    if d5 is None or len(d5) < 1000:
        return [], None
    sig = signal_days(sym, daily_adj(sym), d5, EXTRA)
    return [(sym,) + r for r in trades(sym, d5, sig)], {k: len(v) for k, v in sig.items()}


def market(sym_pairs):
    sym, starts, ends = sym_pairs
    d5 = load_m5(sym)
    if d5 is None:
        return None
    o = pd.Series(d5.o.values, index=d5.ts.values)
    c = pd.Series(d5.c.values, index=d5.ts.values)
    r = c.reindex(ends).values / o.reindex(starts).values - 1
    return r


def run():
    syms = sorted(p.name for p in M5.iterdir() if p.is_dir())
    rows, counts = [], {}
    with Pool(3) as p:
        for k, (r, cn) in enumerate(p.imap_unordered(worker, syms)):
            rows += r
            for a, b in (cn or {}).items():
                counts[a] = counts.get(a, 0) + b
            if k % 30 == 0:
                print(f"events {k+1}/{len(syms)} trades {len(rows)}", flush=True)
    t = pd.DataFrame(rows, columns=["sym", "set", "hold", "var", "s", "e", "ret", "day"])
    pairs = t[["s", "e"]].drop_duplicates().reset_index(drop=True)
    tot, cnt = np.zeros(len(pairs)), np.zeros(len(pairs))
    with Pool(3) as p:
        for k, r in enumerate(p.imap_unordered(market, [(s, pairs.s.values, pairs.e.values) for s in syms])):
            if r is not None:
                ok = ~np.isnan(r)
                tot[ok] += r[ok]
                cnt[ok] += 1
            if k % 30 == 0:
                print(f"market {k+1}/{len(syms)}", flush=True)
    pairs["mkt"] = tot / np.maximum(cnt, 1)
    t = t.merge(pairs, on=["s", "e"], how="left")
    t["ex"] = t.ret - t.mkt
    t["yr"] = t.day.str[:4].astype(int)
    t.to_csv(HERE / "q13.csv", index=False)
    print("signals per set:", counts)
    analyse(t)


def tstat(x):
    return x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 2 and x.std(ddof=1) > 0 else float("nan")


def analyse(t):
    prim = lambda k: "next bar" if k in ("E3", "E4") else "09:20"
    disc_rows, fwd = [], []
    print("\n=== DISCOVERY 2017-2023 (net of 0.10%, excess vs all F&O stocks over the same bars) ===")
    for k in SETS:
        for n in HOLDS:
            v = t[(t.set == k) & (t.hold == n) & (t["var"] == prim(k)) & (t.yr <= 2023)]
            if k in ("E12", "E13"):
                sg = 1 if k == "E12" else -1
                print(f"  {k:<6} {NAMES[k]:<34} {n*5:>2} min: no discovery data, sign fixed {'long' if sg > 0 else 'short'} -> confirm")
                fwd.append((k, n, sg))
                continue
            if len(v) < 30:
                print(f"  {k:<6} {NAMES[k]:<34} {n*5:>2} min: n {len(v)} too few")
                continue
            sg = 1 if v.ex.mean() >= 0 else -1
            net = sg * v.ex - COST
            tt = tstat(net)
            go = net.mean() > 0 and tt >= 2 and k != "DARVAS"
            print(f"  {k:<6} {NAMES[k]:<34} {n*5:>2} min: n {len(v):>6}  {'long ' if sg > 0 else 'short'} gross excess {sg*v.ex.mean():+.3%}  "
                  f"net {net.mean():+.3%}  t {tt:+.1f}  gross > 0.10% {(sg*v.ex > COST).mean():.0%}  {'-> CONFIRM' if go else ''}")
            if go:
                fwd.append((k, n, sg))
    (HERE / "q13_discovery_locked.json").write_text(json.dumps(fwd))
    print(f"\nlocked for confirmation: {fwd}")
    print("\n=== CONFIRMATION 2024-2026 (Holm across the cells above) ===")
    res = []
    for k, n, sg in fwd:
        v = t[(t.set == k) & (t.hold == n) & (t["var"] == prim(k)) & (t.yr >= 2024)]
        net = sg * v.ex - COST
        tt = tstat(net) if len(v) > 2 else float("nan")
        pval = 0.5 * math.erfc(tt / math.sqrt(2)) if not math.isnan(tt) else 1.0
        res.append([k, n, sg, len(v), net.mean() if len(v) else float("nan"), tt, pval])
    order = sorted(range(len(res)), key=lambda i: res[i][6])
    m = len(res)
    alive = True
    for rank, i in enumerate(order):
        k, n, sg, nn, mu, tt, pv = res[i]
        thr = 0.05 / (m - rank)
        ok = alive and pv <= thr and mu > 0 and nn >= 100
        alive = alive and pv <= thr
        print(f"  {k:<6} {NAMES[k]:<34} {n*5:>2} min {'long ' if sg > 0 else 'short'}: n {nn:>6}  net {mu:+.3%}  t {tt:+.1f}  "
              f"p {pv:.4f} (Holm needs <= {thr:.4f})  {'PASS' if ok else 'FAIL'}")
    print("\n=== reported: 09:15 entry, all periods ===")
    for k in SETS:
        if k in ("E3", "E4"):
            continue
        for n in HOLDS:
            v = t[(t.set == k) & (t.hold == n) & (t["var"] == "09:15")]
            for lab, q in (("2017-23", v.yr <= 2023), ("2024-26", v.yr >= 2024)):
                u = v[q]
                if len(u) >= 30:
                    print(f"  {k:<6} {n*5:>2} min {lab}: n {len(u):>6}  excess {u.ex.mean():+.3%}")
    print("\n=== reported: E3/E4 by time of day, 2024-26 ===")
    for k in ("E3", "E4"):
        v = t[(t.set == k) & (t.yr >= 2024)].copy()
        v["hhmm"] = pd.to_datetime(v.s, unit="s").dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata").dt.strftime("%H:%M")
        for n in HOLDS:
            u = v[v.hold == n]
            print(f"  {k} {n*5:>2} min: before 11:00 {u[u.hhmm < '11:00'].ex.mean():+.3%} (n {(u.hhmm < '11:00').sum()}), "
                  f"after {u[u.hhmm >= '11:00'].ex.mean():+.3%} (n {(u.hhmm >= '11:00').sum()})")


def cases():
    ex = extra_events()
    for sym in ("TATACONSUM", "HDFCBANK"):
        d5 = load_m5(sym)
        sig = signal_days(sym, daily_adj(sym), d5, ex)
        print(sym, {k: len(v) for k, v in sig.items()})
        tr = pd.DataFrame(trades(sym, d5, sig), columns=["set", "hold", "var", "s", "e", "ret", "day"])
        for k in SETS:
            u = tr[(tr.set == k) & (tr.hold == 3)].tail(1)
            for _, r in u.iterrows():
                st = (pd.to_datetime(r.s, unit="s") + pd.Timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M")
                en = (pd.to_datetime(r.e, unit="s") + pd.Timedelta(hours=5, minutes=30)).strftime("%H:%M")
                print(f"   {k:<6} last event: entry {st} ({r['var']}), exit bar {en}")


if __name__ == "__main__":
    cases() if sys.argv[1] == "cases" else run()
