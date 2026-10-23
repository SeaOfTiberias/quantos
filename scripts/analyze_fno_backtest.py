#!/usr/bin/env python3
"""
QuantOS — analyse the F&O screener backtest (scripts/backtest_fno_screener.py)
───────────────────────────────────────────────────────────────────────────────
Two questions, from ~/.quantos/bt_fno/outcomes.jsonl:

  direction  Which setup filters pick stocks that then move the right way?
             Per group: n, distinct signal days, mean raw move and mean EXCESS
             move (signal minus the same-day F&O universe average, signed for
             the side) at 1/3/5 sessions, % of excess > 0, and the same mean
             in the first and second half of the window (a filter that only
             works in one half is regime, not edge).

  spreads    For the signals that pass a filter, how should the spread be
             built? Every long strike (ATM, the screener's ITM contract) x
             every short strike on the chain, the short's distance measured
             in 5-session expected moves (EM5 = spot x IV x sqrt(7/365)),
             returns at 1/3/5 sessions at bhavcopy closes, gross and after a
             flat per-leg, per-side cost of COST_PCT of the leg's price.

Overlap warning: a stock that stays OUT for 5 sessions appears up to 5 times
and signals cluster on the same days, so n overstates independent evidence.
"Days" is the honest denominator.

Usage:
  python scripts/analyze_fno_backtest.py direction
  python scripts/analyze_fno_backtest.py spreads [--filter fresh1] [--cost 2]
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Callable, Optional

OUTCOMES = Path.home() / ".quantos" / "bt_fno" / "outcomes.jsonl"
H = (1, 3, 5)


def load() -> list[dict]:
    return [json.loads(l) for l in OUTCOMES.read_text().splitlines() if l.strip()]


def state_bucket(r: dict) -> str:
    if r["state"] == "NEAR":
        return "NEAR"
    if r["state"] == "FRESH":
        return "FRESH"
    d = r["days_out"] or 0
    return "OUT1" if d <= 1 else "OUT2-3" if d <= 3 else "OUT4-5"


def _tercile(rows: list[dict], key: str) -> Callable[[dict], str]:
    xs = sorted(r[key] for r in rows if r.get(key) is not None)
    if not xs:
        return lambda r: "n/a"
    a, b = xs[len(xs) // 3], xs[2 * len(xs) // 3]
    return lambda r: "n/a" if r.get(key) is None else (f"low <{a:.3g}" if r[key] < a else
                                                         f"mid" if r[key] < b else f"high >={b:.3g}")


def _fmt(v: Optional[float], w: int = 6) -> str:
    return f"{v:+{w}.2f}" if v is not None else " " * (w - 1) + "-"


def table(title: str, rows: list[dict], key: Callable[[dict], str], mid_date: str) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    print(f"\n== {title}")
    print(f"{'group':22s} {'n':>5s} {'days':>4s} | {'raw5':>6s} | {'ex1':>6s} {'ex3':>6s} {'ex5':>6s} {'win5':>5s} | {'ex5 H1':>6s} {'ex5 H2':>6s}")
    for g in sorted(groups):
        rs = groups[g]
        def m(k, sub=rs):
            v = [r[k] for r in sub if r.get(k) is not None]
            return mean(v) if v else None
        ex5 = [r["ex5"] for r in rs if r.get("ex5") is not None]
        win = 100 * sum(x > 0 for x in ex5) / len(ex5) if ex5 else None
        h1 = [r for r in rs if r["date"] < mid_date]
        h2 = [r for r in rs if r["date"] >= mid_date]
        print(f"{g[:22]:22s} {len(rs):5d} {len({r['date'] for r in rs}):4d} | {_fmt(m('cc5'))} | "
              f"{_fmt(m('ex1'))} {_fmt(m('ex3'))} {_fmt(m('ex5'))} {(f'{win:4.0f}%' if win is not None else '    -')} | "
              f"{_fmt(m('ex5', h1))} {_fmt(m('ex5', h2))}")


FILTERS: dict[str, Callable[[dict], bool]] = {
    "all":     lambda r: True,
    "fresh1":  lambda r: state_bucket(r) in ("FRESH", "OUT1"),
    "live":    lambda r: state_bucket(r) in ("FRESH", "OUT1") and not (r["side"] == "CE" and r.get("oi") == "short covering"),
    "near":    lambda r: r["state"] == "NEAR",
    "out5":    lambda r: r["state"] in ("FRESH", "OUT"),
}


def direction(rows: list[dict]) -> None:
    dates = sorted({r["date"] for r in rows})
    mid = dates[len(dates) // 2]
    print(f"{len(rows)} signals, {len(dates)} days {dates[0]} .. {dates[-1]}; halves split at {mid}")
    print("raw5 / exN = % move in the pick's direction (excess = minus same-day universe average)")
    for side in ("CE", "PE"):
        rs = [r for r in rows if r["side"] == side]
        print(f"\n######## {side} ########")
        table("setup state", rs, state_bucket, mid)
        fr = [r for r in rs if state_bucket(r) in ("FRESH", "OUT1")]
        table("FRESH+OUT1 by futures OI build-up", fr, lambda r: r.get("oi") or "n/a", mid)
        table("FRESH+OUT1 by Nifty vs EMA20", fr, lambda r: "Nifty above" if r["nifty_above_ema20"] else "Nifty below", mid)
        table("FRESH+OUT1 by momentum tier", fr, lambda r: r["tier"], mid)
        table("FRESH+OUT1 by box width", fr, _tercile(fr, "box_width_pct"), mid)
        table("FRESH+OUT1 by volume ratio", fr, _tercile(fr, "vol_ratio"), mid)
        table("FRESH+OUT1 by liquid contract", fr, lambda r: "has contract" if r.get("contract") else "none", mid)
        table("all states by Darvas bucket", rs, lambda r: r["bucket"], mid)


# ─── spreads ─────────────────────────────────────────────────────────────────

def _k_bucket(k: float) -> str:
    for lo, hi in ((0, 0.75), (0.75, 1.25), (1.25, 1.75), (1.75, 2.5), (2.5, 99)):
        if lo <= k < hi:
            return f"{lo:g}-{hi:g} EM5"
    return "?"


def spreads(rows: list[dict], cost_pct: float) -> None:
    c = cost_pct / 100
    res: dict[tuple, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    used = 0
    for r in rows:
        ch, k = r.get("chain"), r.get("contract")
        if not ch or not k or not k.get("iv") or not ch["spot"][0]:
            continue
        s0, iv = ch["spot"][0], k["iv"]
        em5 = s0 * iv * math.sqrt(7 / 365)
        sign = 1 if r["side"] == "CE" else -1
        strikes = {float(x): v for x, v in ch["strikes"].items()}
        if not strikes:
            continue
        atm = min(strikes, key=lambda x: abs(x - s0))
        used += 1
        for long_name, kl in (("ATM", atm), ("ITM", float(k["strike"]))):
            pl = strikes.get(kl)
            if not pl or not pl[0]:
                continue
            for j, h in enumerate(H, 1):                           # single option
                if pl[j]:
                    res[(long_name, "single")][h].append((pl[j] * (1 - c)) / (pl[0] * (1 + c)) * 100 - 100)
            for ks, ps in strikes.items():
                if (ks - kl) * sign <= 0 or not ps or not ps[0]:
                    continue
                d0 = pl[0] * (1 + c) - ps[0] * (1 - c)
                if d0 <= 0 or d0 >= abs(ks - kl):
                    continue
                kb = _k_bucket(abs(ks - s0) / em5)
                for j, h in enumerate(H, 1):
                    if pl[j] and ps[j]:
                        v = pl[j] * (1 - c) - ps[j] * (1 + c)
                        res[(long_name, kb)][h].append((v / d0 - 1) * 100)
    print(f"{used} signals with a chain; cost {cost_pct:g}% of each leg's price per side")
    print(f"{'long':5s} {'short at':14s} | " + " | ".join(f"{'n':>5s} {'mean'+str(h):>7s} {'med'+str(h):>6s} {'win':>4s}" for h in H))
    for key in sorted(res, key=lambda k: (k[0], k[1] != "single", k[1])):
        cells = []
        for h in H:
            v = res[key][h]
            cells.append(f"{len(v):5d} {mean(v):+7.1f} {median(v):+6.1f} {100 * sum(x > 0 for x in v) / len(v):3.0f}%"
                         if v else f"{0:5d} {'-':>7s} {'-':>6s} {'-':>4s}")
        print(f"{key[0]:5s} {key[1]:14s} | " + " | ".join(cells))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["direction", "spreads"])
    ap.add_argument("--filter", default="live", choices=sorted(FILTERS))
    ap.add_argument("--side", choices=["CE", "PE"])
    ap.add_argument("--cost", type=float, default=0.0, help="per-leg, per-side cost as %% of the leg's price")
    args = ap.parse_args(argv)
    rows = load()
    if args.what == "direction":
        direction(rows)
    else:
        rows = [r for r in rows if FILTERS[args.filter](r) and (not args.side or r["side"] == args.side)]
        spreads(rows, args.cost)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
