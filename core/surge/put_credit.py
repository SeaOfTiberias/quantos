"""
QuantOS — Track A: bull put credit spreads on non-52-week-high surges
──────────────────────────────────────────────────────────────────────
docs/NEW_TRACKS_PREREG_2026-10-24.md, track A. Candidate 23's events
(core/surge/events.py), gated on IV rank >= 0.70 of the stock's daily ATM IV.
Sell the ~35-delta put, buy the ~12.5-delta put below it, in the nearest expiry
with >= 10 trading days; take profit at 50% of the credit, stop at a loss of
1.5 x credit, else out at the close of the last trading day before expiry.
Daily closes only (close, else settlement, else intrinsic from the futures).

Data passes over the cached NSE F&O bhavcopy zips:
  pass 1  every day: futures closes per expiry, and the ATM CE/PE of the IV expiry
          (nearest with >= 5 trading days) for every panel symbol -> daily ATM IV
  pass 2  the gated events only: every PE row of the chosen expiry, entry to exit
"""

from __future__ import annotations

import io
import math
import zipfile
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from core.backtest.evaluator import EvalTrade
from core.options.vrp.bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR
from core.statarb.data import SYMBOL_RENAMES
from core.surge.spreads import FALLBACK_NOTIONAL, TICK, bidask_cost, statutory_cost

IV_MIN_TDAYS = 5
TRADE_MIN_TDAYS = 10
IVR_GATE = 0.70
IVR_WINDOW = 252
IVR_MIN_OBS = 200
SHORT_D, SHORT_BAND = 0.35, (0.30, 0.40)
LONG_D, LONG_BAND = 0.125, (0.10, 0.15)
TAKE_PROFIT = 0.50
STOP_MULT = 2.5                 # spread value at which the loss is 1.5 x credit
SCENARIOS = {"stressed": 0.02, "base": 0.01}
CACHE = Path("data_cache/surge")


# ─── Black-76 ────────────────────────────────────────────────────────────────

def _ncdf(x):
    from scipy.special import ndtr
    return ndtr(x)


def b76(F, K, T, vol, put):
    F, K, T, vol = (np.asarray(a, float) for a in (F, K, T, vol))
    sd = vol * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    call = F * _ncdf(d1) - K * _ncdf(d2)
    return np.where(put, call - F + K, call)


def b76_delta(F, K, T, vol, put):
    F, K, T, vol = (np.asarray(a, float) for a in (F, K, T, vol))
    sd = vol * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd * sd) / sd
    return np.where(put, _ncdf(d1) - 1.0, _ncdf(d1))


def b76_iv(price, F, K, T, put, lo=0.01, hi=5.0, iters=60):
    """Vectorised bisection; NaN where the price is outside (intrinsic, the vol-5 price)."""
    price, F, K, T = (np.asarray(a, float) for a in (price, F, K, T))
    put = np.asarray(put, bool)
    intrinsic = np.where(put, np.maximum(K - F, 0), np.maximum(F - K, 0))
    a, b = np.full(price.shape, lo), np.full(price.shape, hi)
    valid = (price > intrinsic + 1e-9) & (T > 0) & (F > 0) & (K > 0) & (price < b76(F, K, T, b, put))
    for _ in range(iters):
        m = 0.5 * (a + b)
        high = b76(F, K, T, m, put) > price
        b, a = np.where(high, m, b), np.where(high, a, m)
    return np.where(valid, 0.5 * (a + b), np.nan)


def years(d: date, expiry: date) -> float:
    return max((expiry - d).days, 1) / 365.0


# ─── bhavcopy parsing ────────────────────────────────────────────────────────

_OLD_NAME = {new: old for old, new in SYMBOL_RENAMES.items()}


def parse_day(path: Path, d: date, symbols: set[str]) -> pd.DataFrame:
    """Stock futures and option rows for `symbols`: symbol, kind (FUT/CE/PE), expiry, strike,
    close, settle, contracts, lot."""
    lookup = set(symbols) | {_OLD_NAME[s] for s in symbols if s in _OLD_NAME}
    with zipfile.ZipFile(path) as z:
        df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), dtype=str, keep_default_na=False)
    if d >= CUTOVER_DATE:
        df = df[df["FinInstrmTp"].isin(["STO", "STF"]) & df["TckrSymb"].isin(lookup)]
        out = pd.DataFrame({
            "symbol": df["TckrSymb"].str.strip(),
            "kind": np.where(df["FinInstrmTp"] == "STF", "FUT", df["OptnTp"].str.strip()),
            "expiry": pd.to_datetime(df["XpryDt"]).dt.date,
            "strike": pd.to_numeric(df["StrkPric"], errors="coerce").fillna(0.0),
            "close": pd.to_numeric(df["ClsPric"], errors="coerce"),
            "settle": pd.to_numeric(df["SttlmPric"], errors="coerce"),
            "contracts": pd.to_numeric(df["TtlTradgVol"], errors="coerce").fillna(0),
            "lot": pd.to_numeric(df["NewBrdLotQty"], errors="coerce").fillna(0).astype(int),
        })
    else:
        inst = df["INSTRUMENT"].str.strip()
        df = df[inst.isin(["OPTSTK", "FUTSTK"]) & df["SYMBOL"].str.strip().isin(lookup)]
        out = pd.DataFrame({
            "symbol": df["SYMBOL"].str.strip(),
            "kind": np.where(df["INSTRUMENT"].str.strip() == "FUTSTK", "FUT", df["OPTION_TYP"].str.strip()),
            "expiry": pd.to_datetime(df["EXPIRY_DT"], format="%d-%b-%Y").dt.date,
            "strike": pd.to_numeric(df["STRIKE_PR"], errors="coerce").fillna(0.0),
            "close": pd.to_numeric(df["CLOSE"], errors="coerce"),
            "settle": pd.to_numeric(df["SETTLE_PR"], errors="coerce"),
            "contracts": pd.to_numeric(df["CONTRACTS"], errors="coerce").fillna(0),
            "lot": 0,
        })
    out["symbol"] = out["symbol"].map(lambda s: SYMBOL_RENAMES.get(s, s))
    return out


def price_of(close, settle, contracts) -> Optional[float]:
    if contracts > 0 and close and close > 0:
        return float(close)
    if settle and settle > 0:
        return float(settle)
    return None


class Calendar:
    def __init__(self, days: list[date]):
        self.days = sorted(days)
        self.pos = {d: i for i, d in enumerate(self.days)}

    def tdays_after(self, d: date, expiry: date) -> int:
        """Trading days after d up to and including expiry (weekdays beyond the calendar's end)."""
        n = bisect_right(self.days, expiry) - bisect_right(self.days, d)
        if expiry > self.days[-1]:
            extra = pd.bdate_range(self.days[-1], expiry).size - 1
            n += max(extra, 0)
        return n

    def last_before(self, expiry: date) -> Optional[date]:
        k = bisect_right(self.days, expiry) - 1
        while k >= 0 and self.days[k] >= expiry:
            k -= 1
        return self.days[k] if k >= 0 and expiry <= self.days[-1] else None


def pick_expiry(expiries, d: date, cal: Calendar, min_tdays: int) -> Optional[date]:
    ok = sorted(e for e in set(expiries) if e > d and cal.tdays_after(d, e) >= min_tdays)
    return ok[0] if ok else None


def pass1_day(args) -> tuple[list, list]:
    """One day: (futures rows, ATM IV row per symbol)."""
    path, d, symbols, cal_days = args
    cal = Calendar(cal_days)
    df = parse_day(path, d, symbols)
    fut = df[df["kind"] == "FUT"]
    futs = [(d, r.symbol, r.expiry, float(r.close if r.close > 0 else r.settle)) for r in fut.itertuples()
            if (r.close > 0 or r.settle > 0)]
    fmap = {(s, e): c for _, s, e, c in futs}
    near = {}
    for _, s, e, c in sorted(futs, key=lambda x: x[2]):
        near.setdefault(s, c)
    ivs = []
    opts = df[df["kind"].isin(["CE", "PE"])]
    for sym, g in opts.groupby("symbol"):
        e = pick_expiry(g["expiry"], d, cal, IV_MIN_TDAYS)
        if e is None:
            continue
        F = fmap.get((sym, e), near.get(sym))
        if not F:
            continue
        ge = g[g["expiry"] == e]
        strikes = sorted(set(ge["strike"]))
        if not strikes:
            continue
        K = min(strikes, key=lambda k: (abs(k - F), k))
        row = {}
        for kind in ("CE", "PE"):
            x = ge[(ge["strike"] == K) & (ge["kind"] == kind)]
            if len(x):
                r = x.iloc[0]
                row[kind] = price_of(r.close, r.settle, r.contracts)
        if row.get("CE") and row.get("PE"):
            ivs.append((d, sym, e, F, K, row["CE"], row["PE"]))
    return futs, ivs


def pass2_day(args) -> list:
    path, d, wanted = args          # wanted: {symbol: set(expiries)}
    df = parse_day(path, d, set(wanted))
    df = df[(df["kind"] == "PE")]
    keep = [w for w in df.itertuples() if w.expiry in wanted.get(w.symbol, ())]
    return [(d, r.symbol, r.expiry, r.strike, r.close, r.settle, r.contracts, r.lot) for r in keep]


def atm_iv(ivrows: pd.DataFrame) -> pd.DataFrame:
    T = np.array([years(d, e) for d, e in zip(ivrows["date"], ivrows["expiry"])])
    ce = b76_iv(ivrows["ce"], ivrows["F"], ivrows["K"], T, False)
    pe = b76_iv(ivrows["pe"], ivrows["F"], ivrows["K"], T, True)
    out = ivrows[["date", "symbol"]].copy()
    out["iv"] = np.nanmean(np.vstack([ce, pe]), axis=0)
    return out


def iv_rank(iv: pd.DataFrame) -> dict:
    """{(symbol, date): rank} over sessions t-251..t, needing >= 200 valid IVs."""
    out = {}
    for sym, g in iv.sort_values("date").groupby("symbol"):
        v = g["iv"].to_numpy()
        ds = list(g["date"])
        for i in range(len(v)):
            w = v[max(0, i - IVR_WINDOW + 1):i + 1]
            w = w[~np.isnan(w)]
            if len(w) < IVR_MIN_OBS or np.isnan(v[i]):
                continue
            lo, hi = w.min(), w.max()
            if hi > lo:
                out[(sym, ds[i])] = float((v[i] - lo) / (hi - lo))
    return out


# ─── trades ──────────────────────────────────────────────────────────────────

@dataclass
class PutTrade:
    symbol: str
    entry: date
    exit: date
    expiry: date
    short_k: float
    long_k: float
    credit: float
    width: float
    lot: int
    reason: str
    marks: dict           # scenario -> {date: net return on max loss}

    def eval_trade(self, scenario: str) -> EvalTrade:
        return EvalTrade(self.entry, self.exit, (self.width - self.credit) * self.lot,
                         self.marks[scenario], f"{self.symbol} {self.entry}")


def choose_strikes(chain: pd.DataFrame, F: float, d: date, e: date) -> Optional[tuple]:
    """chain: PE rows of (symbol, e) on d. -> (short row, long row) by delta, or None."""
    c = chain[(chain["contracts"] > 0) & (chain["close"] > 0)].copy()
    if c.empty:
        return None
    T = years(d, e)
    c["iv"] = b76_iv(c["close"], F, c["strike"], T, True)
    c = c.dropna(subset=["iv"])
    if c.empty:
        return None
    c["delta"] = -b76_delta(F, c["strike"], T, c["iv"], True)        # |put delta|
    sh = c[(c["delta"] >= SHORT_BAND[0]) & (c["delta"] <= SHORT_BAND[1])]
    if sh.empty:
        return None
    s = sh.iloc[(sh["delta"] - SHORT_D).abs().argsort().iloc[0]]
    lg = c[(c["delta"] >= LONG_BAND[0]) & (c["delta"] <= LONG_BAND[1]) & (c["strike"] < s["strike"])]
    if lg.empty:
        return None
    lo = lg.iloc[(lg["delta"] - LONG_D).abs().argsort().iloc[0]]
    return s, lo


def walk(sym: str, d0: date, e: date, short_k: float, long_k: float, credit: float, lot: int,
         rows: dict, futs: dict, cal: Calendar) -> tuple[Optional[date], dict, str, Counter]:
    """Daily marks from the entry close to the exit. rows[(date, strike)] -> (close, settle, contracts);
    futs[(date)] -> futures close for (sym, e). Returns (exit date, {date: (v_short, v_long)}, reason, fallbacks)."""
    last = cal.last_before(e)
    fb = Counter()
    if last is None:
        return None, {}, "open at data end", fb
    vals = {}
    for d in cal.days[cal.pos[d0]:cal.pos[last] + 1]:
        legs = []
        for k in (short_k, long_k):
            r = rows.get((d, k))
            p = price_of(*r) if r else None
            if r and p is not None and not (r[2] > 0 and r[0] > 0):
                fb["settle"] += 1
            if p is None:
                F = futs.get(d)
                if F is None:
                    legs = None
                    break
                p = max(k - F, 0.0)
                fb["intrinsic"] += 1
            legs.append(p)
        if legs is None:
            continue
        vals[d] = tuple(legs)
        if d == d0:
            continue
        v = legs[0] - legs[1]
        if v <= TAKE_PROFIT * credit:
            return d, vals, "take profit", fb
        if v >= STOP_MULT * credit:
            return d, vals, "stop", fb
    return last, vals, "time", fb


def marks_for(entry: date, credit: float, width: float, lot: int, p_short: float, p_long: float,
              vals: dict, c: float) -> dict:
    """Net return on max loss if closed at each close: credit - value - costs (statutory + bid-ask)."""
    risk = width - credit
    out = {}
    for d, (vs, vl) in sorted(vals.items()):
        gross = credit - (vs - vl)
        stat = statutory_cost(p_long, p_short, vl, vs, lot, entry, d)
        ba = bidask_cost((p_short, p_long, vs, vl), c)
        out[d] = (gross - stat - ba) / risk
    return out
