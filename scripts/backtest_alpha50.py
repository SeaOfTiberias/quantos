#!/usr/bin/env python3
"""
QuantOS — NIFTY Alpha 50 rebuild + skip-month / market-filter grid (2026-11-27)
────────────────────────────────────────────────────────────────────────────────
Pre-registered in docs/ALPHA50_REBUILD_PREREG_2026-11-27.md (0a01741, amendment 1 d7434c6),
signed off by the user before any code or run. Stock data, adjustment and costs are the
Darvas OOS run's own loaders (scripts/backtest_darvas_atr_stop_oos.py), imported unchanged;
index closes from data_cache/indices/ (scripts/fetch_index_history.py).

    python scripts/backtest_alpha50.py --worked     # first two reviews + one filter switch, then stop
    python scripts/backtest_alpha50.py --step1      # the tracking gate only
    python scripts/backtest_alpha50.py              # step 1, then step 2 only if step 1 passes

Pure parts (tests in tests/unit/test_backtest_alpha50.py): review/expiry dates, eligibility,
alpha, selection with the buffer, the portfolio walk with costs, filter and lots, and the stats.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import math
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_FROM, DATA_TO = date(2015, 1, 1), date(2023, 12, 31)
MEASURE_FROM, MEASURE_TO = date(2017, 3, 31), date(2023, 12, 29)
GATE_FROM = date(2018, 3, 14)
HALF_SPLIT = date(2020, 7, 1)
WF_YEARS = range(2019, 2024)
TOP_LIQ, N_STOCKS, BUFFER_RANK = 300, 50, 100
SESS_PER_MONTH = 21
COVERAGE = 0.95
CAPITAL = 1_000_000.0
BOOT, SEED, BLOCK = 10_000, 20261127, 3
GATE_CORR, GATE_CAGR_PP = 0.90, 3.0
IDX = Path("data_cache/indices")
OUT = Path("docs/ALPHA50_REBUILD_RESULTS_2026-11-27.md")


@dataclass(frozen=True)
class Version:
    skip: int = 0           # months skipped before the cut-off
    lookback: int = 12      # months of returns
    filt: Optional[int] = None   # NIFTY 500 SMA length, None = no filter

    @property
    def name(self) -> str:
        f = f"SMA{self.filt}" if self.filt else "no filter"
        return "base (index rules)" if self == BASE else f"skip {self.skip}m, {self.lookback}m, {f}"


BASE = Version()
GRID = [Version(s, l, f) for s in (1, 2) for l in (9, 12) for f in (None, 150, 200)]


# ─── calendar ────────────────────────────────────────────────────────────────

def last_session_of_month(sessions: list[date], y: int, m: int) -> Optional[date]:
    ms = [d for d in sessions if d.year == y and d.month == m]
    return ms[-1] if ms else None


def expiry_day(sessions: list[date], y: int, m: int) -> Optional[date]:
    """The month's last Thursday if it is a session, else the last session before it."""
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() != 3:
        d -= timedelta(days=1)
    i = bisect.bisect_right(sessions, d) - 1
    return sessions[i] if i >= 0 else None


def reviews(sessions: list[date], start_year: int = 2017, end: date = DATA_TO) -> list[tuple[date, date]]:
    """(cut-off, effective close) pairs: cut-off = last session of Feb/May/Aug/Nov, effective =
    the expiry day of Mar/Jun/Sep/Dec (the portfolio changes at that close)."""
    out = []
    for y in range(start_year, end.year + 1):
        for cm in (2, 5, 8, 11):
            c, e = last_session_of_month(sessions, y, cm), expiry_day(sessions, y, cm + 1)
            if c and e and e <= end and e > c:
                out.append((c, e))
    return out


def month_ends(sessions: list[date]) -> set[date]:
    return {a for a, b in zip(sessions, sessions[1:]) if a.month != b.month} | ({sessions[-1]} if sessions else set())


# ─── eligibility and alpha ───────────────────────────────────────────────────

def months_before(d: date, n: int) -> date:
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, min(d.day, 28))


def eligible(bars: dict[str, dict[date, dict]], sessions: list[date], cutoff: date,
             top: int = TOP_LIQ) -> list[str]:
    """Top `top` by average daily traded value over the 6 months to the cut-off, then the
    1-year listing and 100% trading-frequency rules (amendment 1 order)."""
    six = months_before(cutoff, 6)
    year = [d for d in sessions if months_before(cutoff, 12) < d <= cutoff]
    liq = {}
    for s, b in bars.items():
        vals = [r["val"] for d, r in b.items() if six < d <= cutoff]
        if vals:
            liq[s] = sum(vals) / len(vals)
    ranked = sorted(liq, key=lambda s: (-liq[s], s))[:top]
    out = []
    for s in ranked:
        b = bars[s]
        first = min(b)
        if first <= cutoff - timedelta(days=365) and all(d in b for d in year):
            out.append(s)
    return out


def ols_alpha(r: list[float], m: list[float]) -> tuple[float, float]:
    """(annualised alpha, beta) of r = a + b*m + e."""
    n = len(r)
    mr, mm = sum(r) / n, sum(m) / n
    cov = sum((x - mr) * (y - mm) for x, y in zip(r, m))
    var = sum((y - mm) ** 2 for y in m)
    b = cov / var if var else 0.0
    return (mr - b * mm) * 252, b


def window_alpha(b: dict[date, dict], mkt: dict[date, float], sessions: list[date], cutoff: date,
                 v: Version) -> Optional[tuple[float, float]]:
    """Alpha over lookback*21 sessions ending skip*21 sessions before the cut-off; None when
    the stock has bars on under 95% of those sessions."""
    ci = bisect.bisect_right(sessions, cutoff) - 1
    end = ci - v.skip * SESS_PER_MONTH
    start = end - v.lookback * SESS_PER_MONTH
    if start < 1:
        return None
    win = sessions[start:end + 1]
    if sum(d in b for d in win[1:]) < COVERAGE * (len(win) - 1):
        return None
    rs, ms = [], []
    for a, c in zip(win, win[1:]):
        if a in b and c in b and a in mkt and c in mkt:
            rs.append(b[c]["c"] / b[a]["c"] - 1)
            ms.append(mkt[c] / mkt[a] - 1)
    return ols_alpha(rs, ms) if len(rs) > 20 else None


def select(alphas: dict[str, float], existing: set[str], n: int = N_STOCKS, buffer: int = BUFFER_RANK) -> list[str]:
    """Top n by alpha (> 0); an existing constituent ranked within `buffer` is kept. If no
    stock has a positive alpha, the existing constituents are kept."""
    pos = sorted((s for s, a in alphas.items() if a > 0), key=lambda s: (-alphas[s], s))
    if not pos:
        return sorted(existing)
    keep = [s for s in pos[:buffer] if s in existing][:n]
    fill = [s for s in pos if s not in keep][: n - len(keep)]
    return keep + fill


def alpha_weights(names: list[str], alphas: dict[str, float]) -> dict[str, float]:
    tot = sum(max(alphas[s], 0.0) for s in names)
    if tot <= 0:
        return {s: 1 / len(names) for s in names}
    return {s: max(alphas[s], 0.0) / tot for s in names}


# ─── the portfolio walk ──────────────────────────────────────────────────────

@dataclass
class Book:
    cash: float
    shares: dict = field(default_factory=dict)          # symbol -> shares
    lots: dict = field(default_factory=dict)            # symbol -> [[date, shares]]
    traded: float = 0.0
    cost: float = 0.0
    sold_short: float = 0.0                             # rupees sold from lots held < 365 days
    sold_long: float = 0.0

    def value(self, px: dict) -> float:
        return self.cash + sum(q * px[s] for s, q in self.shares.items())

    def _sell(self, s: str, q: float, p: float, d: date, rate: float):
        self.shares[s] -= q
        if self.shares[s] <= 1e-9:
            del self.shares[s]
        rem, lots = q, self.lots.get(s, [])
        while rem > 1e-9 and lots:
            take = min(rem, lots[0][1])
            amt = take * p
            if (d - lots[0][0]).days < 365:
                self.sold_short += amt
            else:
                self.sold_long += amt
            lots[0][1] -= take
            rem -= take
            if lots[0][1] <= 1e-9:
                lots.pop(0)
        amt = q * p
        self.cash += amt - amt * rate
        self.traded += amt
        self.cost += amt * rate

    def _buy(self, s: str, amt: float, p: float, d: date, rate: float):
        q = amt / (p * (1 + rate))
        self.shares[s] = self.shares.get(s, 0.0) + q
        self.lots.setdefault(s, []).append([d, q])
        self.cash -= amt
        self.traded += q * p
        self.cost += q * p * rate

    def rebalance_to(self, target: dict[str, float], px: dict, d: date, rate: float):
        """Trade to target weights at these prices; sells first, buys share what cash is left."""
        V = self.value(px)
        for s in list(self.shares):
            want = target.get(s, 0.0) * V
            have = self.shares[s] * px[s]
            if have > want + 1e-6:
                self._sell(s, (have - want) / px[s], px[s], d, rate)
        need = {s: w * V - self.shares.get(s, 0.0) * px[s] for s, w in target.items()}
        need = {s: x for s, x in need.items() if x > 1e-6}
        tot = sum(need.values())
        if tot > 0:
            scale = min(1.0, max(self.cash, 0.0) / tot)
            for s, x in need.items():
                self._buy(s, x * scale, px[s], d, rate)

    def liquidate(self, px: dict, d: date, rate: float):
        for s in list(self.shares):
            self._sell(s, self.shares[s], px[s], d, rate)


def sma_at(closes: list[tuple[date, float]], d: date, n: int) -> Optional[tuple[float, float]]:
    """(close, SMA n) on the last index date at or before d."""
    i = bisect.bisect_right([x[0] for x in closes], d) - 1
    if i + 1 < n:
        return None
    return closes[i][1], sum(c for _, c in closes[i + 1 - n:i + 1]) / n


def walk(v: Version, sessions: list[date], close: dict[str, dict[date, float]], last_bar: dict[str, date],
         targets: list[tuple[date, dict[str, float]]], n500: list[tuple[date, float]], rate: float,
         start: date, end: date, capital: float = CAPITAL) -> dict:
    """Daily value of one version. targets: (effective close, weights) from its reviews."""
    book = Book(cash=capital)
    eff = dict(targets)
    me = month_ends(sessions)
    last_px: dict[str, float] = {}
    days_of: dict[str, list[date]] = {}

    def px_on(s: str, d: date) -> float:
        """Close on d, else the last close before d (a stock that didn't trade that day)."""
        if d in close[s]:
            return close[s][d]
        if s not in days_of:
            days_of[s] = sorted(close[s])
        i = bisect.bisect_right(days_of[s], d) - 1
        return close[s][days_of[s][i]]

    target: Optional[dict] = None
    invested = v.filt is None
    filt_state_known = v.filt is None
    values, in_cash_days, switches = [], 0, []
    first_eff = min(eff) if eff else None
    if v.filt is not None and first_eff:
        prev_me = [d for d in sorted(me) if d < first_eff]
        if prev_me:
            x = sma_at(n500, prev_me[-1], v.filt)
            invested = bool(x and x[0] >= x[1])
            filt_state_known = True
    for d in sessions:
        if d > end:
            break
        for s in book.shares:
            if d in close[s]:
                last_px[s] = close[s][d]
        for s in list(book.shares):                           # stopped trading: sell at last close, spread pro rata
            if last_bar[s] < d:
                px = {k: last_px[k] for k in book.shares}
                rest = {k: book.shares[k] * px[k] for k in book.shares if k != s}
                book._sell(s, book.shares[s], px[s], d, rate)
                tot = sum(rest.values())
                if tot > 0:
                    cash = book.cash
                    for k, x in rest.items():
                        book._buy(k, cash * x / tot, px[k], d, rate)
        if d in eff:
            target = eff[d]
            for s in target:
                last_px[s] = px_on(s, d)
            if invested and target:
                px = {s: last_px[s] for s in set(target) | set(book.shares)}
                book.rebalance_to(target, px, d, rate)
        if v.filt is not None and d in me and target is not None:
            x = sma_at(n500, d, v.filt)
            above = bool(x and x[0] >= x[1])
            if invested and not above:
                book.liquidate({s: last_px[s] for s in book.shares}, d, rate)
                invested = False
                switches.append((d, "out", x))
            elif not invested and above:
                for s in target:
                    last_px[s] = px_on(s, d)
                book.rebalance_to(target, {s: last_px[s] for s in target}, d, rate)
                invested = True
                switches.append((d, "in", x))
        if target is not None and d >= start:
            values.append((d, book.value({s: last_px[s] for s in book.shares})))
            in_cash_days += (not book.shares)
    return dict(values=values, traded=book.traded, cost=book.cost, sold_short=book.sold_short,
                sold_long=book.sold_long, in_cash_days=in_cash_days, switches=switches)


# ─── stats ───────────────────────────────────────────────────────────────────

def daily_returns(values: list[tuple[date, float]]) -> list[tuple[date, float]]:
    return [(b[0], b[1] / a[1] - 1) for a, b in zip(values, values[1:])]


def sharpe(rets: list[float], per_year: int = 252) -> float:
    if len(rets) < 2:
        return float("nan")
    sd = statistics.stdev(rets)
    return statistics.mean(rets) / sd * math.sqrt(per_year) if sd else float("nan")


def cagr(values: list[tuple[date, float]]) -> float:
    yrs = (values[-1][0] - values[0][0]).days / 365.25
    return (values[-1][1] / values[0][1]) ** (1 / yrs) - 1


def max_drawdown(values: list[tuple[date, float]]) -> float:
    peak, dd = -1.0, 0.0
    for _, x in values:
        peak = max(peak, x)
        dd = min(dd, x / peak - 1)
    return dd


def monthly_returns(values: list[tuple[date, float]]) -> dict[tuple[int, int], float]:
    last = {}
    for d, x in values:
        last[(d.year, d.month)] = x
    keys = sorted(last)
    return {k: last[k] / last[p] - 1 for p, k in zip(keys, keys[1:])}


def block_bootstrap_share(a: list[float], b: list[float], block: int = BLOCK, boot: int = BOOT,
                          seed: int = SEED) -> float:
    """Share of draws in which Sharpe(a) > Sharpe(b), resampling paired monthly returns in blocks."""
    n, rng, wins = len(a), random.Random(seed), 0
    starts = list(range(n - block + 1))
    for _ in range(boot):
        ia: list[int] = []
        while len(ia) < n:
            s = rng.choice(starts)
            ia += range(s, s + block)
        ia = ia[:n]
        wins += sharpe([a[i] for i in ia], 12) > sharpe([b[i] for i in ia], 12)
    return wins / boot


def correlation(x: list[float], y: list[float]) -> float:
    """Pearson (statistics.correlation needs Python 3.10)."""
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx, syy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy)


# ─── data ────────────────────────────────────────────────────────────────────

def read_index(name: str) -> list[tuple[date, float]]:
    with (IDX / f"{name}.csv").open() as f:
        return [(date.fromisoformat(r["date"]), float(r["close"])) for r in csv.DictReader(f)]


def load():
    from scripts import backtest_darvas_atr_stop_oos as oos
    oos.DATA_FROM, oos.DATA_TO = DATA_FROM, DATA_TO            # amendment 1: from 2015
    raw = oos.load_bhavcopies()
    actions = oos.load_actions()
    bars = {}
    for s, rows in raw.items():
        if len(rows) < 120:
            continue
        adj = oos.adjust(rows, actions.get(s, []))
        bars[s] = {r["date"]: r for r in adj}
    sessions = sorted({d for b in bars.values() for d in b})
    return bars, sessions


def cost_rate() -> float:
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL
    qty = 100
    return STRESSED_COST_MODEL.cost_of(1000.0, 1000.0, qty, "BUY") / (2 * 1000.0 * qty)


_POOLS: dict = {}


def build_targets(v: Version, bars, sessions, mkt, revs) -> tuple[list, list]:
    """(effective close, weights) per review, and per-review detail rows."""
    existing: set[str] = set()
    out, detail = [], []
    for cut, eff in revs:
        if cut not in _POOLS:
            _POOLS[cut] = eligible(bars, sessions, cut)
        pool = _POOLS[cut]
        al, betas = {}, {}
        for s in pool:
            x = window_alpha(bars[s], mkt, sessions, cut, v)
            if x:
                al[s], betas[s] = x
        names = select(al, existing)
        w = alpha_weights(names, al)
        detail.append(dict(cutoff=cut, effective=eff, pool=len(pool), with_alpha=len(al), names=names,
                           kept=sorted(existing & set(names)), left=sorted(existing - set(names)),
                           came=sorted(set(names) - existing), alphas=al, betas=betas, weights=w))
        existing = set(names)
        out.append((eff, w))
    return out, detail


# ─── runs ────────────────────────────────────────────────────────────────────

def run_version(v, bars, sessions, mkt, revs, n500, rate):
    targets, detail = build_targets(v, bars, sessions, mkt, revs)
    close = {s: {d: r["c"] for d, r in b.items()} for s, b in bars.items()}
    last_bar = {s: max(b) for s, b in bars.items()}
    w = walk(v, sessions, close, last_bar, targets, n500, rate, MEASURE_FROM, MEASURE_TO)
    w["detail"] = detail
    return w


def worked(bars, sessions, mkt, revs, n500) -> str:
    _, det = build_targets(BASE, bars, sessions, mkt, revs[:2])
    a, b = det
    out = [f"## Review 1: cut-off {a['cutoff']}, effective close {a['effective']}", "",
           f"{a['pool']} eligible after the 300/listing/frequency rules, {a['with_alpha']} with an alpha; "
           f"{len(a['names'])} selected. Top 10 by alpha:", "",
           "| Stock | Alpha (ann.) | Beta | Weight |", "|---|---|---|---|"]
    for s in sorted(a["names"], key=lambda s: -a["alphas"][s])[:10]:
        out.append(f"| {s} | {a['alphas'][s]:+.1%} | {a['betas'][s]:.2f} | {a['weights'][s]:.2%} |")
    out += ["", f"Largest weight {max(a['weights'].values()):.2%}.", "",
            f"## Review 2: cut-off {b['cutoff']}, effective close {b['effective']}", "",
            f"Stayed: {len(b['kept'])}. Left ({len(b['left'])}): {', '.join(b['left'])}.",
            f"Came in ({len(b['came'])}): {', '.join(b['came'])}.", ""]
    kept_buf = [s for s in b["kept"] if sorted(b["alphas"], key=lambda x: -b["alphas"][x]).index(s) >= N_STOCKS]
    out.append(f"Kept only because of the 100% buffer (ranked 51-100): {', '.join(kept_buf) or 'none'}.")
    me = sorted(month_ends(sessions))
    prev = None
    for d in me:
        x = sma_at(n500, d, 200)
        if not x or d < date(2017, 3, 1):
            continue
        st = x[0] >= x[1]
        if prev is not None and st != prev:
            out += ["", f"## First 200-day filter switch from 2017-03: month-end {d}", "",
                    f"NIFTY 500 close {x[0]:.2f} vs SMA200 {x[1]:.2f}: {'back above (buy)' if st else 'below (sell to cash)'}."]
            break
        prev = st
    return "\n".join(out) + "\n"


def step1(base_gross) -> tuple[bool, str]:
    a50 = dict(read_index("NIFTYALPHA50"))
    vals = [(d, x) for d, x in base_gross["values"] if GATE_FROM <= d <= MEASURE_TO and d in a50]
    rb = daily_returns(vals)
    ix = daily_returns([(d, a50[d]) for d, _ in vals])
    corr = correlation([r for _, r in rb], [r for _, r in ix])
    c_rb, c_ix = cagr(vals), cagr([(d, a50[d]) for d, _ in vals])
    ok = corr >= GATE_CORR and abs(c_rb - c_ix) * 100 <= GATE_CAGR_PP
    txt = (f"Base version before costs vs NIFTY Alpha 50 (price), {vals[0][0]} to {vals[-1][0]}, {len(rb)} daily returns:\n\n"
           f"- correlation of daily returns {corr:.3f} (need >= {GATE_CORR})\n"
           f"- CAGR rebuild {c_rb:+.2%} vs index {c_ix:+.2%}: difference {(c_rb - c_ix) * 100:+.2f} pp (need within {GATE_CAGR_PP})\n\n"
           f"**Step 1 {'PASS' if ok else 'FAIL'}**\n")
    return ok, txt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worked", action="store_true")
    ap.add_argument("--step1", action="store_true")
    a = ap.parse_args(argv)
    bars, sessions = load()
    mkt = dict(read_index("NIFTY50"))
    n500 = read_index("NIFTY500")
    revs = reviews(sessions)
    print(f"{len(bars)} symbols, {len(sessions)} sessions, {len(revs)} reviews", flush=True)
    if a.worked:
        sys.stdout.buffer.write(worked(bars, sessions, mkt, revs, n500).encode("utf-8"))
        return 0
    base_gross = run_version(BASE, bars, sessions, mkt, revs, n500, 0.0)
    ok, txt = step1(base_gross)
    sys.stdout.buffer.write(txt.encode("utf-8"))
    if a.step1 or not ok:
        return 0
    raise SystemExit("step 2: run after step 1 is reviewed")


if __name__ == "__main__":
    raise SystemExit(main())
