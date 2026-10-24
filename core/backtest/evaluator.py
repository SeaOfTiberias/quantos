"""
QuantOS — Stage 1 / Stage 2 evaluator (docs/NEW_TRACKS_PREREG_2026-10-24.md)
─────────────────────────────────────────────────────────────────────────────
Pure. A strategy hands over its trades as EvalTrade: an entry and exit date,
a margin per lot (the capital one lot puts at risk), and `marks` -- the
trade's net return on that margin if it were closed at each date's close,
exit costs included. The last mark is the realised return.

Stage 1   per-trade screen: PF, Sharpe of the daily mark-to-market book at one
          unit of risk per signal, win rate, PF in each half, week bootstrap.
Stage 2   chronological NAV with quarter-Kelly lots from trades closed
          before each entry (30-trade warm-up), lot-lockout and capital-busy
          counts, the -5% daily kill switch, max drawdown.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

KELLY_SCALE = 0.25
WARMUP = 30
KILL_DAY = -0.05
MAX_DD = 0.20
TIERS = (100_000.0, 250_000.0, 500_000.0)
BOOT = 10_000
SEED = 20261024


@dataclass
class EvalTrade:
    entry:          date
    exit:           date
    margin_per_lot: float                 # rupees one lot puts at risk
    marks:          dict                  # date -> net return on margin if closed at that close
    label:          str = ""

    @property
    def ret(self) -> float:
        return self.marks[self.exit]


@dataclass(frozen=True)
class Gates:
    pf: float = 1.20
    sharpe: float = 0.80
    win: float = 0.50
    min_trades: int = 100
    boot_q: float = 0.025


@dataclass
class Stage1:
    n: int
    pf: float
    sharpe: float
    win: float
    mean: float
    pf_halves: tuple
    n_halves: tuple
    boot_lo: float
    checks: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(self.checks.values())


def profit_factor(rets: list[float]) -> float:
    gain = sum(r for r in rets if r > 0)
    loss = -sum(r for r in rets if r < 0)
    return gain / loss if loss > 0 else (math.inf if gain > 0 else float("nan"))


def daily_book(trades: list[EvalTrade], calendar: list[date]) -> list[float]:
    """Daily P&L of a book holding every trade at one unit of risk: the change in each open
    trade's mark. A trade's first mark (entry costs) lands on its entry date."""
    pnl = defaultdict(float)
    for t in trades:
        prev = 0.0
        for d in sorted(t.marks):
            pnl[d] += t.marks[d] - prev
            prev = t.marks[d]
    return [pnl.get(d, 0.0) for d in calendar]


def sharpe(daily: list[float]) -> float:
    if len(daily) < 2:
        return float("nan")
    m = sum(daily) / len(daily)
    sd = math.sqrt(sum((x - m) ** 2 for x in daily) / (len(daily) - 1))
    return m / sd * math.sqrt(252) if sd > 0 else float("nan")


def week_bootstrap(trades: list[EvalTrade], q: float, n: int = BOOT, seed: int = SEED) -> float:
    groups = defaultdict(list)
    for t in trades:
        groups[t.entry.isocalendar()[:2]].append(t.ret)
    gl = list(groups.values())
    if not gl:
        return float("nan")
    rng, out = random.Random(seed), []
    for _ in range(n):
        pick = [x for _ in gl for x in rng.choice(gl)]
        out.append(sum(pick) / len(pick))
    out.sort()
    return out[min(len(out) - 1, max(0, int(q * len(out))))]


def stage1(trades: list[EvalTrade], calendar: list[date], split: date, gates: Gates = Gates()) -> Stage1:
    rets = [t.ret for t in trades]
    halves = ([t.ret for t in trades if t.entry < split], [t.ret for t in trades if t.entry >= split])
    s = Stage1(
        n=len(trades),
        pf=profit_factor(rets) if rets else float("nan"),
        sharpe=sharpe(daily_book(trades, calendar)),
        win=(sum(r > 0 for r in rets) / len(rets)) if rets else float("nan"),
        mean=(sum(rets) / len(rets)) if rets else float("nan"),
        pf_halves=tuple(profit_factor(h) if h else float("nan") for h in halves),
        n_halves=tuple(len(h) for h in halves),
        boot_lo=week_bootstrap(trades, gates.boot_q) if trades else float("nan"),
    )
    s.checks = {
        f"PF > {gates.pf}": s.pf > gates.pf,
        f"Sharpe > {gates.sharpe}": s.sharpe > gates.sharpe,
        f"win > {gates.win:.0%}": s.win > gates.win,
        "PF > 1 in each half": all(p > 1.0 for p in s.pf_halves),
        f"bootstrap {gates.boot_q:.1%} > 0": s.boot_lo > 0,
        f"n >= {gates.min_trades}": s.n >= gates.min_trades,
    }
    return s


def kelly(rets: list[float]) -> Optional[float]:
    wins = [r for r in rets if r > 0]
    losses = [-r for r in rets if r < 0]
    if not rets or not wins:
        return 0.0 if rets else None
    if not losses:
        return 1.0
    w = len(wins) / len(rets)
    ratio = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
    return w - (1 - w) / ratio


@dataclass
class Stage2:
    start: float
    end: float
    max_dd: float
    taken: int
    lockouts: int
    busy: int
    no_edge: int
    kills: int
    warmup: int

    @property
    def passed(self) -> bool:
        return self.max_dd < MAX_DD and self.lockouts == 0 and self.taken > 0


def stage2(trades: list[EvalTrade], calendar: list[date], start: float) -> Stage2:
    """Each session, in order: mark open positions to the close, drop those that exit today,
    apply the -5% kill switch (close everything, no entries next session), then take today's
    entries at the close with quarter-Kelly lots."""
    by_entry = defaultdict(list)
    for t in sorted(trades, key=lambda t: (t.entry, t.label)):
        by_entry[t.entry].append(t)
    signal_exits = sorted((t.exit, t.ret) for t in trades)
    nav = peak = start
    max_dd = 0.0
    open_: list[list] = []                 # [trade, lots, last mark]
    closed: list[float] = []               # returns of every signal closed before today
    seen = {"taken": 0, "lockouts": 0, "busy": 0, "no_edge": 0, "kills": 0, "warmup": 0}
    halt_next, k = False, 0
    for d in calendar:
        halt_today, halt_next = halt_next, False
        while k < len(signal_exits) and signal_exits[k][0] < d:
            closed.append(signal_exits[k][1])
            k += 1
        prev_nav, day, still = nav, 0.0, []
        for pos in open_:
            t, lots, last = pos
            m = t.marks.get(d, last)
            day += (m - last) * lots * t.margin_per_lot
            pos[2] = m
            if d < t.exit:
                still.append(pos)
        open_ = still
        nav += day
        if day <= KILL_DAY * prev_nav:
            seen["kills"] += 1
            open_ = []                      # closed at today's marks, already booked
            halt_next = True
        for t in by_entry.get(d, []):
            if halt_today:
                continue
            if len(closed) < WARMUP:
                seen["warmup"] += 1
                continue
            f = kelly(closed)
            if f is None or f <= 0:
                seen["no_edge"] += 1
                continue
            lots = math.floor(nav * KELLY_SCALE * f / t.margin_per_lot) if nav > 0 else 0
            if lots <= 0:
                seen["lockouts"] += 1
                continue
            used = sum(p[1] * p[0].margin_per_lot for p in open_)
            if used + lots * t.margin_per_lot > nav:
                seen["busy"] += 1
                continue
            m0 = t.marks[min(t.marks)]
            nav += m0 * lots * t.margin_per_lot    # entry costs, booked on the entry close
            seen["taken"] += 1
            if t.exit > d:
                open_.append([t, lots, m0])
        peak = max(peak, nav)
        max_dd = max(max_dd, (peak - nav) / peak if peak > 0 else 1.0)
    return Stage2(start=start, end=nav, max_dd=max_dd, **seen)
