#!/usr/bin/env python3
"""
QuantOS — pre-registered entry tests for the F&O screener's breakouts
──────────────────────────────────────────────────────────────────────
Runs exactly the four hypotheses in docs/FNO_ENTRY_SEARCH_PREREG_2026-10-23.md
(H1 retest, H2 relative strength, H3 failed breakout, H4 no chase) against a
baseline (every signal at the next open), with ONE fixed exit: stop on a daily
close 0.75 ATR beyond the entry plus an emergency stop 1 ATR further on touch,
resting 1R target, out at the close of session 10. Futures on the underlying,
0.1% round trip. Pass = mean > 0 in both halves, day-clustered t >= 2.7,
n >= 150, and better than the side's baseline.

Reads ~/.quantos/bt_fno/{bars.pkl, outcomes.jsonl, m15/*.npy}.
"""

from __future__ import annotations

import json
import math
import pickle
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

import numpy as np

BT = Path.home() / ".quantos" / "bt_fno"
IST = timezone(timedelta(hours=5, minutes=30))
COST = 0.10
STOP_ATR, EMERG_ATR, TARGET_R, MAX_SESS = 0.75, 1.0, 1.0, 10
T_PASS, N_PASS = 2.7, 150


class Sym:
    def __init__(self, arr: np.ndarray):
        self.a = arr
        self.days = [datetime.fromtimestamp(t, IST).date() for t in arr[:, 0]]
        self.first: dict[date, int] = {}
        for i, d in enumerate(self.days):
            self.first.setdefault(d, i)

    def day_index(self, d: date) -> Optional[int]:
        return self.first.get(d)


def trade(s: Sym, i0: int, entry: float, side: int, atr: float, check_entry_bar: bool) -> Optional[float]:
    """Signed % return of one futures trade entered at `entry` in bar i0."""
    stop = entry - side * STOP_ATR * atr
    emerg = stop - side * EMERG_ATR * atr
    target = entry + side * TARGET_R * STOP_ATR * atr
    sess, day = 1, s.days[i0]                      # the entry day is session 1
    for i in range(i0 if check_entry_bar else i0 + 1, len(s.a)):
        d = s.days[i]
        if d != day:
            day, sess = d, sess + 1
        o, h, l, c = s.a[i, 1:5]
        adv, fav = (l, h) if side > 0 else (h, l)
        if (adv - emerg) * side <= 0:
            px = min(emerg, o) if side > 0 else max(emerg, o)
            return side * (px / entry - 1) * 100 - COST
        if (fav - target) * side >= 0:
            px = max(target, o) if side > 0 else min(target, o)
            return side * (px / entry - 1) * 100 - COST
        last = i + 1 >= len(s.a) or s.days[i + 1] != d
        if last:
            if (c - stop) * side <= 0 or sess >= MAX_SESS:
                return side * (c / entry - 1) * 100 - COST
    return None


def atr_at(daily: dict[date, tuple], upto: date, n: int = 14) -> Optional[float]:
    ds = sorted(x for x in daily if x <= upto)[-(n + 1):]
    if len(ds) < n + 1:
        return None
    return mean(max(daily[b][1] - daily[b][2], abs(daily[b][1] - daily[a][3]), abs(daily[b][2] - daily[a][3]))
                for a, b in zip(ds, ds[1:]))


def ret_n(daily: dict[date, tuple], d: date, n: int = 20) -> Optional[float]:
    ds = sorted(x for x in daily if x <= d)
    if len(ds) <= n:
        return None
    return (daily[ds[-1]][3] / daily[ds[-1 - n]][3] - 1) * 100


def summarize(name: str, rows: list[tuple[str, float]], mid: str, base_mean: Optional[float]) -> float:
    if not rows:
        print(f"  {name:26s} n=0")
        return float("nan")
    rets = [r for _, r in rows]
    by = defaultdict(list)
    for d, r in rows:
        by[d].append(r)
    dm = [mean(v) for v in by.values()]
    t = mean(dm) / (stdev(dm) / math.sqrt(len(dm))) if len(dm) > 2 and stdev(dm) > 0 else 0.0
    h1 = [r for d, r in rows if d < mid]
    h2 = [r for d, r in rows if d >= mid]
    m1, m2, m = (mean(h1) if h1 else float("nan")), (mean(h2) if h2 else float("nan")), mean(rets)
    ok = (m1 > 0 and m2 > 0 and t >= T_PASS and len(rets) >= N_PASS
          and (base_mean is None or m > base_mean))
    win = 100 * sum(r > 0 for r in rets) / len(rets)
    verdict = "" if base_mean is None else ("PASS" if ok else "fail")
    print(f"  {name:26s} n={len(rets):5d} days={len(dm):3d} mean={m:+.2f}% win={win:3.0f}% "
          f"t={t:+.1f} H1={m1:+.2f} H2={m2:+.2f}  {verdict}")
    return m


def main() -> int:
    raw = pickle.loads((BT / "bars.pkl").read_bytes())
    daily = {s: {(t.astimezone(IST).date() if t.tzinfo else t.date()): (o, h, l, c) for t, o, h, l, c, v in rows}
             for s, rows in raw.items()}
    cal = sorted(daily["NIFTY"])
    nxt = {d: cal[i + 1] for i, d in enumerate(cal[:-1])}
    sigs = [json.loads(l) for l in (BT / "outcomes.jsonl").read_text().splitlines() if l.strip()]
    sigs = [r for r in sigs if r["state"] in ("FRESH", "OUT") and r.get("box_level")]
    dates = sorted({r["date"] for r in sigs})
    mid = dates[len(dates) // 2]
    syms: dict[str, Optional[Sym]] = {}

    def sym(s: str) -> Optional[Sym]:
        if s not in syms:
            f = BT / "m15" / f"{s}.npy"
            arr = np.load(f) if f.exists() else None
            syms[s] = Sym(arr) if arr is not None and arr.size else None
        return syms[s]

    res = {k: {"CE": [], "PE": []} for k in ("base", "H1", "H2", "H3", "H4")}
    for r in sigs:
        s, t = r["symbol"], date.fromisoformat(r["date"])
        side = 1 if r["side"] == "CE" else -1
        S, d1 = sym(s), nxt.get(t)
        if S is None or d1 is None or d1 not in daily[s]:
            continue
        i1 = S.day_index(d1)
        a = atr_at(daily[s], t)
        if i1 is None or not a:
            continue
        L, close_t = r["box_level"], daily[s][t][3]
        o1 = S.a[i1, 1]

        # baseline + H4 (no chase) + H2 (relative strength): next open
        x = trade(S, i1, o1, side, a, True)
        if x is not None:
            res["base"][r["side"]].append((r["date"], x))
            if side * (o1 - close_t) <= 0.5 * a:
                res["H4"][r["side"]].append((r["date"], x))
            rs, rn = ret_n(daily[s], t), ret_n(daily["NIFTY"], t)
            if rs is not None and rn is not None and side * (rs - rn) > 5:
                res["H2"][r["side"]].append((r["date"], x))

        # H1 retest: limit at L + 0.25 ATR (toward the trade), valid 3 sessions
        p = L + side * 0.25 * a
        sess, day = 0, None
        for i in range(i1, len(S.a)):
            if S.days[i] != day:
                day, sess = S.days[i], sess + 1
                if sess > 3:
                    break
            o, h, l, c = S.a[i, 1:5]
            if (l <= p) if side > 0 else (h >= p):
                fill = min(o, p) if side > 0 else max(o, p)
                y = trade(S, i, fill, side, a, False)
                if y is not None:
                    res["H1"][r["side"]].append((r["date"], y))
                break

        # H3 failed breakout: FRESH/OUT1 closes back inside within 2 sessions -> opposite side next open
        if r["state"] == "FRESH" or (r["days_out"] or 0) <= 1:
            d = t
            for _ in range(2):
                d = nxt.get(d)
                if d is None or d not in daily[s]:
                    break
                if (daily[s][d][3] - L) * side < 0:
                    d2 = nxt.get(d)
                    j = S.day_index(d2) if d2 else None
                    a2 = atr_at(daily[s], d)
                    if j is not None and a2:
                        z = trade(S, j, S.a[j, 1], -side, a2, True)
                        if z is not None:
                            res["H3"]["PE" if side > 0 else "CE"].append((d.isoformat(), z))
                    break

    print(f"{len(sigs)} FRESH/OUT<=5 signals, {len(dates)} days, halves split at {mid}")
    print(f"exit: daily-close stop {STOP_ATR} ATR + emergency {EMERG_ATR} ATR, {TARGET_R}R target, "
          f"{MAX_SESS} sessions; cost {COST}%; pass: both halves > 0, t >= {T_PASS}, n >= {N_PASS}, > baseline")
    for side in ("CE", "PE"):
        print(f"\n{side} (H3 rows here = failed {'put breakdowns, traded long' if side == 'CE' else 'call breakouts, traded short'})")
        b = summarize("baseline (next open)", res["base"][side], mid, None)
        for k, name in (("H1", "H1 retest limit"), ("H2", "H2 relative strength"),
                        ("H3", "H3 failed breakout (fade)"), ("H4", "H4 no chase")):
            summarize(name, res[k][side], mid, b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
