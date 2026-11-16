"""Pivot Compression Breakout test, as pre-registered in docs/PIVOT_COMPRESSION_BREAKOUT_PREREG_2026-11-17.md (0882245)."""
import sys
from datetime import timedelta
from pathlib import Path
import pandas as pd
sys.path.insert(0, r"d:\Exodus_14_14\QuantOS\quantos")
sys.path.insert(0, str(Path(__file__).parent))
from core.market_map.l1_store import Store
from core.market_map import structure, card as cd, call_plan as cp
import pivot_compression_breakout as pcb

H = Path(__file__).parent
st = Store(Path.home() / ".quantos/l1_snap_20261113")
m = pd.read_csv(Path.home() / ".quantos/fyers_symbol_master_NSE_FO.csv", header=None, low_memory=False)
und = set(m[m[1].astype(str).str.endswith("FUT")][13].astype(str))
syms = sorted(und & set(st.symbols()) - {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"})
print("universe", len(syms), flush=True)

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
ew10 = (C.shift(-10) / O.shift(-1) - 1).mean(axis=1)        # EW universe, next open -> close 10 sessions on
dates = C.index

VARIANTS = {"rule": ["tight", "ema_piv", "ema_40", "cci_ok", "vol_ok"]}
for drop in ("vol_ok", "ema_40", "tight"):
    VARIANTS[f"no_{drop}"] = [c for c in VARIANTS["rule"] if c != drop]

out = []
for n, s in enumerate(data):
    a = data[s]
    x = pcb.signals(a)
    pc = a["c"].shift(1)
    atr = pd.concat([a["h"] - a["l"], (a["h"] - pc).abs(), (a["l"] - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    x52 = a["c"].shift(1).rolling(55).max()
    brk55 = a["c"] > x52
    for var, conds in VARIANTS.items():
        setup = x[conds].fillna(False).all(axis=1)
        day1 = setup & ~setup.shift(1, fill_value=False)
        for i in a.index[day1 & (a["date"] >= "2021-01-01")]:
            if i + 16 >= len(a):
                continue
            e = a.at[i + 1, "o"]
            stop = a.at[i, "l"] - 0.1 * atr[i]
            risk = e - stop
            if risk <= 0:
                continue
            tg = None
            if var == "rule":
                sub = a.iloc[:i + 1]
                try:
                    c = cd.card(s, structure.l1_read(sub, a.at[i, "date"].date() + timedelta(days=1)), sub)
                    tg = (cp.target(c, "CE") or {}).get("level")
                except Exception:
                    tg = None
            if tg is None or tg - e < risk:
                tg = e + 2 * risk
            R = None
            for j in range(i + 1, i + 16):
                if a.at[j, "l"] <= stop:
                    R = -1.0; break
                if a.at[j, "h"] >= tg:
                    R = (tg - e) / risk; break
            if R is None:
                R = (a.at[i + 15, "c"] - e) / risk
            d = a.at[i, "date"]
            ex10 = None
            if i + 11 < len(a):
                ex10 = a.at[i + 11, "c"] / e - 1 - ew10.get(d, float("nan")) - 0.0025
            nb = brk55.iloc[i + 1:i + 21]
            first = nb.idxmax() if nb.any() else None
            out.append(dict(var=var, sym=s, d=d.date().isoformat(), R=R, ex10=ex10, risk_pct=risk / e,
                            brk20=first is not None, brk_days=(first - i) if first is not None else None,
                            brk_gain=(a.at[first, "c"] / a.at[i, "c"] - 1) if first is not None else None,
                            brk_already=bool(brk55.iloc[i])))
    if n % 20 == 0:
        print(f"{n+1}/{len(data)} {s} rows {len(out)}", flush=True)

r = pd.DataFrame(out)
r.to_csv(H / "q7.csv", index=False)
for var in VARIANTS:
    v = r[r["var"] == var]
    print(f"\n== {var}: n {len(v)}  mean R {v.R.mean():.2f}  win {(v.R > 0).mean():.0%}  "
          f"ex10 after cost {v.ex10.mean():+.2%}  median risk {v.risk_pct.median():.1%}")
    for h, (lo, hi) in (("2021-23", ("2021", "2024")), ("2024-26", ("2024", "2027"))):
        u = v[(v.d >= lo) & (v.d < hi)]
        print(f"   {h}: n {len(u)}  mean R {u.R.mean():.2f}  win {(u.R > 0).mean():.0%}  ex10 {u.ex10.mean():+.2%}")
    if var == "rule":
        print(f"   signal day already a 55-day closing high: {v.brk_already.mean():.0%}")
        nb = v[~v.brk_already]
        print(f"   of the rest ({len(nb)}): 55-day high within 20 sessions {nb.brk20.mean():.0%}, "
              f"median {nb.brk_days.median():.0f} sessions, median gain signal close -> that close {nb.brk_gain.median():+.1%}")
