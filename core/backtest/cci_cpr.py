"""
CCI(34)/SMA52 + monthly CPR signal: pure functions for
docs/CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md (Part A).

Every function works on one stock's bars within one price SEGMENT (core/techno_funda/prices.py),
as numpy arrays in date order, so indicators restart at a segment break. The runner
(scripts/backtest_cci_cpr.py) handles the universe, entries, benchmark and statistics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CCI_N, CCI_AVG_N = 34, 52
SLOPE_LAG, SLOPE_TOL = 5, 5.0
SMA_FAST = 5
PAIR_WINDOW = 3
SKIP_SESSIONS = 10


def sma(x: np.ndarray, n: int) -> np.ndarray:
    """Simple moving average; NaN until n valid values. NaNs in x (a warm-up prefix) stay NaN."""
    return pd.Series(x, dtype="float64").rolling(n, min_periods=n).mean().to_numpy()


def cci(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = CCI_N) -> np.ndarray:
    """CCI(n) on typical price: (TP - SMA_n(TP)) / (0.015 x mean absolute deviation over n)."""
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    out = np.full(len(tp), np.nan)
    if len(tp) < n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(tp, n)
    m = w.mean(axis=1)
    md = np.abs(w - m[:, None]).mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(md > 0, (tp[n - 1:] - m) / (0.015 * md), 0.0)
    out[n - 1:] = v
    return out


def wilder_rsi(c: np.ndarray, n: int = 14) -> np.ndarray:
    s = pd.Series(c, dtype="float64")
    d = s.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        return (100 - 100 / (1 + gain / loss)).to_numpy()


def wilder_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def monthly_cpr(dates: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(top, bottom) of the CPR in force on each day, from the PREVIOUS calendar month's high,
    low and close. NaN when the previous calendar month has no bars in this segment."""
    month = pd.DatetimeIndex(dates).to_period("M")
    df = pd.DataFrame({"m": month, "h": h, "l": l, "c": c})
    g = df.groupby("m", sort=True).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    p = (g["h"] + g["l"] + g["c"]) / 3.0
    bc = (g["h"] + g["l"]) / 2.0
    tc = 2 * p - bc
    top = np.maximum(tc, bc)
    bot = np.minimum(tc, bc)
    prev = month - 1
    top_d = pd.Series(top).reindex(prev).to_numpy()
    bot_d = pd.Series(bot).reindex(prev).to_numpy()
    return top_d, bot_d


def cpr_values(h: float, l: float, c: float) -> tuple[float, float, float]:
    """(BC, P, TC) for one period."""
    p = (h + l + c) / 3.0
    bc = (h + l) / 2.0
    return bc, p, 2 * p - bc


def cci_crosses(cci_v: np.ndarray, avg: np.ndarray, side: int) -> np.ndarray:
    """Indices where CCI crosses its average: up (side +1) or down (side -1)."""
    a, b = cci_v[1:] - avg[1:], cci_v[:-1] - avg[:-1]
    with np.errstate(invalid="ignore"):
        hit = (a > 0) & (b <= 0) if side > 0 else (a < 0) & (b >= 0)
    return np.nonzero(hit)[0] + 1


def slope_ok(avg: np.ndarray, i: int, side: int) -> bool:
    """Long: avg(i) >= avg(i-5) - 5 (flat or rising). Short: avg(i) <= avg(i-5) + 5."""
    if i < SLOPE_LAG or np.isnan(avg[i]) or np.isnan(avg[i - SLOPE_LAG]):
        return False
    d = avg[i] - avg[i - SLOPE_LAG]
    return d >= -SLOPE_TOL if side > 0 else d <= SLOPE_TOL


def cpr_crosses(sma5: np.ndarray, top: np.ndarray, bot: np.ndarray, side: int) -> np.ndarray:
    """Long: SMA5(p) > top(p) and SMA5(p-1) <= top(p). Short: SMA5(p) < bot(p) and SMA5(p-1) >= bot(p).
    Both days are compared with the CPR in force on day p, so a month change alone is no cross."""
    ref = top if side > 0 else bot
    x1, x0, r = sma5[1:], sma5[:-1], ref[1:]
    with np.errstate(invalid="ignore"):
        hit = (x1 > r) & (x0 <= r) if side > 0 else (x1 < r) & (x0 >= r)
    return np.nonzero(hit)[0] + 1


def pair(cci_days: np.ndarray, cpr_days: np.ndarray, window: int = PAIR_WINDOW) -> np.ndarray:
    """Signal days max(c, p) for every CCI day c and CPR day p with |c - p| <= window (unique, sorted)."""
    out = set()
    cpr = np.asarray(cpr_days)
    for c_ in cci_days:
        for p_ in cpr[np.abs(cpr - c_) <= window]:
            out.add(int(max(c_, p_)))
    return np.array(sorted(out), dtype=int)


def apply_skip(days: list[int], skip: int = SKIP_SESSIONS) -> list[int]:
    """Keep a signal day only if no KEPT signal falls in the previous `skip` sessions."""
    kept: list[int] = []
    for d in sorted(days):
        if not kept or d - kept[-1] > skip:
            kept.append(d)
    return kept


ARMS = ("full", "cci_only", "no_slope", "no_cpr")


def candidate_days(h, l, c, dates) -> dict[tuple[str, int], np.ndarray]:
    """Candidate signal days (before universe, date window and skip rule) per (arm, side)."""
    h, l, c = (np.asarray(x, float) for x in (h, l, c))
    cc = cci(h, l, c)
    avg = sma(cc, CCI_AVG_N)
    s5 = sma(c, SMA_FAST)
    top, bot = monthly_cpr(np.asarray(dates), h, l, c)
    out = {}
    for side in (1, -1):
        cx = cci_crosses(cc, avg, side)
        cx_slope = np.array([i for i in cx if slope_ok(avg, i, side)], dtype=int)
        px = cpr_crosses(s5, top, bot, side)
        out[("cci_only", side)] = cx
        out[("no_cpr", side)] = cx_slope
        out[("no_slope", side)] = pair(cx, px)
        out[("full", side)] = pair(cx_slope, px)
    return out
