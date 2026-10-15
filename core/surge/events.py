"""
QuantOS — Candidate 23 Stage 1: +5% surge direction study
──────────────────────────────────────────────────────────
docs/SURGE_DIRECTION_METHODOLOGY.md. Pure numpy over a
core.statarb.residuals.Panel (roll-adjusted near-month stock futures, every
F&O symbol). No I/O, no option prices, no costs.

For each +5% close-to-close day: forward raw and market-excess returns at
1/3/5/8/10 days, five binary conditions, then the mining/holdout selector
test. Inference clusters by event date, because several stocks surging on
the same day are not independent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np

from core.statarb.residuals import Panel

SURGE = 0.05
HISTORY = 252
HORIZONS = (1, 3, 5, 8, 10)
PRIMARY_H = 5
MAX_H = max(HORIZONS)
COOLDOWN = 10            # no new event for a symbol within 10 rows of its last
Z_MULT = 3.0             # C3: r_t >= 3 x sd of prior 20 returns
MARKET_DAY = 0.01        # C4: equal-weighted universe return on t >= +1%
EXTENDED = 0.10          # C5: t-20 -> t-1 return >= +10%
THRESHOLDS = (0.04, 0.07)  # P(R(8) >= x), the Persistent example's distances
MIN_N = 30
MINING_T = 2.0
HOLDOUT_T = 1.5
CONDITIONS = ("results", "breakout52", "big_z", "market_day", "extended")


@dataclass(frozen=True)
class SurgeEvent:
    symbol: str
    t: int
    day: date
    surge: float
    raw: dict[int, float]
    excess: dict[int, float]
    cond: dict[str, bool]


@dataclass
class Exclusions:
    history: int = 0
    corp_action: int = 0
    forward: int = 0
    cooldown: int = 0


def _simple(panel: Panel) -> np.ndarray:
    r = np.full_like(panel.adj, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[1:] = panel.adj[1:] / panel.adj[:-1] - 1
    return r


def _forward_sums(panel: Panel) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """{h: (sum over symbols of R(h) at each t, count)} for the market leg."""
    out = {}
    for h in HORIZONS:
        fwd = np.full_like(panel.adj, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            fwd[:-h] = panel.adj[h:] / panel.adj[:-h] - 1
        ok = ~np.isnan(fwd)
        out[h] = (np.where(ok, fwd, 0.0).sum(axis=1), ok.sum(axis=1))
    return out


def find_events(panel: Panel, results_days: dict[str, set[int]]) -> tuple[list[SurgeEvent], Exclusions]:
    """results_days: {symbol: row indices t that count as results-driven}
    (a results meeting on dates[t-1]..dates[t] inclusive)."""
    ret = _simple(panel)
    sums = _forward_sums(panel)
    ok_ret = ~np.isnan(ret)
    mkt_day = np.where(ok_ret, ret, 0.0).sum(axis=1) / np.maximum(ok_ret.sum(axis=1), 1)

    events: list[SurgeEvent] = []
    excl = Exclusions()
    T = len(panel.dates)
    for j, sym in enumerate(panel.symbols):
        last = -10**9
        res = results_days.get(sym, set())
        for t in np.where(ret[:, j] >= SURGE)[0]:
            t = int(t)
            if t < HISTORY or np.isnan(panel.adj[t - HISTORY:t, j]).any():
                excl.history += 1
                continue
            if t + MAX_H >= T or np.isnan(panel.adj[t:t + MAX_H + 1, j]).any():
                excl.forward += 1
                continue
            if panel.jump[t:t + MAX_H + 1, j].any():
                excl.corp_action += 1
                continue
            if t - last <= COOLDOWN:
                excl.cooldown += 1
                continue
            last = t

            p0 = panel.adj[t, j]
            raw, excess = {}, {}
            for h in HORIZONS:
                r = panel.adj[t + h, j] / p0 - 1
                s, c = sums[h]
                m = (s[t] - r) / (c[t] - 1) if c[t] > 1 else 0.0
                raw[h], excess[h] = float(r), float(r - m)

            prior20 = ret[t - 20:t, j]
            cond = {
                "results": t in res,
                "breakout52": bool(panel.adj[t, j] >= np.nanmax(panel.adj[t - HISTORY:t, j])),
                "big_z": bool(ret[t, j] >= Z_MULT * np.nanstd(prior20, ddof=1)),
                "market_day": bool(mkt_day[t] >= MARKET_DAY),
                "extended": bool(panel.adj[t - 1, j] / panel.adj[t - 21, j] - 1 >= EXTENDED),
            }
            events.append(SurgeEvent(sym, t, panel.dates[t], float(ret[t, j]), raw, excess, cond))
    events.sort(key=lambda e: (e.t, e.symbol))
    return events, excl


def baseline(panel: Panel) -> dict[str, float]:
    """Unconditional stock-day figures: P(R(8) >= x), P(R(8) <= 0)."""
    h = 8
    fwd = panel.adj[h:] / panel.adj[:-h] - 1
    vals = fwd[~np.isnan(fwd)]
    out = {f"p_ge_{int(x * 100)}": float((vals >= x).mean()) for x in THRESHOLDS}
    out["p_le_0"] = float((vals <= 0).mean())
    out["n"] = float(len(vals))
    return out


@dataclass
class SubsetStats:
    n: int
    n_dates: int
    clustered_mean: float      # mean over event dates of the per-date mean X(h)
    t: float
    event_mean: float
    median: float
    drift: dict[int, float] = field(default_factory=dict)     # event-mean X(h) per h
    probs: dict[str, float] = field(default_factory=dict)     # raw R(8) thresholds


def stats(events: list[SurgeEvent], h: int = PRIMARY_H) -> Optional[SubsetStats]:
    if not events:
        return None
    by_date: dict[int, list[float]] = {}
    for e in events:
        by_date.setdefault(e.t, []).append(e.excess[h])
    dm = np.array([np.mean(v) for v in by_date.values()])
    if len(dm) > 1 and dm.std(ddof=1) > 0:
        t = float(dm.mean() / (dm.std(ddof=1) / math.sqrt(len(dm))))
    else:
        t = float("nan")
    x = np.array([e.excess[h] for e in events])
    r8 = np.array([e.raw[8] for e in events])
    return SubsetStats(
        n=len(events), n_dates=len(dm), clustered_mean=float(dm.mean()), t=t,
        event_mean=float(x.mean()), median=float(np.median(x)),
        drift={hh: float(np.mean([e.excess[hh] for e in events])) for hh in HORIZONS},
        probs={**{f"p_ge_{int(v * 100)}": float((r8 >= v).mean()) for v in THRESHOLDS},
               "p_le_0": float((r8 <= 0).mean())},
    )


def split(events: list[SurgeEvent], frac: float = 0.8) -> tuple[list[SurgeEvent], list[SurgeEvent], Optional[date]]:
    """Earliest `frac` of events = mining; the cutoff never splits a date."""
    if not events:
        return [], [], None
    cut_day = events[min(int(len(events) * frac), len(events) - 1)].day
    return ([e for e in events if e.day < cut_day], [e for e in events if e.day >= cut_day], cut_day)


@dataclass
class BranchResult:
    subset: str
    mining: Optional[SubsetStats]
    holdout: Optional[SubsetStats]
    passed: bool
    reason: str

    @property
    def direction(self) -> str:
        if not self.mining:
            return ""
        return "continuation" if self.mining.clustered_mean > 0 else "reversal"


def judge(name: str, mining: list[SurgeEvent], holdout: list[SurgeEvent]) -> BranchResult:
    m, h = stats(mining), stats(holdout)
    if not m or not h or m.n < MIN_N or h.n < MIN_N:
        return BranchResult(name, m, h, False,
                            f"too few events (mining {m.n if m else 0}, holdout {h.n if h else 0}; need {MIN_N} each)")
    if not abs(m.t) >= MINING_T:
        return BranchResult(name, m, h, False, f"mining |t| {abs(m.t):.2f} < {MINING_T}")
    sign = 1 if m.clustered_mean > 0 else -1
    if not (np.sign(h.clustered_mean) == sign and sign * h.t >= HOLDOUT_T):
        return BranchResult(name, m, h, False,
                            f"holdout does not confirm (mean {h.clustered_mean:+.2%}, t {h.t:.2f})")
    return BranchResult(name, m, h, True, "branch: mining and holdout agree")


def subsets(events: list[SurgeEvent]) -> dict[str, list[SurgeEvent]]:
    out = {}
    for c in CONDITIONS:
        out[f"{c}=TRUE"] = [e for e in events if e.cond[c]]
        out[f"{c}=FALSE"] = [e for e in events if not e.cond[c]]
    return out


def results_rows(panel: Panel, meetings: dict[str, list[date]]) -> dict[str, set[int]]:
    """Row indices t whose window dates[t-1]..dates[t] contains a results
    meeting, per symbol (C1)."""
    import bisect

    out: dict[str, set[int]] = {}
    for sym, days in meetings.items():
        rows = set()
        for d in days:
            i = bisect.bisect_left(panel.dates, d)   # first trading day >= d
            if i < len(panel.dates):
                rows.add(i)                           # meeting on a trading day or a holiday before it
                if i + 1 < len(panel.dates) and panel.dates[i] == d:
                    rows.add(i + 1)                   # meeting day t-1 -> reaction on t
        out[sym] = rows
    return out
