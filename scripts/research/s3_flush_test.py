"""Buy the S3 flush at map demand, as pre-registered in docs/S3_FLUSH_LONG_PREREG_2026-11-17.md (35759d3).
  python q11.py cases      five worked cases, printed in full
  python q11.py run        the full test (multiprocessing by symbol)"""
import sys
from datetime import timedelta
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, r"d:\Exodus_14_14\QuantOS\quantos")
from core.market_map.l1_store import Store
from core.market_map import structure, card as cd, call_plan as cp

H = Path(__file__).parent
SNAP = Path.home() / ".quantos/l1_snap_20261113"
DEMAND = {"demand", "bull_ob", "bull_fvg"}
COST = 0.0025


def universe():
    st = Store(SNAP)
    m = pd.read_csv(Path.home() / ".quantos/fyers_symbol_master_NSE_FO.csv", header=None, low_memory=False)
    und = set(m[m[1].astype(str).str.endswith("FUT")][13].astype(str))
    return sorted(und & set(st.symbols()) - {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"})


def bars(sym):
    a, _ = Store(SNAP).adjusted(sym)
    a = a.reset_index(drop=True)
    a["date"] = pd.to_datetime(a["date"])
    return a


def card_at(sym, a, i):
    sub = a.iloc[:i + 1]
    return cd.card(sym, structure.l1_read(sub, a.at[i, "date"].date() + timedelta(days=1)), sub), sub


def trade(a, i, e, stop, tg, n=10):
    risk = e - stop
    for j in range(i + 1, i + 1 + n):
        if a.at[j, "l"] <= stop:
            return -1.0, "stop", j
        if a.at[j, "h"] >= tg:
            return (tg - e) / risk, "target", j
    return (a.at[i + n, "c"] - e) / risk, "time", i + n


def events(sym, verbose=False, only=None):
    a = bars(sym)
    if len(a) < 300:
        return []
    P = (a.h + a.l + a.c).shift(1) / 3
    s3 = P - 2 * (a.h - a.l).shift(1)
    sig = a.c < s3
    first = sig & ~sig.shift(1, fill_value=False)
    pc = a.c.shift(1)
    atr = pd.concat([a.h - a.l, (a.h - pc).abs(), (a.l - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    out = []
    for i in a.index[first & (a.date >= "2021-01-01")]:
        if i + 11 >= len(a) or pd.isna(atr[i]) or i < 300:
            continue
        if only and a.at[i, "date"].date().isoformat() not in only:
            continue
        try:
            c, sub = card_at(sym, a, i)
            cprev, subp = card_at(sym, a, i - 1)
        except Exception as ex:
            if verbose:
                print("card failed", sym, ex)
            continue
        close, low = a.at[i, "c"], a.at[i, "l"]
        za = [z for z in (c.get("zones_d") or {}).get("inside", []) if z["kind"] in DEMAND]
        zb = (c.get("zones") or {}).get("inside", [])
        lv = cp.structural_levels(cprev, subp, "CE")      # as registered: support levels on the prior card
        zc = sorted({(round(p, 2), k) for p, k in lv if low <= p <= close})
        e = a.at[i + 1, "o"]
        stop = min(low - 0.1 * atr[i], a.at[i + 1, "o"] - 0.5 * atr[i])     # amended before the run (HDFCBANK 09-09)
        risk = e - stop
        if risk <= 0:
            continue
        t = cp.target(c, "CE", e)
        tg = t["level"] if t and t["level"] - e >= risk else e + 2 * risk
        R, why, j = trade(a, i, e, stop, tg)
        Rc, _, _ = trade(a, i, close, stop, tg if tg - close >= close - stop else close + 2 * (close - stop)) \
            if close > stop else (np.nan, None, None)
        row = dict(sym=sym, d=a.at[i, "date"].date().isoformat(), close=close, s3=round(s3[i], 2), low=low,
                   entry=e, stop=round(stop, 2), target=round(tg, 2), tgt_kind=(t or {}).get("kind") if t and tg == t["level"] else "2R",
                   R=R - COST * e / risk, R_close=(Rc - COST * close / (close - stop)) if close > stop else np.nan,
                   exit=why, ret10=a.at[i + 11, "c"] / e - 1, risk_pct=risk / e,
                   a=bool(za), b=bool(zb), c=bool(zc),
                   a_what="; ".join(z["name"] for z in za), b_what="; ".join(f"{z['lo']}-{z['hi']} {z['why'][:40]}" for z in zb),
                   c_what="; ".join(f"{p} {k}" for p, k in zc))
        row["MAP"] = row["a"] or row["b"] or row["c"]
        out.append(row)
        if verbose:
            print(pd.Series(row).to_string(), "\n")
    return out


def run():
    syms = universe()
    with Pool(3) as p:
        rows = []
        for k, r in enumerate(p.imap_unordered(events, syms)):
            rows += r
            if k % 20 == 0:
                print(f"{k+1}/{len(syms)} rows {len(rows)}", flush=True)
    r = pd.DataFrame(rows)
    # equal-weight universe, next open -> close 10 sessions on
    O, C = {}, {}
    for s in syms:
        a = bars(s)
        O[s], C[s] = a.set_index("date")["o"], a.set_index("date")["c"]
    O, C = pd.DataFrame(O).sort_index(), pd.DataFrame(C).sort_index()
    ew = (C.shift(-11) / O.shift(-1) - 1).mean(axis=1)
    nifty = pd.read_csv(H / "index_bars/NIFTY.csv", parse_dates=["date"]).set_index("date")["c"]
    nchg = nifty.pct_change()
    r["ex10"] = r.ret10 - r.d.map(lambda d: ew.get(pd.Timestamp(d), np.nan)) - COST
    r["nifty_flush"] = r.d.map(lambda d: nchg.get(pd.Timestamp(d), np.nan) < -0.01)
    r.to_csv(H / "q11.csv", index=False)
    report(r)


def report(r):
    halves = (("2021-23", "2021", "2024"), ("2024-26", "2024", "2027"))
    def line(v, lab):
        print(f"  {lab:<34} n {len(v):>5}  net R {v.R.mean():+.2f}  win {(v.R > 0).mean():.0%}  ex10 {v.ex10.mean():+.2%}  "
              f"close-entry R {v.R_close.mean():+.2f}")
    for name, g in (("H1 MAP", r[r.MAP]), ("NO MAP", r[~r.MAP]), ("H2 every S3", r)):
        print(f"\n== {name}")
        line(g, "all")
        for h, lo, hi in halves:
            line(g[(g.d >= lo) & (g.d < hi)], h)
    print("\nMAP sub-kinds (reported):")
    for k, lab in (("a", "(a) in D demand/bull OB/FVG"), ("b", "(b) in HTF zone"), ("c", "(c) swept-and-held level")):
        for h, lo, hi in halves:
            v = r[r[k] & (r.d >= lo) & (r.d < hi)]
            line(v, f"{lab} {h}")
    print("\nNIFTY down > 1% that day (reported):")
    for f in (True, False):
        for h, lo, hi in halves:
            v = r[(r.nifty_flush == f) & (r.d >= lo) & (r.d < hi)]
            line(v, f"{'market flush' if f else 'stock-specific'} {h}")


if __name__ == "__main__":
    if sys.argv[1] == "cases":
        for s, d in (("TATACONSUM", None), ("HDFCBANK", None), ("COALINDIA", None)):
            ev = events(s)
            print(f"{s}: {len(ev)} S3 flushes since 2021; MAP {sum(e['MAP'] for e in ev)}")
        for s in ("TATACONSUM", "COALINDIA"):
            ev = events(s)
            for e in ev[-3:]:
                print(pd.Series(e).to_string(), "\n")
    else:
        run()
