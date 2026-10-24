"""
QuantOS — Track B: EUR/USD vs GBP/USD cointegration (docs/NEW_TRACKS_PREREG_2026-10-24.md)
──────────────────────────────────────────────────────────────────────────────────────────
Daily FRED fixes. Each day, on the last 252 observations of x = ln EURUSD and
y = ln GBPUSD: Johansen (r = 0 rejected at 95%), ADF on s = x + b·y (p < 0.05),
AR(1) half-life 1..126. Entry when all hold and |z| > 1.5; b, L and the half-life
freeze at entry; exit when z crosses 0 or after 4 half-lives. One unit = $10,000
in EUR and b × $10,000 in GBP, held as fixed currency amounts, with carry from
policy-rate differentials and 4-pip (Stressed) or 1-pip (Base) costs per leg per side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from core.backtest.evaluator import EvalTrade

WINDOW = 252
ENTRY_Z = 1.5
HL_MIN, HL_MAX = 1.0, 126.0
L_MIN, L_MAX = 5, 126
MAX_HOLD_HL = 4
UNIT_USD = 10_000.0
MARGIN = 0.035
BROKERAGE_INR = 20.0
PIPS = {"stressed": 0.0004, "base": 0.0001}
SERIES = ("DEXUSEU", "DEXUSUK", "DEXINUS", "DFF", "ECBDFR", "IUDSOIA")
CACHE = Path("data_cache/fx")
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def load(cache: Path = CACHE, refresh: bool = False) -> pd.DataFrame:
    """Daily frame: eur, gbp (USD per unit), inr (INR per USD), r_usd, r_eur, r_gbp (% a year).
    FX rows only on days both EUR and GBP fixed; rates forward-filled."""
    cache.mkdir(parents=True, exist_ok=True)
    cols = {}
    for sid in SERIES:
        p = cache / f"{sid}.csv"
        if refresh or not p.exists():
            import urllib.request
            with urllib.request.urlopen(FRED.format(sid), timeout=60) as r:
                p.write_bytes(r.read())
        s = pd.read_csv(p)
        s.columns = ["date", sid]
        s["date"] = pd.to_datetime(s["date"])
        s[sid] = pd.to_numeric(s[sid], errors="coerce")
        cols[sid] = s.set_index("date")[sid]
    df = pd.concat(cols, axis=1).sort_index()
    df[["DEXINUS", "DFF", "ECBDFR", "IUDSOIA"]] = df[["DEXINUS", "DFF", "ECBDFR", "IUDSOIA"]].ffill()
    df = df.dropna(subset=["DEXUSEU", "DEXUSUK", "DEXINUS"])
    df = df.rename(columns={"DEXUSEU": "eur", "DEXUSUK": "gbp", "DEXINUS": "inr",
                            "DFF": "r_usd", "ECBDFR": "r_eur", "IUDSOIA": "r_gbp"})
    return df.fillna({"r_usd": 0.0, "r_eur": 0.0, "r_gbp": 0.0})


@dataclass
class Fit:
    ok: bool
    b: float = float("nan")
    hl: float = float("nan")
    trace_ok: bool = False
    adf_p: float = float("nan")


def fit(x: np.ndarray, y: np.ndarray) -> Fit:
    from statsmodels.tsa.stattools import adfuller
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    j = coint_johansen(np.column_stack([x, y]), det_order=0, k_ar_diff=1)
    trace_ok = bool(j.lr1[0] > j.cvt[0, 1])
    v = j.evec[:, 0]
    if abs(v[0]) < 1e-12:
        return Fit(False, trace_ok=trace_ok)
    b = float(v[1] / v[0])
    s = x + b * y
    adf_p = float(adfuller(s, regression="c", autolag="AIC")[1])
    ds, lag = np.diff(s), s[:-1]
    X = np.column_stack([np.ones_like(lag), lag])
    phi = float(np.linalg.lstsq(X, ds, rcond=None)[0][1])
    hl = -math.log(2) / math.log(1 + phi) if -1 < phi < 0 else float("inf")
    ok = trace_ok and adf_p < 0.05 and HL_MIN <= hl <= HL_MAX
    return Fit(ok, b, hl, trace_ok, adf_p)


def zscore(s_hist: np.ndarray, L: int) -> float:
    w = s_hist[-L:]
    sd = w.std(ddof=1)
    return float((w[-1] - w.mean()) / sd) if sd > 0 else 0.0


@dataclass
class Position:
    side: int          # +1 long spread, -1 short
    i0: int
    b: float
    L: int
    hl: float
    units_e: float     # EUR held (signed, includes side)
    units_g: float     # GBP held (signed)


def _usd_cost(units_e: float, units_g: float, pip: float) -> float:
    return pip * (abs(units_e) + abs(units_g))


def run(df: pd.DataFrame, scenario: str = "stressed", start: date = date(2000, 1, 3)) -> tuple[list[EvalTrade], dict]:
    pip = PIPS[scenario]
    x, y = np.log(df["eur"].to_numpy()), np.log(df["gbp"].to_numpy())
    E, G, R = df["eur"].to_numpy(), df["gbp"].to_numpy(), df["inr"].to_numpy()
    ru, re_, rg = df["r_usd"].to_numpy(), df["r_eur"].to_numpy(), df["r_gbp"].to_numpy()
    dates = [d.date() for d in df.index]
    trades: list[EvalTrade] = []
    counts = {"days": 0, "fit_ok": 0, "signals": 0}
    pos = None
    for i in range(WINDOW - 1, len(df)):
        if dates[i] < start:
            continue
        counts["days"] += 1
        if pos is None:
            f = fit(x[i - WINDOW + 1:i + 1], y[i - WINDOW + 1:i + 1])
            if not f.ok:
                continue
            counts["fit_ok"] += 1
            L = int(min(L_MAX, max(L_MIN, round(f.hl))))
            z = zscore(x[i - L + 1:i + 1] + f.b * y[i - L + 1:i + 1], L)
            if abs(z) <= ENTRY_Z:
                continue
            counts["signals"] += 1
            side = 1 if z < -ENTRY_Z else -1
            pos = Position(side, i, f.b, L, f.hl, side * UNIT_USD / E[i], side * f.b * UNIT_USD / G[i])
            pos.marks, pos.usd_pnl_inr = {}, 0.0
            pos.margin = MARGIN * (abs(pos.units_e) * E[i] + abs(pos.units_g) * G[i]) * R[i]
            pos.entry_cost = _usd_cost(pos.units_e, pos.units_g, pip) * R[i] + 2 * BROKERAGE_INR
            pos.marks[dates[i]] = -(pos.entry_cost + _usd_cost(pos.units_e, pos.units_g, pip) * R[i]
                                    + 2 * BROKERAGE_INR) / pos.margin
            continue
        days = (dates[i] - dates[i - 1]).days
        move = pos.units_e * (E[i] - E[i - 1]) + pos.units_g * (G[i] - G[i - 1])
        carry = (pos.units_e * E[i - 1] * (re_[i - 1] - ru[i - 1])
                 + pos.units_g * G[i - 1] * (rg[i - 1] - ru[i - 1])) / 100 * days / 365
        pos.usd_pnl_inr += (move + carry) * R[i]
        exit_cost = _usd_cost(pos.units_e, pos.units_g, pip) * R[i] + 2 * BROKERAGE_INR
        pos.marks[dates[i]] = (pos.usd_pnl_inr - pos.entry_cost - exit_cost) / pos.margin
        z = zscore(x[i - pos.L + 1:i + 1] + pos.b * y[i - pos.L + 1:i + 1], pos.L)
        crossed = z >= 0 if pos.side > 0 else z <= 0
        if crossed or i - pos.i0 >= math.ceil(MAX_HOLD_HL * pos.hl) or i == len(df) - 1:
            trades.append(EvalTrade(dates[pos.i0], dates[i], pos.margin, pos.marks,
                                    f"{'long' if pos.side > 0 else 'short'} b={pos.b:.3f} hl={pos.hl:.1f}"))
            pos = None
    return trades, counts
