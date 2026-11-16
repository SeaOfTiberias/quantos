"""Pivot Compression Breakout, ported 1:1 from the user's Pine v2.0 (USER;649b64c9..., 2026-11-17).
Defaults: tight 3%, EMA 5, SMA 40, CCI 34 on hlc3, CCI MA 52, volume 1.2 x 50-SMA, window 5."""
import pandas as pd
import numpy as np


def cci(src, n):
    m = src.rolling(n).mean()
    md = src.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (src - m) / (0.015 * md)


def barssince(cond):
    idx = pd.Series(np.where(cond, np.arange(len(cond)), np.nan), index=cond.index).ffill()
    return pd.Series(np.arange(len(cond)), index=cond.index) - idx


def signals(a, tight=0.03, ema_n=5, sma_n=40, cci_n=34, cci_ma=52, vol_mult=1.2, lb=5):
    a = a.reset_index(drop=True)
    a["date"] = pd.to_datetime(a["date"])
    mo = a.set_index("date").resample("MS").agg(dict(h="max", l="min", c="last")).dropna()
    piv = (mo["h"] + mo["l"] + mo["c"]) / 3
    month = a["date"].dt.to_period("M").dt.to_timestamp()
    pm = piv.shift(1)          # last completed month
    pm2 = piv.shift(2)
    curr = month.map(pm)
    prev = month.map(pm2)
    ema = a["c"].ewm(span=ema_n, adjust=False).mean()
    sma = a["c"].rolling(sma_n).mean()
    hlc3 = (a["h"] + a["l"] + a["c"]) / 3
    cc = cci(hlc3, cci_n)
    ccm = cc.rolling(cci_ma).mean()
    vs = a["vol"].rolling(50).mean()
    xo = lambda x, y: (x > y) & (x.shift(1) <= y.shift(1))
    tight_ok = (curr - prev).abs() / curr <= tight
    ema_piv = (ema > curr) & (ema.rolling(lb).min() <= curr)
    ema_40 = (ema > sma) & (barssince(xo(ema, sma)) <= lb)
    cci_ok = (cc > ccm) & (barssince(xo(cc, ccm)) <= lb)
    vol_ok = (a["vol"] > vs * vol_mult) & (a["c"] > a["o"])
    setup = (tight_ok & ema_piv & ema_40 & cci_ok & vol_ok).fillna(False)
    day1 = setup & ~setup.shift(1, fill_value=False)
    return a.assign(pivot=curr, prev_pivot=prev, ema5=ema, sma40=sma, cci=cc, cci_ma=ccm,
                    tight=tight_ok, ema_piv=ema_piv, ema_40=ema_40, cci_ok=cci_ok, vol_ok=vol_ok,
                    setup=setup, day1=day1)
