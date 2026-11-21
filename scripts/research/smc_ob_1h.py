#!/usr/bin/env python3
"""NIFTY 1H SMC order block test (docs/NIFTY_SMC_OB_1H_PREREG_2026-11-22.md). Runs on the PC from the frozen
files in ~/.quantos/research/smc_ob_1h (sha256 in docs/RESEARCH_DATA.md).

    python scripts/research/smc_ob_1h.py reproduce      # step 2: spot entries vs the TradingView export, both grids
    python scripts/research/smc_ob_1h.py cases          # step 2: worked trades side by side

Step 3 (options, placebo, verdict) is not in this file until the user's go-ahead after step 2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.backtest import smc_ob_1h as eng  # noqa: E402

DATA = Path.home() / ".quantos" / "research" / "smc_ob_1h"
TV = Path(__file__).resolve().parents[2] / "backtest_results" / "SMC-OB-1H_TV_NSE_NIFTY_2026-11-22.csv"
SHA = {"NIFTY_60.csv": "c75200873218f62676e7123bafa47509f7b6d82d2bf3c85046856318d9b18268",
       "NIFTY_5.csv": "1f5092b4ac938f12eb735e294feb1e892a9e23fdc2aebdd91babfc4b45292444",
       "NIFTY_daily.csv": "89ed66310ca977d8b5a3c5105de6e69a08ba50baea0a2d3f06cc5b17aff34ac9"}
REPRO_FROM = date(2017, 12, 1)
GATE = 0.80


def check_hashes() -> None:
    for name, want in SHA.items():
        got = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f"{name}: sha256 {got} != frozen {want}")


def load_rows(name: str) -> list[tuple]:
    with (DATA / name).open() as f:
        r = csv.reader(f)
        next(r)
        return [(datetime.strptime(x[0], "%Y-%m-%d %H:%M"), *map(float, x[1:5])) for x in r]


def htf_filter(daily_path: Path):
    """Item 1: previous completed session's close > EMA40 and EMA9 > EMA40 (NSE daily closes)."""
    days, closes = [], []
    with daily_path.open() as f:
        for row in csv.DictReader(f):
            days.append(date.fromisoformat(row["date"][:10]))
            closes.append(float(row["c"]))
    e9 = e40 = None
    ok = []
    for c in closes:
        e9 = c if e9 is None else e9 + 2 / 10 * (c - e9)
        e40 = c if e40 is None else e40 + 2 / 41 * (c - e40)
        ok.append(c > e40 and e9 > e40)

    def f(d: date) -> bool:
        i = bisect_left(days, d) - 1          # the last session strictly before d
        return i >= 40 and ok[i]
    return f


def grid_a(h60: list[tuple], m5: list[tuple]) -> list[eng.Bar]:
    starts = [r[0] for r in m5]
    out = []
    for s, o, h, l, c in h60:
        i, j = bisect_left(starts, s), bisect_left(starts, s + timedelta(minutes=60))
        out.append(eng.Bar(s, o, h, l, c, tuple(m5[i:j])))
    return out


def grid_b(m5: list[tuple]) -> list[eng.Bar]:
    """Hour-aligned bins from 5-minute bars: 09:15-10:00, 10:00-11:00, ..., 15:00-15:30. A bin is labelled
    by its hour (09:00 for the first), matching the TradingView export's stamps."""
    bins = defaultdict(list)
    for r in m5:
        bins[r[0].replace(minute=0)].append(r)
    out = []
    for k in sorted(bins):
        rs = bins[k]
        out.append(eng.Bar(k, rs[0][1], max(x[2] for x in rs), min(x[3] for x in rs), rs[-1][4], tuple(rs)))
    return out


def tv_entries(path: Path = TV) -> list[dict]:
    out = []
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["Type"] == "Entry long":
                ts = datetime.strptime(row["Date and time"], "%Y-%m-%d %H:%M")
                out.append(dict(n=int(row["Trade number"]), ts=ts, price=float(row["Price"]),
                                window="am" if ts.hour < 13 else "pm"))
    exits = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["Type"] == "Exit long":
                exits[int(row["Trade number"])] = dict(ts=datetime.strptime(row["Date and time"], "%Y-%m-%d %H:%M"),
                                                      price=float(row["Price"]), signal=row["Signal"],
                                                      bars=int(row["Duration (bars)"]))
    for e in out:
        e["exit"] = exits.get(e["n"])
    return out


def match(trades: list[eng.Trade], tv: list[dict]) -> dict:
    ours = {(t.entry_time.date(), t.window): t for t in trades}
    tvs = [e for e in tv if e["ts"].date() >= REPRO_FROM]
    hit = [e for e in tvs if (e["ts"].date(), e["window"]) in ours]
    tv_keys = {(e["ts"].date(), e["window"]) for e in tv}
    extra = [t for t in trades if t.entry_time.date() >= REPRO_FROM
             and t.entry_time.date() <= max(e["ts"].date() for e in tv)
             and (t.entry_time.date(), t.window) not in tv_keys]
    return dict(n_tv=len(tvs), matched=len(hit), rate=len(hit) / len(tvs), missed=[e for e in tvs if e not in hit],
                extra=extra, ours=ours)


def reproduce() -> int:
    check_hashes()
    h60, m5 = load_rows("NIFTY_60.csv"), load_rows("NIFTY_5.csv")
    htf = htf_filter(DATA / "NIFTY_daily.csv")
    tv = tv_entries()
    res = {}
    for name, bars, starts in (("a (Fyers 09:15 grid)", grid_a(h60, m5), eng.GRID_A),
                               ("b (hour-aligned grid)", grid_b(m5), eng.GRID_B)):
        trades = eng.run(bars, htf, starts, allow_from=date(2017, 11, 22))
        m = match(trades, tv)
        res[name] = (trades, m)
        print(f"grid {name}: {len(trades)} trades; TradingView entries from {REPRO_FROM} matched "
              f"{m['matched']}/{m['n_tv']} = {m['rate']:.0%}; our entries not in TradingView: {len(m['extra'])}")
    best = max(res, key=lambda k: res[k][1]["rate"])
    ra, rb = (res[k][1]["rate"] for k in res)
    if abs(ra - rb) <= 0.02:
        best = next(iter(res))
    m = res[best][1]
    print(f"\nchosen grid {best}: gate {'PASSED' if m['rate'] >= GATE else 'FAILED'} ({m['rate']:.0%} vs {GATE:.0%})")
    print("missed TradingView entries:", ", ".join(f"#{e['n']} {e['ts']:%Y-%m-%d %H:%M}" for e in m["missed"]) or "none")
    print("our extra entries:", ", ".join(f"{t.entry_time:%Y-%m-%d %H:%M}" for t in m["extra"]) or "none")
    return 0


CASES = (54, 44, 78, 92, 85, 68)   # chosen 2026-11-22: am time stop, Friday pm entry, am target, am stop, pm stop, the one miss


def cases() -> int:
    """Step 2's worked trades: this engine (grid b) against the TradingView export, spot only."""
    check_hashes()
    bars = grid_b(load_rows("NIFTY_5.csv"))
    trades = eng.run(bars, htf_filter(DATA / "NIFTY_daily.csv"), eng.GRID_B, allow_from=date(2017, 11, 22))
    ours = {(t.entry_time.date(), t.window): t for t in trades}
    for e in tv_entries():
        if e["n"] not in CASES:
            continue
        x = e["exit"]
        print()
        print(f"TV #{e['n']} {e['ts']:%a %Y-%m-%d %H:%M} entry {e['price']:.2f} -> {x['ts']:%a %m-%d %H:%M} "
              f"{x['price']:.2f} {x['signal']} ({x['bars']} bars)")
        t = ours.get((e["ts"].date(), e["window"]))
        if t is None:
            near = [u for u in trades if abs((u.entry_time.date() - e["ts"].date()).days) <= 3]
            print("  ours: no entry that day/window; nearby:", ", ".join(f"{u.entry_time:%a %m-%d %H:%M}" for u in near))
            continue
        print(f"  ours  signal bar {t.signal_start:%H:%M}, entry {t.entry_time:%a %Y-%m-%d %H:%M} {t.entry:.2f}; "
              f"ATR {t.atr:.1f}, OB bottom {t.ob_bot:.2f}, risk {t.risk:.1f} -> stop {t.stop0:.2f}, target {t.target:.2f}")
        mv = "; ".join(f"{a:%m-%d %H:%M} {b:.2f}" for a, b in t.stops) or "none"
        print(f"        stop moves: {mv}")
        print(f"        exit {t.exit_time:%a %m-%d %H:%M} {t.exit:.2f} {t.reason} ({t.bars_held} bars)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["reproduce", "cases"])
    a = ap.parse_args(argv)
    return reproduce() if a.step == "reproduce" else cases()


if __name__ == "__main__":
    sys.exit(main())
