"""Shorts: close below ET's S2 / S3 (prior session P - (H-L) / P - 2(H-L)) and the user's Pivot Compression
rule mirrored (5-EMA under the monthly pivot, under the 40-SMA, CCI under its 52-SMA, 1.2x volume on a red bar).
Next day and 5 days, F&O stocks 2021-26, vs every stock-day. Split: downtrend = close < 200-SMA and the 200-SMA
lower than 20 sessions ago. For shorts a NEGATIVE move is the gain."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, r"d:\Exodus_14_14\QuantOS\quantos"); sys.path.insert(0, str(Path(__file__).parent))
from core.market_map.l1_store import Store
import pivot_compression_breakout as pcb
st = Store(Path.home() / ".quantos/l1_snap_20261113")
m = pd.read_csv(Path.home() / ".quantos/fyers_symbol_master_NSE_FO.csv", header=None, low_memory=False)
und = set(m[m[1].astype(str).str.endswith("FUT")][13].astype(str))
syms = sorted(und & set(st.symbols()) - {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"})
rows = []
for s in syms:
    a, _ = st.adjusted(s); a = a.reset_index(drop=True); a["date"] = pd.to_datetime(a["date"])
    if len(a) < 300: continue
    P = (a.h + a.l + a.c).shift(1) / 3; R = (a.h - a.l).shift(1)
    x = pcb.signals(a)
    xd = lambda u, v: (u < v) & (u.shift(1) >= v.shift(1))
    ema, sma, cc, ccm, piv = x["ema5"], x["sma40"], x["cci"], x["cci_ma"], x["pivot"]
    short_setup = (x["tight"].astype(bool) & (ema < piv) & (ema.rolling(5).max() >= piv) & (ema < sma) & (pcb.barssince(xd(ema, sma)) <= 5)
                   & (cc < ccm) & (pcb.barssince(xd(cc, ccm)) <= 5) & (a.vol > a.vol.rolling(50).mean() * 1.2) & (a.c < a.o)).fillna(False)
    s200 = a.c.rolling(200).mean()
    nx = a.shift(-1)
    d = pd.DataFrame(dict(sym=s, date=a.date, gap=nx.o / a.c - 1, cc=nx.c / a.c - 1, oc=nx.c / nx.o - 1,
        c5=a.c.shift(-5) / a.c - 1, c10=a.c.shift(-10) / a.c - 1,
        down=(a.c < s200) & (s200 < s200.shift(20)),
        S2=(a.c < P - R) & ~(a.c.shift(1) < (P - R).shift(1)),
        S3=(a.c < P - 2 * R) & ~(a.c.shift(1) < (P - 2 * R).shift(1)),
        PCB_short=short_setup & ~short_setup.shift(1, fill_value=False)))
    rows.append(d[(d.date >= "2021-01-01") & d.c10.notna()])
b = pd.concat(rows)
def line(x, lab):
    print(f"{lab:<34} n {len(x):>6}  gap {x.gap.mean():+.2%}  close-close {x.cc.mean():+.2%}  down next day {(x.cc<0).mean():.0%}  "
          f"open-close {x.oc.mean():+.2%}  5d {x.c5.mean():+.2%}  10d {x.c10.mean():+.2%}")
H = (("2021-23", ("2021", "2024")), ("2024-26", ("2024", "2027")))
for h, (lo, hi) in H:
    line(b[(b.date >= lo) & (b.date < hi)], f"every stock-day {h}")
for sig in ("S2", "S3", "PCB_short"):
    e = b[b[sig]]
    print(f"\n== {sig}")
    for h, (lo, hi) in H:
        u = e[(e.date >= lo) & (e.date < hi)]
        line(u, f"  all {h}"); line(u[u.down], f"  in a downtrend {h}"); line(u[~u.down], f"  not in a downtrend {h}")
