"""Run: python scripts/gutcheck_earnings_gap_drift.py  (results: docs/EARNINGS_GAP_DRIFT_GUTCHECK.md)

Earnings-gap drift gut-check on NSE F&O stocks, 2016-01 .. 2026-06.

Pre-registered (written before any result was seen):
  event  : close/prevclose - 1 >= +5% (up) or <= -5% (down) AND volume >= 4x
           the trailing 50-session average volume (excluding the day itself)
  universe: today's 213 F&O stocks (survivorship bias: favours up-drift), price >= 50
  dedupe : at most one event per stock per 20 sessions (first one kept)
  entry  : close of event day + 1 (what a trader can realistically get)
  measure: forward return over 5/10/20 sessions from entry, minus the equal-weight
           average of the universe over the same window (market-adjusted)
  split  : 2016-2020 vs 2021-2026 must agree in sign to call it real
"""
import glob, io, sys, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data_cache" / "pead_nse" / "eq_bhavcopy_raw"
HERE = REPO / "data_cache" / "earnings_gap_drift"
HERE.mkdir(parents=True, exist_ok=True)
CACHE = HERE / "eq_panel.pkl"
UNIVERSE = set((REPO / "agent" / "universe_fno_2026-10-19.txt").read_text().split())


def parse(f):
    z = zipfile.ZipFile(f)
    d = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    if "SYMBOL" in d.columns:
        d = d[d["SERIES"] == "EQ"]
        out = pd.DataFrame({"symbol": d["SYMBOL"], "open": d["OPEN"], "close": d["CLOSE"],
                            "prev": d["PREVCLOSE"], "vol": d["TOTTRDQTY"]})
    else:
        d = d[d["SctySrs"] == "EQ"]
        out = pd.DataFrame({"symbol": d["TckrSymb"], "open": d["OpnPric"], "close": d["ClsPric"],
                            "prev": d["PrvsClsgPric"], "vol": d["TtlTradgVol"]})
    out = out[out["symbol"].isin(UNIVERSE)]
    out["date"] = pd.Timestamp(Path(f).stem)
    return out


if CACHE.exists():
    panel = pd.read_pickle(CACHE)
else:
    parts = []
    for i, f in enumerate(sorted(glob.glob(str(RAW / "*.zip")))):
        try:
            parts.append(parse(f))
        except Exception as e:
            print("skip", f, e, file=sys.stderr)
    panel = pd.concat(parts, ignore_index=True)
    panel.to_pickle(CACHE)
print("panel", panel.shape, panel["date"].min().date(), panel["date"].max().date(), panel["symbol"].nunique(), "symbols")

close = panel.pivot_table(index="date", columns="symbol", values="close")
prev = panel.pivot_table(index="date", columns="symbol", values="prev")
vol = panel.pivot_table(index="date", columns="symbol", values="vol")
ret1 = close / prev - 1                        # uses NSE's own prev close (split-safe on the day)
avgvol = vol.shift(1).rolling(50, min_periods=40).mean()
volx = vol / avgvol

# Forward log-free simple returns from entry (= close at t+1). A split inside the window
# shows up as a huge negative return; drop windows where any single-day |ret1| > 35%
# that is not the event day itself.
crazy = (ret1.abs() > 0.35)
HORIZONS = (5, 10, 20)
fwd, mkt = {}, {}
for h in HORIZONS:
    r = close.shift(-(1 + h)) / close.shift(-1) - 1
    # any |daily move| > 35% on days t+2 .. t+1+h (the holding window)
    bad = crazy.astype(float).rolling(h, min_periods=1).max().shift(-(1 + h)).fillna(0).astype(bool)
    r = r.mask(bad)
    fwd[h] = r
    mkt[h] = r.mean(axis=1)                      # equal-weight universe, same window

events = []
for side, cond in (("up", ret1 >= 0.05), ("down", ret1 <= -0.05)):
    hit = cond & (volx >= 4) & (close >= 50)
    for sym in hit.columns:
        dates = hit.index[hit[sym].fillna(False).values]
        last = None
        idx = close.index
        for d in dates:
            pos = idx.get_loc(d)
            if last is not None and pos - last < 20:
                continue
            last = pos
            row = {"side": side, "symbol": sym, "date": d, "ret": ret1.at[d, sym], "volx": volx.at[d, sym]}
            for h in HORIZONS:
                row[f"r{h}"] = fwd[h].at[d, sym]
                row[f"x{h}"] = fwd[h].at[d, sym] - mkt[h].at[d]
            events.append(row)
ev = pd.DataFrame(events).dropna(subset=["x20"])
ev.to_csv(HERE / "drift_events.csv", index=False)


def summary(df, label):
    out = [f"{label:<26} n={len(df):4d}"]
    for h in HORIZONS:
        x = df[f"x{h}"].dropna()
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else float("nan")
        out.append(f"{h:>2}d excess {100*x.mean():+5.2f}% med {100*x.median():+5.2f}% hit {100*(x>0).mean():4.1f}% t {t:+4.1f}")
    print(" | ".join(out))


for side in ("up", "down"):
    s = ev[ev.side == side]
    print(f"\n=== {side.upper()} events (entry = close of day after) ===")
    summary(s, "all")
    summary(s[s.date.dt.year <= 2020], "2016-2020")
    summary(s[s.date.dt.year >= 2021], "2021-2026")
    summary(s[s.volx >= 8], "volume >= 8x")
    summary(s[s.ret.abs() >= 0.08], "move >= 8%")
    for y, g in s.groupby(s.date.dt.year):
        x = g["x20"].dropna()
        print(f"   {y}: n={len(x):3d} 20d excess {100*x.mean():+5.2f}% hit {100*(x>0).mean():4.1f}%")

# Raw (not market-adjusted) 20d return of a typical 20-session window, for scale
allr = fwd[20].stack()
print(f"\nBaseline: any stock, any day, 20d raw mean {100*allr.mean():+.2f}%  median {100*allr.median():+.2f}%")
