#!/usr/bin/env python3
"""
QuantOS — CCI(34)/EMA52 and SMA 5/40 as filters on the F&O screener's picks
──────────────────────────────────────────────────────────────────────────
Runs exactly docs/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md: the screener
backtest's signals and exit (scripts/backtest_fno_entries.py), one trade per
breakout episode, kept vs rejected by each filter on the signal day.

Reads ~/.quantos/bt_fno/{bars.pkl, outcomes.jsonl, m15/*.npy}.

Usage:
    python scripts/backtest_fno_indicator_filter.py --out docs/FNO_INDICATOR_FILTER_RESULTS_2026-10-26.md
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_fno_entries import BT, IST, Sym, atr_at, trade  # noqa: E402

CCI_N, CCI_EMA, SMA_FAST, SMA_SLOW = 34, 52, 5, 40
N_PASS, T_PASS = 100, 2.7
FILTERS = ("cci", "sma", "both")


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def indicator_states(daily: dict[date, tuple]) -> dict[date, tuple[int, int]]:
    """Per day: (CCI(34) vs its EMA52, SMA5 vs SMA40), each +1 / -1 / 0; missing until warmed up."""
    ds = sorted(daily)
    tp = [(daily[d][1] + daily[d][2] + daily[d][3]) / 3 for d in ds]
    close = [daily[d][3] for d in ds]
    alpha = 2.0 / (CCI_EMA + 1)
    ema, seen, out = None, 0, {}
    for i, d in enumerate(ds):
        cci_state = None
        if i >= CCI_N - 1:
            w = tp[i - CCI_N + 1:i + 1]
            m = sum(w) / CCI_N
            md = sum(abs(x - m) for x in w) / CCI_N
            cci = (tp[i] - m) / (0.015 * md) if md else 0.0
            ema = cci if ema is None else ema + alpha * (cci - ema)
            seen += 1
            if seen >= CCI_EMA:
                cci_state = _sign(cci - ema)
        sma_state = None
        if i >= SMA_SLOW - 1:
            sma_state = _sign(sum(close[i - SMA_FAST + 1:i + 1]) / SMA_FAST - sum(close[i - SMA_SLOW + 1:i + 1]) / SMA_SLOW)
        if cci_state is not None and sma_state is not None:
            out[d] = (cci_state, sma_state)
    return out


def agrees(f: str, st: tuple[int, int], side: int) -> bool:
    cci, sma = st
    return {"cci": cci == side, "sma": sma == side, "both": cci == side and sma == side}[f]


def stats(rows: list[tuple[str, float]], mid: str) -> dict:
    if not rows:
        return {"n": 0}
    rets = [r for _, r in rows]
    by = defaultdict(list)
    for d, r in rows:
        by[d].append(r)
    dm = [mean(v) for v in by.values()]
    t = mean(dm) / (stdev(dm) / math.sqrt(len(dm))) if len(dm) > 2 and stdev(dm) > 0 else 0.0
    h1 = [r for d, r in rows if d < mid]
    h2 = [r for d, r in rows if d >= mid]
    return {"n": len(rets), "days": len(dm), "mean": mean(rets), "win": sum(r > 0 for r in rets) / len(rets),
            "t": t, "h1": mean(h1) if h1 else float("nan"), "h2": mean(h2) if h2 else float("nan")}


def _row(label: str, s: dict, verdict: str = "") -> str:
    if not s["n"]:
        return f"| {label} | 0 | | | | | | | {verdict} |"
    return (f"| {label} | {s['n']} | {s['days']} | {s['mean']:+.2f}% | {s['win']:.0%} | {s['t']:+.1f} | "
            f"{s['h1']:+.2f}% | {s['h2']:+.2f}% | {verdict} |")


HEAD = ("| | n | days | mean/trade | win | t (day-clustered) | H1 | H2 | verdict |\n"
        "|---|---|---|---|---|---|---|---|---|")


def collect() -> tuple[dict[str, list], str, int]:
    raw = pickle.loads((BT / "bars.pkl").read_bytes())
    daily = {s: {(t.astimezone(IST).date() if t.tzinfo else t.date()): (o, h, l, c) for t, o, h, l, c, v in rows}
             for s, rows in raw.items()}
    cal = sorted(daily["NIFTY"])
    nxt = {d: cal[i + 1] for i, d in enumerate(cal[:-1])}
    sigs = [json.loads(l) for l in (BT / "outcomes.jsonl").read_text().splitlines() if l.strip()]
    sigs = sorted((r for r in sigs if r["state"] in ("FRESH", "OUT") and r.get("box_level")), key=lambda r: r["date"])
    dates = sorted({r["date"] for r in sigs})
    mid = dates[len(dates) // 2]
    states = {s: indicator_states(d) for s, d in daily.items()}
    syms: dict[str, Optional[Sym]] = {}

    def sym(s: str) -> Optional[Sym]:
        if s not in syms:
            f = BT / "m15" / f"{s}.npy"
            arr = np.load(f) if f.exists() else None
            syms[s] = Sym(arr) if arr is not None and arr.size else None
        return syms[s]

    # each row: (signal date, return %, side, indicator state on the signal day)
    sets: dict[str, list] = {"CE baseline": [], "PE baseline": [], "PE H1 retest": []}
    base_done, h1_done = set(), set()
    no_state = 0
    for r in sigs:
        s, t = r["symbol"], date.fromisoformat(r["date"])
        side = 1 if r["side"] == "CE" else -1
        episode = (s, r["side"], round(r["box_level"], 2))
        S, d1 = sym(s), nxt.get(t)
        if S is None or d1 is None or d1 not in daily[s]:
            continue
        i1, a = S.day_index(d1), atr_at(daily[s], t)
        if i1 is None or not a:
            continue
        st = states[s].get(t)
        if st is None:
            no_state += 1
            continue
        if episode not in base_done:
            x = trade(S, i1, S.a[i1, 1], side, a, True)
            if x is not None:
                base_done.add(episode)
                sets[f"{r['side']} baseline"].append((r["date"], x, side, st))
        if side < 0 and episode not in h1_done:
            p = r["box_level"] - 0.25 * a
            sess, day = 0, None
            for i in range(i1, len(S.a)):
                if S.days[i] != day:
                    day, sess = S.days[i], sess + 1
                    if sess > 3:
                        break
                o, h = S.a[i, 1], S.a[i, 2]
                if h >= p:
                    y = trade(S, i, max(o, p), side, a, False)
                    if y is not None:
                        h1_done.add(episode)
                        sets["PE H1 retest"].append((r["date"], y, side, st))
                    break
    return sets, mid, no_state


def report() -> str:
    sets, mid, no_state = collect()
    out = ["# F&O screener — CCI(34)/EMA52 and SMA 5/40 filters: results", "",
           f"Rules: docs/FNO_INDICATOR_FILTER_PREREG_2026-10-26.md. One trade per breakout episode; "
           f"halves split at {mid}; {no_state} signal rows skipped for indicator warm-up. Returns are % per trade "
           f"after 0.1% cost (futures on the underlying).", ""]
    verdicts = []
    for name, rows in sets.items():
        allrows = [(d, x) for d, x, _, _ in rows]
        base = stats(allrows, mid)
        out += [f"## {name}", "", HEAD, _row("unfiltered", base)]
        for f in FILTERS:
            kept = [(d, x) for d, x, side, st in rows if agrees(f, st, side)]
            rej = [(d, x) for d, x, side, st in rows if not agrees(f, st, side)]
            k = stats(kept, mid)
            ok = (k["n"] >= N_PASS and k["h1"] > 0 and k["h2"] > 0 and k["t"] >= T_PASS
                  and k["h1"] > base["h1"] and k["h2"] > base["h2"])
            v = "PASS" if ok else "FAIL"
            verdicts.append(f"{name} × {f}: {v}")
            out += [_row(f"{f}: kept", k, v), _row(f"{f}: rejected", stats(rej, mid))]
        out.append("")
    out[4:4] = ["**Verdicts:** " + "; ".join(verdicts), ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/FNO_INDICATOR_FILTER_RESULTS_2026-10-26.md")
    args = ap.parse_args()
    text = report()
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
