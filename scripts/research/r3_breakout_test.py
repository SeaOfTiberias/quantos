"""Close above R3 / below S3, as pre-registered in docs/R3_BREAKOUT_PREREG_2026-11-17.md (1a545bd)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, r"d:\Exodus_14_14\QuantOS\quantos")
from core.market_map.l1_store import Store

H = Path(__file__).parent
st = Store(Path.home() / ".quantos/l1_snap_20261113")
m = pd.read_csv(Path.home() / ".quantos/fyers_symbol_master_NSE_FO.csv", header=None, low_memory=False)
und = set(m[m[1].astype(str).str.endswith("FUT")][13].astype(str))
syms = sorted(und & set(st.symbols()) - {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"})
nifty = pd.read_csv(H / "index_bars/NIFTY.csv", parse_dates=["date"]).set_index("date")["c"]
n_up = nifty > nifty.rolling(50).mean()

data, opens, closes = {}, {}, {}
for s in syms:
    a, _ = st.adjusted(s)
    a = a.reset_index(drop=True)
    a["date"] = pd.to_datetime(a["date"])
    if len(a) < 300:
        continue
    data[s] = a
    opens[s] = a.set_index("date")["o"]
    closes[s] = a.set_index("date")["c"]
O = pd.DataFrame(opens).sort_index()
C = pd.DataFrame(closes).sort_index()
ew10 = (C.shift(-10) / O.shift(-1) - 1).mean(axis=1)
print("universe", len(data), flush=True)


def trade(a, i, sg, e, stop):
    risk = sg * (e - stop)
    if risk <= 0:
        return None
    tg = e + sg * 2 * risk
    for j in range(i + 1, i + 16):
        if (a.at[j, "l"] <= stop) if sg > 0 else (a.at[j, "h"] >= stop):
            return -1.0
        if (a.at[j, "h"] >= tg) if sg > 0 else (a.at[j, "l"] <= tg):
            return 2.0
    return sg * (a.at[i + 15, "c"] - e) / risk


out = []
for n, (s, a) in enumerate(data.items()):
    P = (a["h"] + a["l"] + a["c"]).shift(1) / 3
    R = (a["h"] - a["l"]).shift(1)
    r3, s3 = P + 2 * R, P - 2 * R
    pc = a["c"].shift(1)
    atr = pd.concat([a["h"] - a["l"], (a["h"] - pc).abs(), (a["l"] - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    hi55 = a["c"] > a["c"].shift(1).rolling(55).max()
    for side, sg, sig in (("CE", 1, a["c"] > r3), ("PE", -1, a["c"] < s3)):
        first = sig & ~sig.shift(1, fill_value=False)
        for i in a.index[first & (a["date"] >= "2021-01-01")]:
            if i + 16 >= len(a) or pd.isna(atr[i]):
                continue
            stop = (a.at[i, "l"] - 0.1 * atr[i]) if sg > 0 else (a.at[i, "h"] + 0.1 * atr[i])
            Ro = trade(a, i, sg, a.at[i + 1, "o"], stop)
            Rc = trade(a, i, sg, a.at[i, "c"], stop)
            if Ro is None:
                continue
            d = a.at[i, "date"]
            e = a.at[i + 1, "o"]
            ex10 = sg * (a.at[i + 11, "c"] / e - 1 - ew10.get(d, np.nan)) - 0.0025 if i + 11 < len(a) else np.nan
            nb = hi55.iloc[i + 1:i + 21]
            f = nb.idxmax() if nb.any() else None
            out.append(dict(side=side, sym=s, d=d.date().isoformat(), R=Ro, R_close=Rc, ex10=ex10,
                            risk_pct=sg * (e - stop) / e, nifty_up=bool(n_up.asof(d)),
                            hi55_now=bool(hi55.iloc[i]), hi55_20=f is not None,
                            hi55_days=(f - i) if f is not None else np.nan,
                            hi55_gain=(a.at[f, "c"] / a.at[i, "c"] - 1) if f is not None else np.nan))
    if n % 40 == 0:
        print(f"{n+1}/{len(data)} {s} rows {len(out)}", flush=True)

r = pd.DataFrame(out)
r.to_csv(H / "q8.csv", index=False)
for side in ("CE", "PE"):
    v = r[r.side == side]
    print(f"\n== {side}: n {len(v)}  mean R {v.R.mean():+.2f}  win {(v.R > 0).mean():.0%}  ex10 {v.ex10.mean():+.2%}  "
          f"median risk {v.risk_pct.median():.1%}")
    for h, (lo, hi) in (("2021-23", ("2021", "2024")), ("2024-26", ("2024", "2027"))):
        u = v[(v.d >= lo) & (v.d < hi)]
        print(f"   {h}: n {len(u)}  mean R {u.R.mean():+.2f}  win {(u.R > 0).mean():.0%}  ex10 {u.ex10.mean():+.2%}")
    for lab, b in (("NIFTY above 50-day mean", True), ("NIFTY below 50-day mean", False)):
        u = v[v.nifty_up == b]
        print(f"   {lab}: n {len(u)}  mean R {u.R.mean():+.2f}  ex10 {u.ex10.mean():+.2%}")
    print(f"   entered at the signal close instead: mean R {v.R_close.mean():+.2f}")
    if side == "CE":
        nb = v[~v.hi55_now]
        print(f"   already a 55-day closing high: {v.hi55_now.mean():.0%}; of the rest ({len(nb)}): one within 20 sessions "
              f"{nb.hi55_20.mean():.0%}, median {nb.hi55_days.median():.0f} sessions, gain to it {nb.hi55_gain.median():+.1%}")
