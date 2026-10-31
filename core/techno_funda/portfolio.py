"""
Portfolio simulation, costs and metrics for the techno-funda candidate
────────────────────────────────────────────────────────────────────────
Rules from docs/TECHNO_FUNDA_PREREG_2026-11-01.md, nothing tuned:

  - start Rs 10,00,000; at most 15 positions; each new one sized NAV/15 at
    the open it is bought, whole shares; idle cash earns 0%.
  - signals at close t -> buy at open t+1, best close/ATH first, then
    alphabetical; a held stock is not bought again; no bar on t+1 -> skipped.
  - exits checked at close t, sold at the next open the stock trades:
    close < EMA20, close <= 0.93 x entry fill, RSI14 < 45, close < 0.75 x ATH
    (the first three plus ATH come in as `exit_sig`; the hard stop is here).
  - delisted while held (last bar before the run ends) -> sold at that close.
  - costs per leg: 0.1% spec cost + delivery statutory charges, plus 10 bps
    slippage on the fill price.

Prices are back-adjusted, so a position is held in adjusted units:
qty_adj = whole raw shares / mult at entry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

SLOTS = 15
NAV0 = 1_000_000.0
HARD_STOP = 0.93
SLIPPAGE = 0.0010

# per-leg charges as fractions of turnover (delivery)
SPEC_COST = 0.0010           # the spec's 0.1% transaction cost (treated as brokerage: GST applies)
STT = 0.0010                 # delivery STT, both legs
STAMP_BUY = 0.00015          # stamp duty, buy leg
EXCHANGE = 0.0000307         # NSE cash 0.00297% + IPFT 0.0001% (core/risk/costs.py)
SEBI = 0.000001              # Rs 10 / crore
GST = 0.18                   # on spec cost + exchange + SEBI


def leg_cost(turnover: float, buy: bool) -> float:
    """Charges for one leg (Rs), excluding slippage, which is in the fill price."""
    base = SPEC_COST + EXCHANGE + SEBI
    return turnover * (base + STT + (STAMP_BUY if buy else 0.0) + GST * base)


@dataclass
class Position:
    sym: int
    qty_adj: float
    entry_fill: float            # adjusted, incl. slippage
    entry_day: int
    cost_paid: float


@dataclass
class Trade:
    sym: int
    entry_day: int
    exit_day: int
    entry_fill: float
    exit_fill: float
    qty_adj: float
    costs: float
    reason: str

    @property
    def pnl(self) -> float:
        return self.qty_adj * (self.exit_fill - self.entry_fill) - self.costs

    @property
    def ret(self) -> float:
        return self.pnl / (self.qty_adj * self.entry_fill)


@dataclass
class Result:
    nav: np.ndarray
    trades: list[Trade] = field(default_factory=list)
    costs: float = 0.0
    invested: np.ndarray | None = None


def simulate(open_: np.ndarray, close: np.ndarray, mult: np.ndarray, has_bar: np.ndarray,
             entry_sig: np.ndarray, rank: np.ndarray, exit_sig: np.ndarray,
             last_bar: np.ndarray, sym_names: list[str], nav0: float = NAV0,
             slots: int = SLOTS) -> Result:
    """Arrays are [day, symbol]. rank: higher = better (close / ATH).
    last_bar[s] = last day index the stock trades in the WHOLE data set."""
    n_days, _ = close.shape
    cash, pos = nav0, {}
    pending: set[int] = set()
    reasons: dict[int, str] = {}
    nav, invested = np.empty(n_days), np.empty(n_days)
    trades, costs_total = [], 0.0
    last_close = np.full(close.shape[1], np.nan)

    def sell(p: Position, day: int, price: float, reason: str) -> None:
        nonlocal cash, costs_total
        fill = price * (1 - SLIPPAGE)
        c = leg_cost(p.qty_adj * fill, buy=False)
        cash += p.qty_adj * fill - c
        costs_total += c
        trades.append(Trade(p.sym, p.entry_day, day, p.entry_fill, fill, p.qty_adj, p.cost_paid + c, reason))

    for d in range(n_days):
        bar = has_bar[d]
        if d > 0:
            # 1. exits decided at the previous close (or deferred)
            for s in sorted(pending):
                if bar[s]:
                    sell(pos.pop(s), d, open_[d, s], reasons.pop(s))
                    pending.discard(s)
            # 2. entries from the previous close's signals
            free = slots - len(pos)
            if free > 0:
                cand = [s for s in np.nonzero(entry_sig[d - 1])[0] if s not in pos]
                cand.sort(key=lambda s: (-rank[d - 1, s], sym_names[s]))
                nav_open = cash + sum(p.qty_adj * (open_[d, s] if bar[s] else last_close[s])
                                      for s, p in pos.items())
                alloc = nav_open / slots
                for s in cand:
                    if free == 0:
                        break
                    if not bar[s]:
                        continue
                    fill = open_[d, s] * (1 + SLIPPAGE)
                    raw_fill = fill / mult[d, s]
                    budget = min(alloc, cash)
                    qty_raw = math.floor(budget / raw_fill)
                    while qty_raw > 0 and qty_raw * raw_fill + leg_cost(qty_raw * raw_fill, True) > cash:
                        qty_raw -= 1
                    if qty_raw < 1:
                        continue
                    turnover = qty_raw * raw_fill
                    c = leg_cost(turnover, buy=True)
                    cash -= turnover + c
                    costs_total += c
                    pos[s] = Position(s, qty_raw / mult[d, s], fill, d, c)
                    free -= 1
        last_close = np.where(bar, close[d], last_close)
        # 3. close: delistings, then exit checks
        for s in list(pos):
            if bar[s] and last_bar[s] == d and d < n_days - 1:
                sell(pos.pop(s), d, close[d, s], "delisted")
                pending.discard(s)
                reasons.pop(s, None)
        for s, p in pos.items():
            if s in pending or not bar[s]:
                continue
            if close[d, s] <= HARD_STOP * p.entry_fill:
                pending.add(s)
                reasons[s] = "hard_stop"
            elif exit_sig[d, s]:
                pending.add(s)
                reasons[s] = "signal"
        held = sum(p.qty_adj * last_close[s] for s, p in pos.items())
        nav[d], invested[d] = cash + held, held
    return Result(nav, trades, costs_total, invested)


# ─── Metrics ──────────────────────────────────────────────────────────────────

def daily_returns(nav: np.ndarray) -> np.ndarray:
    return nav[1:] / nav[:-1] - 1


def cagr(nav: np.ndarray, years: float) -> float:
    return (nav[-1] / nav[0]) ** (1 / years) - 1


def sharpe(r: np.ndarray) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan")


def sortino(r: np.ndarray) -> float:
    down = np.minimum(r, 0)
    dd = math.sqrt((down ** 2).mean())
    return float(r.mean() / dd * math.sqrt(252)) if dd > 0 else float("nan")


def max_drawdown(nav: np.ndarray) -> float:
    peak = np.maximum.accumulate(nav)
    return float((1 - nav / peak).max())


def block_bootstrap_ci(x: np.ndarray, blocks: np.ndarray, n: int = 10_000, seed: int = 20261101,
                       level: float = 0.90) -> tuple[float, float]:
    """CI of mean(x) resampling whole blocks (weeks) with replacement."""
    rng = np.random.default_rng(seed)
    ids = np.unique(blocks)
    groups = [x[blocks == b] for b in ids]
    sums = np.array([g.sum() for g in groups])
    lens = np.array([len(g) for g in groups])
    draws = rng.integers(0, len(ids), size=(n, len(ids)))
    means = sums[draws].sum(axis=1) / lens[draws].sum(axis=1)
    a = (1 - level) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))
