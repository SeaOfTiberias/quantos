"""Index overnight rebound after a NIFTY sell-off day.

Pre-registration: docs/OVERNIGHT_REBOUND_PREREG_2026-11-17.md. Research only, no orders.
Long at the signal close, out at the next open; scored per instrument against non-signal nights.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from core.reference import calendar as cal

IDX = Path.home() / ".quantos/index_bars"
COST = 0.0007
DISC = (pd.Timestamp("2012-02-21"), pd.Timestamp("2020-12-31"))
CONF = (pd.Timestamp("2021-01-01"), pd.Timestamp("2026-11-13"))


def load(sym: str) -> pd.DataFrame:
    d = pd.read_csv(IDX / f"{sym}.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    d["no"] = d.o.shift(-1)
    d["nc"] = d.c.shift(-1)
    d["nd"] = d.date.shift(-1)
    d["ret"] = d.c / d.c.shift(1) - 1
    d["on"] = d.no / d.c - 1          # signal close -> next open
    d["cc"] = d.nc / d.c - 1          # signal close -> next close
    lo, hi = cal.coverage()

    def ok(r) -> bool:
        if pd.isna(r.nd):
            return False
        t = r.date.date()
        if lo <= t and r.nd.date() <= hi:
            return cal.next_trading_day(t) == r.nd.date()
        return (r.nd - r.date).days <= 4

    d["valid"] = d.apply(ok, axis=1)
    return d


def score(x: pd.DataFrame, sig: pd.Series, col: str = "on", cost: float = COST) -> dict:
    s = x.loc[sig & x.valid, col]
    b = x.loc[~sig & x.valid, col]
    net = s - cost
    t1 = net.mean() / (net.std(ddof=1) / math.sqrt(len(net))) if len(net) > 1 else float("nan")
    tw = stats.ttest_ind(s, b, equal_var=False).statistic if len(s) > 1 else float("nan")
    p1 = stats.t.sf(t1, len(net) - 1) if len(net) > 1 else float("nan")
    return dict(n=len(s), gross=s.mean(), net=net.mean(), t=t1, p=p1, base=b.mean(), welch=tw,
                win=(net > 0).mean(), worst=s.min(), p5=s.quantile(0.05) if len(s) else float("nan"))


def fmt(r: dict) -> str:
    return (f"n {r['n']:>4}  gross {r['gross']:+.3%}  net {r['net']:+.3%}  t {r['t']:+.2f}  "
            f"base {r['base']:+.3%}  Welch {r['welch']:+.2f}  win {r['win']:.0%}  "
            f"worst {r['worst']:+.2%}  p5 {r['p5']:+.2%}")


def per(x, a, b):
    return x[(x.date >= a) & (x.date <= b)]


def main() -> None:
    nifty = load("NIFTY")
    sigmap = dict(zip(nifty.date, nifty.ret))
    data = {s: load(s) for s in ("NIFTY", "BANKNIFTY")}
    for s, x in data.items():
        x["nret"] = x.date.map(sigmap)

    print("== five worked signal nights (NIFTY, -1%)")
    x = data["NIFTY"]
    w = x[(x.nret <= -0.01) & x.valid]
    for _, r in w.iloc[[0, 50, 150, 300, -1]].iterrows():
        print(f"  {r.date.date()}  NIFTY ret {r.nret:+.2%}  close {r.c:.2f}  next {r.nd.date()} open {r.no:.2f}  "
              f"overnight {r.on:+.3%}")

    verdict = {}
    print("\n== SCORED: NIFTY close <= -1.0%, long close -> next open, cost 0.07%")
    confp = {}
    for s, x in data.items():
        sig = x.nret <= -0.01
        d = per(x, *DISC)
        rd = score(d, sig.loc[d.index])
        d20 = d[d.date.dt.year != 2020]
        rx = score(d20, sig.loc[d20.index])
        c = per(x, *CONF)
        rc = score(c, sig.loc[c.index])
        print(f" {s}\n   discovery 2012-20: {fmt(rd)}\n   ex-2020:           {fmt(rx)}\n   confirm 2021-26:   {fmt(rc)}")
        dpass = rd["net"] > 0 and rd["t"] >= 2 and rd["welch"] >= 1.65 and rx["net"] > 0
        verdict[s] = dict(disc=dpass, rc=rc)
        print(f"   discovery: {'PASS' if dpass else 'FAIL'} (net>0 & t>=2: {rd['net'] > 0 and rd['t'] >= 2}, "
              f"Welch>=1.65: {rd['welch'] >= 1.65}, ex-2020 net>0: {rx['net'] > 0})")
        if dpass:
            confp[s] = rc["p"]
    # Holm over instruments that reached confirmation
    order = sorted(confp, key=confp.get)
    m = len(order)
    holm_ok, stop = {}, False
    for k, s in enumerate(order):
        ok = (not stop) and confp[s] <= 0.05 / (m - k)
        stop = stop or not ok
        holm_ok[s] = ok
    print("\n== VERDICT")
    for s, v in verdict.items():
        rc = v["rc"]
        if not v["disc"]:
            print(f" {s}: FAIL at discovery")
            continue
        cpass = rc["n"] >= 50 and rc["net"] > 0 and holm_ok[s] and rc["gross"] > rc["base"]
        print(f" {s}: {'PASS' if cpass else 'FAIL'} at confirmation (n {rc['n']}, net {rc['net']:+.3%}, "
              f"p {rc['p']:.4f}, Holm {holm_ok[s]}, gross>base {rc['gross'] > rc['base']})")

    print("\n== REPORTED, not scored")
    for s, x in data.items():
        for lab, sig, col, cost in (
            ("exit next CLOSE, -1%", x.nret <= -0.01, "cc", COST),
            ("threshold -1.5%", x.nret <= -0.015, "on", COST),
            ("threshold -2.0%", x.nret <= -0.02, "on", COST),
            ("cost 0.10%, -1%", x.nret <= -0.01, "on", 0.001),
        ) + ((("own -1% signal", x.ret <= -0.01, "on", COST),) if s == "BANKNIFTY" else ()):
            for pl, a, b in (("2012-20", *DISC), ("2021-26", *CONF)):
                d = per(x, a, b)
                print(f" {s:<9} {lab:<22} {pl}: {fmt(score(d, sig.loc[d.index], col, cost))}")
    print("\n by year (NIFTY signal -1%, close -> open, gross mean / n / base):")
    for s, x in data.items():
        sig = (x.nret <= -0.01) & x.valid
        rows = []
        for yr, g in x[x.valid].groupby(x.date.dt.year):
            sg = sig.loc[g.index]
            rows.append(f"{yr}:{g.loc[sg, 'on'].mean():+.2%}/{int(sg.sum())}/{g.loc[~sg, 'on'].mean():+.2%}")
        print(f" {s}: " + "  ".join(rows))


if __name__ == "__main__":
    main()
