#!/usr/bin/env python3
"""
QuantOS — 50/200 DMA cross (A) and price/DMA cross (B), parameter permutation, 2016-23
────────────────────────────────────────────────────────────────────────────────────────
Pre-registered in docs/MA_CROSS_PREREG_2026-11-27.md (dae5cc8, signed off by the user
before any code or run). Long only. Data, universe, split/bonus adjustment, equal-weight
benchmark and costs are the Darvas OOS run's own (scripts/backtest_darvas_atr_stop_oos.py),
imported unchanged; only the trade rules below are new.

    python scripts/backtest_ma_cross.py --worked     # five headline trades per rule, then stop
    python scripts/backtest_ma_cross.py              # the full grid, once; writes the results doc

Rules (pure functions, tests in tests/unit/test_backtest_ma_cross.py):
  A: SMA(fast) closes above SMA(slow) today, at or below yesterday -> buy next open;
     exit when SMA(fast) < SMA(slow) at a close.
  B: close above SMA(D) today, at or below yesterday -> buy next open; exit when the close
     is below SMA(D).
  Exit "atr k": also exit when the close falls below the trail, where after each close
     trail = max(trail, highest close since entry - k * ATR14(Wilder)); a close is checked
     against the trail set at the previous close. Every exit fills at the next open.
"""

from __future__ import annotations

import argparse
import bisect
import json
import random
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ENTRY_FROM, ENTRY_TO = date(2016, 11, 1), date(2023, 9, 30)      # signal dates
FASTS, SLOWS, DS = (40, 45, 50, 55, 60), (180, 190, 200, 210, 220), (40, 45, 50, 55, 60)
EXITS = (None, 2.5, 3.0, 4.0)                                     # None = signal only
ATR_N = 14
BOOT, SEED, PLACEBO_RUNS = 10_000, 20261127, 200
WF_YEARS = range(2018, 2024)
BREADTH = 0.70
DATA_END_NEAR = date(2023, 12, 15)       # a series ending before this stopped trading (delisted/merged)
CACHE = Path.home() / ".quantos" / "ma_cross_trades.json"
OUT = Path("docs/MA_CROSS_RESULTS_2026-11-27.md")


# ─── indicators ──────────────────────────────────────────────────────────────

def sma(xs: list[float], n: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def wilder_atr(rows: list[dict], n: int = ATR_N) -> list[Optional[float]]:
    """ATR at each bar, equal to core.darvas.weekly_discovery._atr(bars[:i+1]) once n true
    ranges exist (mean of the first n, then Wilder smoothing); None before that."""
    out: list[Optional[float]] = [None] * len(rows)
    trs: list[float] = []
    atr = None
    for i in range(1, len(rows)):
        h, l, pc = rows[i]["h"], rows[i]["l"], rows[i - 1]["c"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        if atr is None:
            trs.append(tr)
            if len(trs) == n:
                atr = sum(trs) / n
        else:
            atr = tr / n + atr * (1 - 1 / n)
        out[i] = atr
    return out


# ─── one version on one symbol ───────────────────────────────────────────────

def version_key(rule: str, a: int, b: Optional[int], k: Optional[float]) -> str:
    ex = "signal" if k is None else f"atr{k:g}"
    return f"A {a}/{b} {ex}" if rule == "A" else f"B {a} {ex}"


def simulate(rows: list[dict], rule: str, a: int, b: Optional[int], k: Optional[float],
             eligible: Callable[[date], bool], entry_from: date = ENTRY_FROM, entry_to: date = ENTRY_TO,
             atr: Optional[list] = None, smas: Optional[dict] = None) -> list[dict]:
    """Trades of one version on one symbol's adjusted bars (dicts with date, o, h, l, c)."""
    closes = [r["c"] for r in rows]
    smas = smas if smas is not None else {}
    for n in (a, b) if rule == "A" else (a,):
        if n not in smas:
            smas[n] = sma(closes, n)
    if rule == "A":
        f, s = smas[a], smas[b]
        up = lambda i: f[i] is not None and s[i] is not None and f[i] > s[i]
    else:
        m = smas[a]
        up = lambda i: m[i] is not None and closes[i] > m[i]
    ready = (lambda i: smas[a][i] is not None and smas[b][i] is not None) if rule == "A" \
        else (lambda i: smas[a][i] is not None)
    if k is not None and atr is None:
        atr = wilder_atr(rows)
    trades, i, last = [], 1, len(rows) - 1
    while i < last:
        d = rows[i]["date"]
        if d > entry_to:
            break
        if not (d >= entry_from and ready(i - 1) and up(i) and not up(i - 1) and eligible(d)):
            i += 1
            continue
        e = i + 1                                         # entry at the next open
        hc, trail, j, reason = None, None, e, None
        while True:
            c = closes[j]
            if not up(j):
                reason = "signal"
            elif trail is not None and c < trail:
                reason = "trail"
            if reason or j == last:
                break
            if k is not None and atr[j] is not None:
                hc = c if hc is None else max(hc, c)
                t = hc - k * atr[j]
                trail = t if trail is None else max(trail, t)
            j += 1
        if j == last:                                     # data end, or the symbol stopped trading: marked at its last close
                                                          # (also when the exit signal falls on that bar: no next open)
            ended = "open" if rows[last]["date"] >= DATA_END_NEAR else "delisted"
            trades.append(dict(signal_date=d.isoformat(), entry_date=rows[e]["date"].isoformat(),
                               entry_price=rows[e]["o"], exit_date=rows[j]["date"].isoformat(),
                               exit_price=closes[j], reason=ended, hold=j - e))
            break
        x = j + 1
        trades.append(dict(signal_date=d.isoformat(), entry_date=rows[e]["date"].isoformat(),
                           entry_price=rows[e]["o"], exit_date=rows[x]["date"].isoformat(),
                           exit_price=rows[x]["o"], reason=reason, hold=x - e,
                           exit_close=c, trail=trail))
        i = x                                             # a new signal can come from the exit day on
    return trades


def grid() -> list[tuple[str, int, Optional[int], Optional[float]]]:
    out = [("A", f, s, k) for f in FASTS for s in SLOWS for k in EXITS]
    out += [("B", d, None, k) for d in DS for k in EXITS]
    return out


# ─── scoring (pure) ──────────────────────────────────────────────────────────

def median_version(scores: dict[str, float]) -> str:
    """Ranked lowest to highest; the lower of the two middle versions (50th of 100, 10th of 20)."""
    ranked = sorted(scores, key=lambda v: (scores[v], v))
    return ranked[len(ranked) // 2 - 1] if len(ranked) % 2 == 0 else ranked[len(ranked) // 2]


def week_bootstrap_ci(trades: list[dict], key: str, boot: int = BOOT, seed: int = SEED) -> tuple[float, float]:
    weeks = defaultdict(list)
    for t in trades:
        weeks[date.fromisoformat(t["entry_date"]).isocalendar()[:2]].append(t[key])
    groups, rng, means = list(weeks.values()), random.Random(seed), []
    for _ in range(boot):
        pick = [x for _ in groups for x in rng.choice(groups)]
        means.append(statistics.mean(pick))
    means.sort()
    return means[int(0.05 * boot)], means[int(0.95 * boot)]


def walk_forward(by_version: dict[str, list[dict]], years=WF_YEARS) -> tuple[list[dict], list[tuple[int, str]]]:
    """Each year: the version with the best mean excess on all earlier entries; keep its trades
    entered that year. Ties go to the first version in grid order (dict order)."""
    kept, chosen = [], []
    for y in years:
        best, best_s = None, None
        for v, tr in by_version.items():
            past = [t["excess"] for t in tr if int(t["entry_date"][:4]) < y]
            if past and (best_s is None or statistics.mean(past) > best_s):
                best, best_s = v, statistics.mean(past)
        if best is None:
            continue
        chosen.append((y, best))
        kept += [t for t in by_version[best] if int(t["entry_date"][:4]) == y]
    return kept, chosen


def profit_factor(nets: list[float]) -> float:
    g, l = sum(x for x in nets if x > 0), -sum(x for x in nets if x < 0)
    return g / l if l else float("inf")


def worst_drawdown(trades: list[dict], key: str = "net") -> float:
    peak = run = dd = 0.0
    for t in sorted(trades, key=lambda t: (t["exit_date"], t["entry_date"])):
        run += t[key]
        peak = max(peak, run)
        dd = min(dd, run - peak)
    return dd


def verdict(scores: dict[str, float], med_trades: list[dict], wf_trades: list[dict]) -> list[tuple[str, bool, str]]:
    lo, hi = week_bootstrap_ci(med_trades, "excess")
    m = statistics.mean(t["excess"] for t in med_trades)
    pos = sum(s > 0 for s in scores.values())
    need = -(-int(BREADTH * 100) * len(scores) // 100)
    h1 = [t["excess"] for t in med_trades if t["entry_date"][:4] <= "2019"]
    h2 = [t["excess"] for t in med_trades if t["entry_date"][:4] >= "2020"]
    wf = statistics.mean(t["excess"] for t in wf_trades) if wf_trades else float("nan")
    return [
        ("1 median version: mean excess > 0 and 90% CI lower end > 0", m > 0 and lo > 0,
         f"mean {m:+.2%}, CI {lo:+.2%} .. {hi:+.2%}, n={len(med_trades)}"),
        ("2 breadth: >= 70% of versions with mean excess > 0", pos >= need, f"{pos} of {len(scores)} (need {need})"),
        ("3 both halves > 0", bool(h1) and bool(h2) and statistics.mean(h1) > 0 and statistics.mean(h2) > 0,
         f"2016-19 {statistics.mean(h1) if h1 else float('nan'):+.2%} (n={len(h1)}), "
         f"2020-23 {statistics.mean(h2) if h2 else float('nan'):+.2%} (n={len(h2)})"),
        ("4 walk-forward mean excess > 0", bool(wf_trades) and wf > 0, f"{wf:+.2%} (n={len(wf_trades)})"),
    ]


# ─── data plumbing (the Darvas OOS run's, unchanged) ─────────────────────────

def membership(snapshots) -> Callable[[str, date], bool]:
    starts = [s.valid_from.date() for s in snapshots]

    def member(sym: str, d: date) -> bool:
        i = max(0, bisect.bisect_right(starts, d) - 1)
        return sym in snapshots[i].symbols
    return member


_G: dict = {}


def _init(adj, snaps, ew_days, ew_lvls):
    _G["adj"], _G["member"], _G["lvl"] = adj, membership(snaps), level_fn(ew_days, ew_lvls)


def _work(sym: str) -> tuple[str, dict]:
    """Every version's trades on one symbol, compact: (entry, exit, net, excess, reason, hold)."""
    rows, member, lvl = _G["adj"][sym], _G["member"], _G["lvl"]
    atr, smas, out = wilder_atr(rows), {}, {}
    for rule, a, b, k in grid():
        tr = simulate(rows, rule, a, b, k, lambda d: member(sym, d), atr=atr, smas=smas)
        enrich(tr, sym, lvl)
        out[version_key(rule, a, b, k)] = [(t["entry_date"], t["exit_date"], t["net"], t["excess"], t["reason"],
                                            t["hold"]) for t in tr]
    return sym, out


def load_all():
    from scripts import backtest_darvas_atr_stop_oos as oos
    raw = oos.load_bhavcopies()
    snaps = oos.build_universe(raw)
    members = sorted(frozenset().union(*(s.symbols for s in snaps)))
    actions = oos.load_actions()
    adj = {s: oos.adjust(raw[s], actions.get(s, [])) for s in members}
    return adj, snaps, members


def enrich(trades: list[dict], sym: str, lvl) -> None:
    from scripts.backtest_darvas_atr_stop_oos import net_return
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL
    for t in trades:
        t["symbol"] = sym
        t["net"] = net_return(t, STRESSED_COST_MODEL)
        a, b = lvl(date.fromisoformat(t["entry_date"])), lvl(date.fromisoformat(t["exit_date"]))
        t["excess"] = t["net"] - (b / a - 1) if a and b else None


def level_fn(days, lvls):
    def lvl(d: date):
        i = bisect.bisect_right(days, d) - 1
        return lvls[i] if i >= 0 else None
    return lvl


# ─── placebo and report ─────────────────────────────────────────────────────

def placebo(trades: list[dict], adj, snaps, runs: int = PLACEBO_RUNS, seed: int = SEED) -> list[float]:
    """Mean net return of each run: every trade keeps its symbol and holding length, its entry
    moves to a random universe-eligible session in the same calendar year (entry next open,
    exit at the open `hold` sessions later)."""
    from scripts.backtest_darvas_atr_stop_oos import net_return
    from scripts.backtest_darvas_box_width import STRESSED_COST_MODEL
    member, rng = membership(snaps), random.Random(seed)
    slots: dict = {}
    for t in trades:
        key = (t["symbol"], int(t["entry_date"][:4]), max(1, t["hold"]))
        if key not in slots:
            rows = adj[t["symbol"]]
            slots[key] = [i for i, r in enumerate(rows) if r["date"].year == key[1] and member(key[0], r["date"])
                          and i + 1 + key[2] < len(rows)]
    means = []
    for _ in range(runs):
        nets = []
        for t in trades:
            key = (t["symbol"], int(t["entry_date"][:4]), max(1, t["hold"]))
            if not slots[key]:
                continue
            i, rows = rng.choice(slots[key]), adj[t["symbol"]]
            fake = dict(entry_price=rows[i + 1]["o"], exit_price=rows[i + 1 + key[2]]["o"])
            nets.append(net_return(fake, STRESSED_COST_MODEL))
        means.append(statistics.mean(nets))
    return means


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else float("nan")


def build_report(by_version: dict[str, list[dict]], adj, snaps) -> str:
    out = ["# 50/200 DMA cross and price/DMA cross: results (2016-23)", "",
           "Pre-registered in `docs/MA_CROSS_PREREG_2026-11-27.md` (dae5cc8). Run once with "
           "`scripts/backtest_ma_cross.py`. Long only, Stressed costs, Rs 1,00,000 per trade; excess = net return "
           "minus the equal-weight universe over the same dates.", ""]
    for rule, title in (("A", "A. Golden cross (fast/slow SMA)"), ("B", "B. Close crosses the SMA")):
        vs = {v: tr for v, tr in by_version.items() if v.startswith(rule + " ")}
        clean = {v: [t for t in tr if t["excess"] is not None] for v, tr in vs.items()}
        scores = {v: _mean(t["excess"] for t in tr) for v, tr in clean.items() if tr}
        med = median_version(scores)
        best = max(scores, key=scores.get)
        wf_trades, chosen = walk_forward(clean)
        checks = verdict(scores, clean[med], wf_trades)
        passed = all(ok for _, ok, _ in checks)
        mt = clean[med]
        nets = [t["net"] for t in mt]
        out += [f"## {title}", "",
                f"**Median version: {med}** (score {scores[med]:+.2%}); best version {best} ({scores[best]:+.2%}).", ""]
        out += [f"- {name}: {'holds' if ok else '**FAILS**'} ({detail})" for name, ok, detail in checks]
        out += ["", f"**{'PASS' if passed else 'FAIL'}**", ""]
        missing = sum(len(vs[v]) - len(clean[v]) for v in vs)
        out += ["### Reported, not scored", "",
                f"- Median version: profit factor {profit_factor(nets):.2f}, mean net {_mean(nets):+.2%}, "
                f"win rate {sum(x > 0 for x in nets) / len(nets):.1%}, worst running-sum drawdown "
                f"{worst_drawdown(mt):+.1%} (sum of per-trade net returns), median hold "
                f"{statistics.median(t['hold'] for t in mt):.0f} sessions.",
                "- Median version per entry year (mean excess): " + ", ".join(
                    f"{y}: {_mean(t['excess'] for t in mt if t['entry_date'][:4] == str(y)):+.2%} "
                    f"(n={sum(t['entry_date'][:4] == str(y) for t in mt)})" for y in range(2016, 2024)),
                "- Walk-forward choice per year: " + ", ".join(f"{y}: {v}" for y, v in chosen)]
        head = version_key(rule, 50, 200 if rule == "A" else None, None)
        out.append(f"- Headline version {head}: mean excess {scores.get(head, float('nan')):+.2%}, "
                   f"mean net {_mean(t['net'] for t in clean[head]):+.2%}, n={len(clean[head])}.")
        for ex in ("signal", "atr2.5", "atr3", "atr4"):
            sub = {v: s for v, s in scores.items() if v.endswith(" " + ex)}
            m = median_version(sub)
            tr = clean[m]
            trail = sum(t["reason"] == "trail" for t in tr) / len(tr)
            out.append(f"- Exit {ex}: median version {m} ({sub[m]:+.2%}); {sum(s > 0 for s in sub.values())} of "
                       f"{len(sub)} versions > 0; share of its trades closed by the trail {trail:.0%}.")
        pl = sorted(placebo(mt, adj, snaps))
        p = sum(x >= _mean(nets) for x in pl) / len(pl)
        out.append(f"- Placebo (random entry, same symbol/year/hold, {len(pl)} runs): median version's mean net "
                   f"{_mean(nets):+.2%} vs placebo median {statistics.median(pl):+.2%}, "
                   f"5th-95th {pl[int(.05 * len(pl))]:+.2%} .. {pl[int(.95 * len(pl))]:+.2%}; p = {p:.3f}.")
        if missing:
            out.append(f"- {missing} trades had no benchmark level and are left out of excess figures.")
        out.append("- 2024-26 (L1 store, survivorship-biased): not run here; the L1 store lives on the VM.")
        out += ["", "### The grid", "", "| Version | Trades | Win rate | Mean net | Mean excess | Median hold |",
                "|---|---|---|---|---|---|"]
        for v in sorted(scores, key=lambda v: -scores[v]):
            tr = clean[v]
            out.append(f"| {v}{' (median)' if v == med else ''} | {len(tr)} | "
                       f"{sum(t['net'] > 0 for t in tr) / len(tr):.1%} | {_mean(t['net'] for t in tr):+.2%} | "
                       f"{scores[v]:+.2%} | {statistics.median(t['hold'] for t in tr):.0f} |")
        out.append("")
    return "\n".join(out) + "\n"


# ─── worked cases ────────────────────────────────────────────────────────────

def worked(adj, snaps, members) -> str:
    from scripts.backtest_darvas_atr_stop_oos import ew_index
    member = membership(snaps)
    lvl = level_fn(*ew_index(adj, snaps))
    out = []
    for rule, a, b in (("A", 50, 200), ("B", 50, None)):
        found = []
        for sym in members:
            rows = adj[sym]
            for t in simulate(rows, rule, a, b, None, lambda d, s=sym: member(s, d)):
                found.append((t["signal_date"], sym, t))
        for _, sym, t in sorted(found)[:5]:
            enrich([t], sym, lvl)
        found.sort()
        out.append(f"\n## {version_key(rule, a, b, None)}: first five entries\n")
        for _, sym, t in found[:5]:
            rows = adj[sym]
            idx = {r["date"].isoformat(): i for i, r in enumerate(rows)}
            closes = [r["c"] for r in rows]
            i = idx[t["signal_date"]]
            sm = {n: sma(closes, n) for n in ((a, b) if rule == "A" else (a,))}
            ma = ", ".join(f"SMA{n} {sm[n][i - 1]:.2f} -> {sm[n][i]:.2f}" for n in sm)
            out.append(f"- **{sym}** signal {t['signal_date']} (close {closes[i - 1]:.2f} -> {closes[i]:.2f}; {ma}); "
                       f"entry {t['entry_date']} open {t['entry_price']:.2f}; exit ({t['reason']}) "
                       f"{t['exit_date']} {t['exit_price']:.2f}, held {t['hold']} sessions; "
                       f"net {t['net']:+.2%}, excess {t['excess']:+.2%}")
            atr = wilder_atr(rows)
            t3 = [x for x in simulate(rows, rule, a, b, 3.0, lambda d, s=sym: member(s, d), atr=atr)
                  if x["signal_date"] == t["signal_date"]]
            if t3:
                x = t3[0]
                enrich([x], sym, lvl)
                why = (f"close {x['exit_close']:.2f} < trail {x['trail']:.2f}" if x["reason"] == "trail"
                       else f"close {x.get('exit_close', 0):.2f} below the average")
                out.append(f"  - ATR 3: exit ({x['reason']}: {why}) {x['exit_date']} {x['exit_price']:.2f}, "
                           f"held {x['hold']}; net {x['net']:+.2%}, excess {x['excess']:+.2%}")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worked", action="store_true", help="five headline trades per rule, no grid")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    adj, snaps, members = load_all()
    print(f"{len(members)} symbols ever in the universe", flush=True)
    if a.worked:
        sys.stdout.buffer.write(worked(adj, snaps, members).encode("utf-8"))
        return 0
    from scripts.backtest_darvas_atr_stop_oos import ew_index
    ew_days, ew_lvls = ew_index(adj, snaps)
    print("equal-weight index built", flush=True)
    by_version: dict[str, list[dict]] = {version_key(*g): [] for g in grid()}
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init,
                             initargs=(adj, snaps, ew_days, ew_lvls)) as ex:
        for n, (sym, res) in enumerate(ex.map(_work, members, chunksize=4), 1):
            for v, tr in res.items():
                by_version[v] += [dict(symbol=sym, entry_date=e, exit_date=x, net=net, excess=exc, reason=r, hold=h)
                                  for e, x, net, exc, r, h in tr]
            if n % 100 == 0:
                print(f"[{n}/{len(members)}]", flush=True)
    report = build_report(by_version, adj, snaps)
    OUT.write_text(report, encoding="utf-8")
    sys.stdout.buffer.write(report.encode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
