#!/usr/bin/env python3
"""
QuantOS — CCI(34)/EMA52 and SMA 5/40 crosses as standalone daily signals
──────────────────────────────────────────────────────────────────────
Runs exactly docs/CCI_SMA_CROSS_SIGNALS_PREREG_2026-10-26.md on the 213 F&O
stocks' daily bars: fresh crosses enter at the next open, exit on the opposite
cross or on the screener's fixed daily rules, judged net of NIFTY over the
same days.

Reads ~/.quantos/bt_fno/bars.pkl.

Usage:
    python scripts/backtest_cci_sma_cross.py --out docs/CCI_SMA_CROSS_SIGNALS_RESULTS_2026-10-26.md
"""

from __future__ import annotations

import argparse
import math
import pickle
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_fno_entries import BT, IST  # noqa: E402
from scripts.backtest_fno_indicator_filter import indicator_states  # noqa: E402

COST = 0.10
STOP_ATR, EMERG_ATR, MAX_FIXED, MAX_CROSS = 0.75, 1.0, 10, 60
N_PASS, T_PASS = 150, 2.7
SIGNALS, EXITS = ("sma", "cci", "both"), ("opposite", "fixed")


def state_of(kind: str, st: Optional[tuple[int, int]]) -> Optional[int]:
    if st is None:
        return None
    cci, sma = st
    return {"cci": cci, "sma": sma, "both": cci if cci == sma else 0}[kind]


def crosses(states: list[Optional[int]]) -> list[tuple[int, int]]:
    """(index, side) where the state turns to +1 or -1 from anything else."""
    out = []
    for i in range(1, len(states)):
        s, p = states[i], states[i - 1]
        if s in (1, -1) and p is not None and p != s:
            out.append((i, s))
    return out


def atr(bars: list[tuple], i: int, n: int = 14) -> Optional[float]:
    if i < n:
        return None
    return mean(max(bars[k][1] - bars[k][2], abs(bars[k][1] - bars[k - 1][3]), abs(bars[k][2] - bars[k - 1][3]))
                for k in range(i - n + 1, i + 1))


def exit_opposite(bars, states, e: int, side: int) -> Optional[tuple[int, float, str]]:
    """Exit at the next open after the state stops being `side`; at the close of session 60 at the latest."""
    for j in range(e, len(bars)):
        if j - e + 1 >= MAX_CROSS:
            return j, bars[j][3], "close"
        if states[j] != side:
            return (j + 1, bars[j + 1][0], "open") if j + 1 < len(bars) else None
    return None


def exit_fixed(bars, e: int, side: int, a: float) -> Optional[tuple[int, float, str]]:
    entry = bars[e][0]
    stop = entry - side * STOP_ATR * a
    emerg = stop - side * EMERG_ATR * a
    target = entry + side * STOP_ATR * a
    for j in range(e, len(bars)):
        o, h, l, c = bars[j]
        adv, fav = (l, h) if side > 0 else (h, l)
        if (adv - emerg) * side <= 0:
            return j, (min(emerg, o) if side > 0 else max(emerg, o)) if j > e else emerg, "close"
        if (fav - target) * side >= 0:
            return j, (max(target, o) if side > 0 else min(target, o)) if j > e else target, "close"
        if (c - stop) * side <= 0 or j - e + 1 >= MAX_FIXED:
            return j, c, "close"
    return None


def run(daily: dict[str, dict[date, tuple]]) -> dict[tuple[str, str, int], list[tuple[str, float, float]]]:
    """(signal, exit, side) -> [(entry date, raw % after cost, NIFTY-adjusted %)]."""
    nifty = daily["NIFTY"]
    res: dict[tuple[str, str, int], list] = defaultdict(list)
    for s, d in daily.items():
        if s == "NIFTY":
            continue
        ds = sorted(d)
        bars = [d[x] for x in ds]
        st = indicator_states(d)
        for kind in SIGNALS:
            states = [state_of(kind, st.get(x)) for x in ds]
            for ex in EXITS:
                busy, busy_px = -1, "close"
                for i, side in crosses(states):
                    e = i + 1
                    # an exit at an open frees that open for the next entry (the reversal); one at a close doesn't
                    if e >= len(bars) or e < busy or (e == busy and busy_px == "close"):
                        continue
                    a = atr(bars, i)
                    if ex == "fixed" and not a:
                        continue
                    r = exit_opposite(bars, states, e, side) if ex == "opposite" else exit_fixed(bars, e, side, a)
                    if r is None:
                        continue
                    j, px, kind_px = r
                    busy, busy_px = j, kind_px
                    n0, n1 = nifty.get(ds[e]), nifty.get(ds[j])
                    if n0 is None or n1 is None:
                        continue
                    raw = side * (px / bars[e][0] - 1) * 100 - COST
                    mkt = (n1[0] if kind_px == "open" else n1[3]) / n0[0] - 1
                    res[(kind, ex, side)].append((ds[e].isoformat(), raw, raw - side * mkt * 100))
    return res


def stats(rows: list[tuple[str, float, float]], mid: str) -> dict:
    adj = [x for _, _, x in rows]
    by = defaultdict(list)
    for d, _, x in rows:
        by[d].append(x)
    dm = [mean(v) for v in by.values()]
    t = mean(dm) / (stdev(dm) / math.sqrt(len(dm))) if len(dm) > 2 and stdev(dm) > 0 else 0.0
    h1 = [x for d, _, x in rows if d < mid]
    h2 = [x for d, _, x in rows if d >= mid]
    return {"n": len(adj), "raw": mean(r for _, r, _ in rows), "adj": mean(adj), "win": sum(x > 0 for x in adj) / len(adj),
            "t": t, "h1": mean(h1) if h1 else float("nan"), "h2": mean(h2) if h2 else float("nan")}


def report() -> str:
    raw = pickle.loads((BT / "bars.pkl").read_bytes())
    daily = {s: {(t.astimezone(IST).date() if t.tzinfo else t.date()): (o, h, l, c) for t, o, h, l, c, v in rows}
             for s, rows in raw.items()}
    res = run(daily)
    dates = sorted({d for rows in res.values() for d, _, _ in rows})
    mid = dates[len(dates) // 2]
    out = ["# CCI(34)/EMA52 and SMA 5/40 crosses as standalone signals: results", "",
           f"Rules: docs/CCI_SMA_CROSS_SIGNALS_PREREG_2026-10-26.md. {len(daily) - 1} stocks, entries "
           f"{dates[0]} to {dates[-1]}, halves split at {mid}. % per trade after 0.1% cost; "
           f"'vs NIFTY' subtracts NIFTY's move over the same days.", "",
           "| signal | exit | side | n | raw mean | vs NIFTY mean | win (vs NIFTY) | t | H1 | H2 | verdict |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    passes = []
    for kind in SIGNALS:
        for ex in EXITS:
            for side in (1, -1):
                rows = res.get((kind, ex, side), [])
                name = "long" if side > 0 else "short"
                if not rows:
                    out.append(f"| {kind} | {ex} | {name} | 0 | | | | | | | FAIL |")
                    continue
                m = stats(rows, mid)
                ok = m["n"] >= N_PASS and m["h1"] > 0 and m["h2"] > 0 and m["t"] >= T_PASS
                if ok:
                    passes.append(f"{kind}/{ex}/{name}")
                out.append(f"| {kind} | {ex} | {name} | {m['n']} | {m['raw']:+.2f}% | {m['adj']:+.2f}% | "
                           f"{m['win']:.0%} | {m['t']:+.1f} | {m['h1']:+.2f}% | {m['h2']:+.2f}% | "
                           f"{'PASS' if ok else 'FAIL'} |")
    out[4:4] = [f"**Verdict:** {len(passes)} of 12 pass" + (f" ({', '.join(passes)})" if passes else "") + ".", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/CCI_SMA_CROSS_SIGNALS_RESULTS_2026-10-26.md")
    args = ap.parse_args()
    text = report()
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
