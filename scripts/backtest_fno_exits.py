#!/usr/bin/env python3
"""
QuantOS — exit-rule backtest for the F&O screener's breakouts (research)
─────────────────────────────────────────────────────────────────────────
The 22 Oct 2026 TCS trade was the right call lost to the exit: a stop judged
on 15-minute closes 20 points under entry fired on ordinary noise, and the
target was hit by a 15-minute opening spike nobody was watching. This asks,
on a year of the screener's own signals (scripts/backtest_fno_screener.py),
which stop timescale, buffer, target, trail and time limit would have made
the most -- as a FUTURES position on the underlying, so the answer is about
the exit, not the option wrapper.

Simulation, per signal (side s = +1 call / -1 put, box level L = the box
edge it broke):
  entry   the next session's first 15-minute open, E. If that open is
          already back through L the breakout failed overnight: no trade.
  stop    box: L minus k x ATR(14, daily); entry: E minus k x ATR -- judged on a 15m, 1h or daily
          CLOSE beyond it (exit at that close). The 1h and daily variants
          also carry an EMERGENCY stop 1 ATR further, hit on touch (exit at
          the level, or at the open if the bar gapped through it).
  target  none | 1R | 2R | 3R | MM (box height beyond L), R = E - stop.
          Hit on touch, filled at the level (or the open if it gapped past)
          -- i.e. a resting limit order.
  trail   none | after +1R, a stop at the highest daily close - 1 ATR,
          checked on daily closes, never loosened.
  time    exit at the close of session N.
Within a bar, adverse levels are checked before favourable ones
(conservative). Returns are % of E, signed, minus COST_PCT round trip.

Usage:
  python scripts/backtest_fno_exits.py [--filter live|fresh1|out5] [--top 25]
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

import numpy as np

BT = Path.home() / ".quantos" / "bt_fno"
IST = timezone(timedelta(hours=5, minutes=30))
COST_PCT = 0.10            # futures round trip incl. stop slippage, % of price
MAX_SESSIONS = 10
ATR_N = 14


def _ist_date(epoch: float) -> date:
    return datetime.fromtimestamp(epoch, IST).date()


def load():
    raw = pickle.loads((BT / "bars.pkl").read_bytes())
    daily = {}
    for s, rows in raw.items():
        d = {}
        for t, o, h, l, c, v in rows:
            dd = t.astimezone(IST).date() if t.tzinfo else t.date()
            d[dd] = (o, h, l, c)
        daily[s] = d
    sigs = [json.loads(l) for l in (BT / "outcomes.jsonl").read_text().splitlines() if l.strip()]
    return daily, sigs


def atr(daily: dict[date, tuple], upto: date) -> Optional[float]:
    days = sorted(d for d in daily if d <= upto)[-(ATR_N + 1):]
    if len(days) < ATR_N + 1:
        return None
    trs = []
    for a, b in zip(days, days[1:]):
        _, h, l, _ = daily[b]
        pc = daily[a][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)


class Path15:
    """One signal's 15-minute bars after the signal day, directional (+ = good)."""

    def __init__(self, arr: np.ndarray, sig_day: date, side: int):
        days = [_ist_date(t) for t in arr[:, 0]]
        start = bisect_left(days, sig_day + timedelta(days=1))
        self.bars = []                     # (session_no, is_last_of_session, is_hour_close, o, fav, adv, c) in %
        sess, prev_day, k = 0, None, 0
        rows = arr[start:]
        rdays = days[start:]
        if len(rows) == 0:
            self.entry = None
            return
        self.entry = rows[0, 1]
        e = self.entry
        for i, (row, d) in enumerate(zip(rows, rdays)):
            if d != prev_day:
                sess += 1
                prev_day, k = d, 0
                if sess > MAX_SESSIONS:
                    break
            k += 1
            last = i + 1 >= len(rows) or rdays[i + 1] != d
            o, h, l, c = row[1:5]
            conv = (lambda p: (p / e - 1) * 100 * side)
            fav, adv = (conv(h), conv(l)) if side > 0 else (conv(l), conv(h))
            self.bars.append((sess, last, last or k % 4 == 0, conv(o), fav, adv, conv(c)))


def simulate(p: Path15, lvl: float, atr_pct: float, mm: Optional[float], rule: tuple) -> Optional[tuple[float, int]]:
    basis, (anchor, k), target, trail, max_sess = rule
    stop = (lvl - k * atr_pct) if anchor == "box" else -k * atr_pct
    if stop >= 0:                                   # entry at or through the stop: breakout already failed
        return None
    r = -stop
    emerg = stop - atr_pct if basis != "15m" else None
    tgt = {"none": None, "1R": r, "2R": 2 * r, "3R": 3 * r, "MM": mm}[target]
    trail_stop, best_close, armed = None, -1e9, False
    for sess, last, hour_close, o, fav, adv, c in p.bars:
        if sess > max_sess:
            break
        if emerg is not None and adv <= emerg:
            return min(emerg, o), sess
        if tgt is not None and fav >= tgt:
            return max(tgt, o), sess
        closes_here = basis == "15m" or (basis == "1h" and hour_close) or (basis == "1d" and last)
        if closes_here and c <= stop:
            return c, sess
        if last:
            best_close = max(best_close, c)
            if trail == "atr" and (armed or best_close >= r):
                armed = True
                trail_stop = max(trail_stop if trail_stop is not None else -1e9, best_close - atr_pct)
                if c <= trail_stop:
                    return c, sess
            if sess == max_sess:
                return c, sess
    return None                                       # ran out of data before the time limit


FILTERS = {
    "live":   lambda r: (r["state"] == "FRESH" or (r["state"] == "OUT" and (r["days_out"] or 0) <= 1))
                        and not (r["side"] == "CE" and r.get("oi") == "short covering"),
    "fresh1": lambda r: r["state"] == "FRESH" or (r["state"] == "OUT" and (r["days_out"] or 0) <= 1),
    "out5":   lambda r: r["state"] in ("FRESH", "OUT"),
}

STOPS = (("box", 0.0), ("box", 0.5), ("entry", 0.75), ("entry", 1.5))
RULES = list(itertools.product(("15m", "1h", "1d"), STOPS, ("none", "1R", "2R", "3R", "MM"),
                               ("none", "atr"), (3, 5, 10)))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--filter", default="live", choices=sorted(FILTERS))
    ap.add_argument("--side", choices=["CE", "PE"])
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args(argv)

    daily, sigs = load()
    sigs = [r for r in sigs if FILTERS[args.filter](r) and r.get("box_level")
            and (not args.side or r["side"] == args.side)]
    dates = sorted({r["date"] for r in sigs})
    mid = dates[len(dates) // 2]
    cache: dict[str, np.ndarray] = {}
    prepared = []
    for r in sigs:
        s = r["symbol"]
        if s not in cache:
            f = BT / "m15" / f"{s}.npy"
            cache[s] = np.load(f) if f.exists() else np.empty((0, 5))
        if len(cache[s]) == 0:
            continue
        side = 1 if r["side"] == "CE" else -1
        t = date.fromisoformat(r["date"])
        a = atr(daily[s], t)
        p = Path15(cache[s], t, side)
        if a is None or p.entry is None or not p.bars:
            continue
        e = p.entry
        lvl = (r["box_level"] / e - 1) * 100 * side
        atr_pct = a / e * 100
        w = r.get("box_width_pct")
        height = r["box_level"] * w / (100 + w) if w else None       # ceiling - floor, from width = (c-f)/f
        mm = (lvl + height / e * 100) if height else None
        prepared.append((r, p, lvl, atr_pct, mm))
    print(f"{len(prepared)} signals with intraday data ({args.filter}{', ' + args.side if args.side else ''}); "
          f"{len(dates)} days, halves split at {mid}; cost {COST_PCT}% round trip")

    results = []
    for rule in RULES:
        rets, h1, h2, holds, skipped = [], [], [], [], 0
        for r, p, lvl, atr_pct, mm in prepared:
            if rule[2] == "MM" and mm is None:
                continue
            out = simulate(p, lvl, atr_pct, mm, rule)
            if out is None:
                skipped += 1
                continue
            ret = out[0] - COST_PCT
            rets.append(ret)
            holds.append(out[1])
            (h1 if r["date"] < mid else h2).append(ret)
        if len(rets) < 30:
            continue
        gains, losses = sum(x for x in rets if x > 0), -sum(x for x in rets if x < 0)
        results.append(dict(rule=rule, n=len(rets), mean=mean(rets), med=median(rets),
                            win=100 * sum(x > 0 for x in rets) / len(rets), pf=gains / losses if losses else 99,
                            h1=mean(h1) if h1 else 0, h2=mean(h2) if h2 else 0, hold=mean(holds), skipped=skipped))

    def show(rows, title):
        print(f"\n== {title}")
        print(f"{'stop on':7s} {'stop':>9s} {'target':>6s} {'trail':>5s} {'max':>3s} | {'n':>5s} {'mean%':>6s} {'med%':>6s} {'win':>4s} {'PF':>5s} {'hold':>4s} | {'H1':>6s} {'H2':>6s}")
        for x in rows:
            b, (an, k), t, tr, ms = x["rule"]
            print(f"{b:7s} {an:>5s}{k:4.2f} {t:>6s} {tr:>5s} {ms:3d} | {x['n']:5d} {x['mean']:+6.2f} {x['med']:+6.2f} "
                  f"{x['win']:3.0f}% {x['pf']:5.2f} {x['hold']:4.1f} | {x['h1']:+6.2f} {x['h2']:+6.2f}")

    results.sort(key=lambda x: -x["mean"])
    show(results[:args.top], f"top {args.top} by mean return per trade")
    robust = sorted((x for x in results if x["h1"] > 0 and x["h2"] > 0), key=lambda x: -min(x["h1"], x["h2"]))
    show(robust[:args.top], "positive in BOTH halves, ranked by the weaker half")

    print("\n== marginal effect (mean % per trade, averaged over all other choices)")
    for i, name in enumerate(("stop on", "stop", "target", "trail", "max sessions")):
        g = defaultdict(list)
        for x in results:
            g[x["rule"][i]].append(x["mean"])
        print(f"  {name:13s} " + "  ".join(f"{k}: {mean(v):+.2f}" for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
