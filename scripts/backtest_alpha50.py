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


def listing_and_frequency(ranked: list[str], bars: dict[str, dict[date, dict]], sessions: list[date],
                          cutoff: date) -> list[str]:
    """Bars from at least one year before the cut-off and on every session of the year to it."""
    year = [d for d in sessions if months_before(cutoff, 12) < d <= cutoff]
    out = []
    for s in ranked:
        b = bars[s]
        if min(b) <= cutoff - timedelta(days=365) and all(d in b for d in year):
            out.append(s)
    return out


def eligible(bars: dict[str, dict[date, dict]], sessions: list[date], cutoff: date,
             top: int = TOP_LIQ) -> list[str]:
    """Round 1: top `top` by average daily traded value over the 6 months to the cut-off, then the
    1-year listing and 100% trading-frequency rules (amendment 1 order)."""
    six = months_before(cutoff, 6)
    liq = {}
    for s, b in bars.items():
        vals = [r["val"] for d, r in b.items() if six < d <= cutoff]
        if vals:
            liq[s] = sum(vals) / len(vals)
    ranked = sorted(liq, key=lambda s: (-liq[s], s))[:top]
    return listing_and_frequency(ranked, bars, sessions, cutoff)


# ─── round 2 universe: AMFI average market cap (docs/ALPHA50_REBUILD_V2_PREREG_2026-11-27.md) ──

AMFI = Path("data_cache/amfi_mcap")
AMFI_FIRST_YEAR = 2018            # first cut-off with a public list: 2018-02-28 (Jul-Dec 2017 list)


def amfi_period(cutoff: date) -> str:
    """Feb/May cut-offs use the previous year's Jul-Dec list, Aug/Nov the same year's Jan-Jun list."""
    return f"{cutoff.year - 1}H2" if cutoff.month <= 6 else f"{cutoff.year}H1"


def read_amfi(period: str, root: Path = AMFI) -> list[str]:
    """NSE symbols in AMFI rank order (scripts/parse_amfi_mcap.py output); blanks and repeats dropped."""
    with (root / f"amfi_{period}.csv").open(encoding="utf-8") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["rank"]))
    out, seen = [], set()
    for r in rows:
        s = r["nse_symbol"].strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def eligible_amfi(bars: dict[str, dict[date, dict]], sessions: list[date], cutoff: date,
                  ranked: list[str], top: int = TOP_LIQ) -> tuple[list[str], list[str], list[str]]:
    """(eligible, matched top `top`, unmatched skipped): the `top` highest-ranked AMFI names that have
    bars in our data (an unmatched name is skipped and the next rank fills in), then round 1's listing
    and frequency rules, with no replacement for stocks that fail them."""
    matched, unmatched = [], []
    for s in ranked:
        if len(matched) == top:
            break
        (matched if s in bars else unmatched).append(s)
    return listing_and_frequency(matched, bars, sessions, cutoff), matched, unmatched


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
UNIVERSE = "turnover"             # round 1; "amfi" = round 2


def pool_at(bars, sessions, cut) -> list[str]:
    key = (UNIVERSE, cut)
    if key not in _POOLS:
        if UNIVERSE == "amfi":
            _POOLS[key] = eligible_amfi(bars, sessions, cut, read_amfi(amfi_period(cut)))[0]
        else:
            _POOLS[key] = eligible(bars, sessions, cut)
    return _POOLS[key]


def build_targets(v: Version, bars, sessions, mkt, revs) -> tuple[list, list]:
    """(effective close, weights) per review, and per-review detail rows."""
    existing: set[str] = set()
    out, detail = [], []
    for cut, eff in revs:
        pool = pool_at(bars, sessions, cut)
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


def amfi_mechanics(bars, sessions, revs) -> str:
    """Round 2 'before the full run' tables: parser counts, per-review overlap with round 1, no returns."""
    out = ["## AMFI lists (parser rows vs last rank)", "", "| List | Rows | Last rank | Rank-300 NSE symbol |", "|---|---|---|---|"]
    for p in sorted({amfi_period(c) for c, _ in revs}):
        with (AMFI / f"amfi_{p}.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        r300 = [r["nse_symbol"] for r in rows if r["rank"] == "300"]
        out.append(f"| {p} | {len(rows)} | {max(int(r['rank']) for r in rows)} | {r300[0] if r300 else '?'} |")
    out += ["", "## Per review", "",
            "| Cut-off | List | Top-300 matched | Unmatched skipped | Eligible (round 2) | Eligible (round 1) | In both | Round-1 names dropped |",
            "|---|---|---|---|---|---|---|---|"]
    first = None
    for cut, eff in revs:
        el, matched, un = eligible_amfi(bars, sessions, cut, read_amfi(amfi_period(cut)))
        r1 = eligible(bars, sessions, cut)
        both = set(el) & set(r1)
        out.append(f"| {cut} | {amfi_period(cut)} | {len(matched)} | {len(un)} | {len(el)} | {len(r1)} | {len(both)} | {len(set(r1) - set(el))} |")
        if first is None:
            first = (cut, el, matched, un, r1)
    cut, el, matched, un, r1 = first
    out += ["", f"## First review, cut-off {cut}", "",
            f"Unmatched top-300 names skipped ({len(un)}): {', '.join(un) or 'none'}.", "",
            f"Failed the listing/frequency rules, not replaced ({len(matched) - len(el)}): "
            f"{', '.join(s for s in matched if s not in el) or 'none'}.", "",
            f"Round-1 names dropped ({len(set(r1) - set(el))}): {', '.join(sorted(set(r1) - set(el)))}.", ""]
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


# ─── step 2: the grid (prereg 0a01741 step 2; round 2 window from the first effective close) ──

def window_sharpe(rets: list[tuple[date, float]], a: date, b: date) -> float:
    return sharpe([r for d, r in rets if a <= d <= b])


def median_version(scores: dict[Version, float]) -> Version:
    """The 12 ranked lowest to highest by score; the median is the 6th (lower of the middle two)."""
    ranked = sorted(scores, key=lambda v: (scores[v], v.skip, v.lookback, v.filt or 0))
    return ranked[(len(ranked) - 1) // 2]


def walk_forward(rets: dict[Version, list[tuple[date, float]]], start: date,
                 years=WF_YEARS) -> tuple[list[tuple[date, float]], dict[int, Version]]:
    """Each year: the version with the best Sharpe from `start` to the end of the year before;
    its daily returns for that year are kept (switching costs ignored)."""
    stitched, choice = [], {}
    for y in years:
        fit = {v: window_sharpe(r, start, date(y - 1, 12, 31)) for v, r in rets.items()}
        best = max(fit, key=lambda v: (fit[v], -v.skip, -v.lookback, -(v.filt or 0)))
        choice[y] = best
        stitched += [(d, x) for d, x in rets[best] if d.year == y]
    return stitched, choice


def step2_verdict(runs: dict[Version, dict], base: dict, start: date, end: date = MEASURE_TO,
                  boot: int = BOOT) -> dict:
    """The five pass criteria. runs: the 12 grid versions' walk() output, base: the base's; net of costs."""
    rets = {v: [(d, x) for d, x in daily_returns(w["values"]) if start <= d <= end] for v, w in runs.items()}
    brets = [(d, x) for d, x in daily_returns(base["values"]) if start <= d <= end]
    score = {v: sharpe([x for _, x in r]) for v, r in rets.items()}
    b_score = sharpe([x for _, x in brets])
    med = median_version(score)
    mm, bm = monthly_returns(runs[med]["values"]), monthly_returns(base["values"])
    keys = sorted(k for k in set(mm) & set(bm) if date(k[0], k[1], 1) >= date(start.year, start.month, 1))
    share = block_bootstrap_share([mm[k] for k in keys], [bm[k] for k in keys], boot=boot)
    halves = [(start, HALF_SPLIT - timedelta(days=1)), (HALF_SPLIT, end)]
    half_med = [window_sharpe(rets[med], a, b) for a, b in halves]
    half_base = [window_sharpe(brets, a, b) for a, b in halves]
    stitched, choice = walk_forward(rets, start)
    wf_from = date(WF_YEARS[0], 1, 1)
    wf_s, wf_b = sharpe([x for _, x in stitched]), window_sharpe(brets, wf_from, end)
    dd_med = max_drawdown([(d, x) for d, x in runs[med]["values"] if start <= d <= end])
    dd_base = max_drawdown([(d, x) for d, x in base["values"] if start <= d <= end])
    above = sum(s > b_score for s in score.values())
    checks = {
        "1 better risk-adjusted (Sharpe above base, bootstrap >= 90%)": score[med] > b_score and share >= 0.90,
        "2 smaller max drawdown": dd_med > dd_base,          # drawdowns are negative: closer to 0 is smaller
        "3 breadth: >= 9 of 12 above base": above >= 9,
        "4 both halves above base": all(m > b for m, b in zip(half_med, half_base)),
        "5 walk-forward above base 2019-23": wf_s > wf_b,
    }
    return dict(score=score, base_score=b_score, median=med, share=share, half_med=half_med,
                half_base=half_base, halves=halves, wf_sharpe=wf_s, wf_base=wf_b, wf_choice=choice,
                dd_med=dd_med, dd_base=dd_base, above=above, checks=checks, passed=all(checks.values()))


def per_year(values: list[tuple[date, float]]) -> dict[int, float]:
    out, prev = {}, values[0][1]
    for y in sorted({d.year for d, _ in values}):
        last = [x for d, x in values if d.year == y][-1]
        out[y], prev = last / prev - 1, last
    return out


def step2_report(runs, base, ver, start, rate, a50, n500) -> str:
    def row(name, w):
        vals = [(d, x) for d, x in w["values"] if start <= d <= MEASURE_TO]
        yrs = (vals[-1][0] - vals[0][0]).days / 365.25
        avg = statistics.mean(x for _, x in vals)
        tax = w["sold_short"] / (w["sold_short"] + w["sold_long"]) if w["sold_short"] + w["sold_long"] else float("nan")
        return (f"| {name} | {cagr(vals):+.2%} | {sharpe([x for _, x in daily_returns(vals)]):.2f} | "
                f"{max_drawdown(vals):.1%} | {w['in_cash_days'] / len(vals):.0%} | {w['traded'] / avg / yrs:.2f}x | {tax:.0%} |")
    med = ver["median"]
    out = [f"Window {start} to {MEASURE_TO}, net of costs at {rate * 1e4:.1f} bps per side.", "",
           "## Pass criteria", ""]
    out += [f"- {k}: **{'PASS' if ok else 'FAIL'}**" for k, ok in ver["checks"].items()]
    out += ["", f"**Step 2 {'PASS' if ver['passed'] else 'FAIL'}**", "",
            f"Median version (6th of 12 by Sharpe): **{med.name}**, Sharpe {ver['score'][med]:.3f} vs base {ver['base_score']:.3f}; "
            f"bootstrap share {ver['share']:.1%} (need >= 90%); max drawdown {ver['dd_med']:.1%} vs base {ver['dd_base']:.1%}; "
            f"{ver['above']} of 12 above the base.", "",
            "| Half | Median | Base |", "|---|---|---|"]
    for (a, b), m, bs in zip(ver["halves"], ver["half_med"], ver["half_base"]):
        out.append(f"| {a} to {b} | {m:.3f} | {bs:.3f} |")
    out += ["", f"Walk-forward 2019-23: stitched Sharpe {ver['wf_sharpe']:.3f} vs base {ver['wf_base']:.3f}. Choices: "
            + "; ".join(f"{y} {v.name}" for y, v in ver["wf_choice"].items()) + ".", "",
            "## All versions (reported, not scored)", "",
            "| Version | CAGR | Sharpe | Max DD | Time in cash | Turnover/yr | Sold < 1 yr (short-term tax) |",
            "|---|---|---|---|---|---|---|", row(BASE.name, base)]
    for v in sorted(runs, key=lambda v: -ver["score"][v]):
        out.append(row(v.name + (" ← median" if v == med else ""), runs[v]))
    common = [d for d, _ in runs[med]["values"] if start <= d <= MEASURE_TO and d in a50 and d in n500]
    out += ["", f"## Median and base vs the indices ({common[0]} to {common[-1]}, price indices, ours net of costs)", "",
            "| Series | CAGR | Sharpe | Max DD |", "|---|---|---|---|"]
    for name, ser in [("median version", dict(runs[med]["values"])), ("base", dict(base["values"])),
                      ("NIFTY Alpha 50", a50), ("NIFTY 500", n500)]:
        vals = [(d, ser[d]) for d in common]
        out.append(f"| {name} | {cagr(vals):+.2%} | {sharpe([x for _, x in daily_returns(vals)]):.2f} | {max_drawdown(vals):.1%} |")
    py = {n: per_year([(d, s[d]) for d in common]) for n, s in
          [("median", dict(runs[med]["values"])), ("base", dict(base["values"])), ("Alpha 50", a50)]}
    out += ["", "## Per year (first year part-year)", "", "| Year | Median | Base | Alpha 50 |", "|---|---|---|---|"]
    for y in sorted(py["base"]):
        out.append(f"| {y} | {py['median'][y]:+.1%} | {py['base'][y]:+.1%} | {py['Alpha 50'][y]:+.1%} |")
    out += ["", "## Largest single-stock weight per review (median version)", "",
            " ".join(f"{x['cutoff']}: {max(x['weights'].values()):.1%}" for x in runs[med]["detail"] if x["weights"]), "",
            "2024-26 (newer price store, survivorship-biased): reported later from the VM, not part of the verdict.", ""]
    return "\n".join(out)


def worked2(bars, sessions, mkt, revs, n500) -> str:
    """Step 2 mechanics, no returns: one skip window, the filter switches in the window, the cost rate."""
    cut, eff = revs[0]
    v = Version(2, 9)
    ci = bisect.bisect_right(sessions, cut) - 1
    e, s = ci - v.skip * SESS_PER_MONTH, ci - v.skip * SESS_PER_MONTH - v.lookback * SESS_PER_MONTH
    pool = pool_at(bars, sessions, cut)
    al = {x: a for x in pool if (a := window_alpha(bars[x], mkt, sessions, cut, v))}
    top = sorted(al, key=lambda x: -al[x][0])[:5]
    out = [f"## {v.name} at cut-off {cut}", "",
           f"Alpha window: {sessions[s]} to {sessions[e]} ({e - s} returns), ending {v.skip * SESS_PER_MONTH} sessions before the cut-off.",
           f"{len(al)} of {len(pool)} eligible have >= 95% coverage. Top 5: "
           + ", ".join(f"{x} {al[x][0]:+.1%} (beta {al[x][1]:.2f})" for x in top), ""]
    for n in (150, 200):
        sw, prev = [], None
        for d in sorted(month_ends(sessions)):
            x = sma_at(n500, d, n)
            if not x or d < eff:
                continue
            st = x[0] >= x[1]
            if prev is not None and st != prev:
                sw.append(f"{d} {'in' if st else 'out'} ({x[0]:.0f} vs {x[1]:.0f})")
            prev = st
        out.append(f"SMA{n} month-end switches from {eff}: {len(sw)}: " + "; ".join(sw))
    out += ["", f"Cost per side: {cost_rate() * 1e4:.2f} bps of rupees traded.", ""]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worked", action="store_true")
    ap.add_argument("--step1", action="store_true")
    ap.add_argument("--universe", choices=["turnover", "amfi"], default="turnover",
                    help="turnover = round 1; amfi = round 2 (AMFI average market cap top 300)")
    ap.add_argument("--mechanics", action="store_true", help="round 2: universe tables only, no returns")
    ap.add_argument("--worked2", action="store_true", help="step 2 mechanics only, no returns")
    a = ap.parse_args(argv)
    global UNIVERSE
    UNIVERSE = a.universe
    bars, sessions = load()
    mkt = dict(read_index("NIFTY50"))
    n500 = read_index("NIFTY500")
    revs = reviews(sessions, AMFI_FIRST_YEAR if UNIVERSE == "amfi" else 2017)
    print(f"{len(bars)} symbols, {len(sessions)} sessions, {len(revs)} reviews, universe {UNIVERSE}", flush=True)
    if a.mechanics:
        sys.stdout.buffer.write(amfi_mechanics(bars, sessions, revs).encode("utf-8"))
        return 0
    if a.worked2:
        sys.stdout.buffer.write(worked2(bars, sessions, mkt, revs, n500).encode("utf-8"))
        return 0
    if a.worked:
        sys.stdout.buffer.write(worked(bars, sessions, mkt, revs, n500).encode("utf-8"))
        return 0
    base_gross = run_version(BASE, bars, sessions, mkt, revs, n500, 0.0)
    ok, txt = step1(base_gross)
    sys.stdout.buffer.write(txt.encode("utf-8"))
    if a.step1 or not ok:
        return 0
    rate = cost_rate()
    start = revs[0][1] if UNIVERSE == "amfi" else MEASURE_FROM
    base = run_version(BASE, bars, sessions, mkt, revs, n500, rate)
    runs = {}
    for v in GRID:
        runs[v] = run_version(v, bars, sessions, mkt, revs, n500, rate)
        print(f"  ran {v.name}", flush=True)
    ver = step2_verdict(runs, base, start)
    rep = step2_report(runs, base, ver, start, rate, dict(read_index("NIFTYALPHA50")), dict(n500))
    sys.stdout.buffer.write(("\n## Step 1\n\n" + txt + "\n# Step 2\n\n" + rep).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
