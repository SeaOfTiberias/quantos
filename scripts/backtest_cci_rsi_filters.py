#!/usr/bin/env python3
"""
Part B of docs/CCI_CPR_SIGNAL_AND_FILTERS_PREREG_2026-11-07.md: CCI(34) +/-50 and RSI(14) 40/60
as blocks on the F&O screener backtest's trades. The trades, exit and deduplication are exactly
those of scripts/backtest_fno_indicator_filter.py (2026-10-26); only the filters differ.

Reads ~/.quantos/bt_fno/{bars.pkl, outcomes.jsonl, m15/*.npy}. Returns the report section as text.
"""

from __future__ import annotations

import json
import pickle
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.cci_cpr import cci, wilder_rsi  # noqa: E402
from scripts.backtest_fno_entries import BT, IST, Sym, atr_at, trade  # noqa: E402
from scripts.backtest_fno_indicator_filter import HEAD, _row, stats  # noqa: E402

N_PASS, T_PASS, MIN_BLOCK, MIN_GAP = 100, 2.7, 0.10, 0.30


def daily_values(daily: dict[date, tuple]) -> dict[date, tuple[float, float]]:
    """Per day: (CCI(34), RSI(14)) from the stock's own daily bars; days before warm-up omitted."""
    ds = sorted(daily)
    h = np.array([daily[d][1] for d in ds], float)
    l = np.array([daily[d][2] for d in ds], float)
    c = np.array([daily[d][3] for d in ds], float)
    cc, rs = cci(h, l, c), wilder_rsi(c)
    return {d: (cc[i], rs[i]) for i, d in enumerate(ds) if not (np.isnan(cc[i]) or np.isnan(rs[i]))}


def blocked(f: str, v: tuple[float, float], side: int) -> bool:
    """F1 CCI: put blocked when CCI < -50, call when > +50. F2 RSI: put when RSI < 40, call when > 60."""
    cc, rs = v
    if f == "cci":
        return cc < -50 if side < 0 else cc > 50
    return rs < 40 if side < 0 else rs > 60


def collect():
    raw = pickle.loads((BT / "bars.pkl").read_bytes())
    daily = {s: {(t.astimezone(IST).date() if t.tzinfo else t.date()): (o, h, l, c) for t, o, h, l, c, v in rows}
             for s, rows in raw.items()}
    cal = sorted(daily["NIFTY"])
    nxt = {d: cal[i + 1] for i, d in enumerate(cal[:-1])}
    sigs = [json.loads(x) for x in (BT / "outcomes.jsonl").read_text().splitlines() if x.strip()]
    sigs = sorted((r for r in sigs if r["state"] in ("FRESH", "OUT") and r.get("box_level")), key=lambda r: r["date"])
    dates = sorted({r["date"] for r in sigs})
    mid = dates[len(dates) // 2]
    vals = {s: daily_values(d) for s, d in daily.items()}
    syms: dict[str, Optional[Sym]] = {}

    def sym(s: str) -> Optional[Sym]:
        if s not in syms:
            f = BT / "m15" / f"{s}.npy"
            arr = np.load(f) if f.exists() else None
            syms[s] = Sym(arr) if arr is not None and arr.size else None
        return syms[s]

    sets: dict[str, list] = {"CE baseline": [], "PE baseline": [], "PE H1 retest": []}
    base_done, h1_done = set(), set()
    no_value = 0
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
        v = vals[s].get(t)
        if v is None:
            no_value += 1
            continue
        if episode not in base_done:
            x = trade(S, i1, S.a[i1, 1], side, a, True)
            if x is not None:
                base_done.add(episode)
                sets[f"{r['side']} baseline"].append((r["date"], x, side, v))
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
                        sets["PE H1 retest"].append((r["date"], y, side, v))
                    break
    return sets, mid, no_value


def report() -> tuple[str, list[str]]:
    sets, mid, no_value = collect()
    out = ["## Part B: CCI and RSI as entry filters", "",
           f"F&O screener backtest trades, one per breakout episode; halves split at {mid}; {no_value} signal "
           f"rows skipped for indicator warm-up. % per trade after 0.1% cost.", ""]
    verdicts = []
    for name, rows in sets.items():
        base = stats([(d, x) for d, x, _, _ in rows], mid)
        out += [f"### {name}", "", HEAD, _row("unfiltered", base)]
        for f in ("cci", "rsi"):
            kept = [(d, x) for d, x, side, v in rows if not blocked(f, v, side)]
            rej = [(d, x) for d, x, side, v in rows if blocked(f, v, side)]
            k, b = stats(kept, mid), stats(rej, mid)
            share = len(rej) / len(rows) if rows else 0.0
            gap = (k["mean"] - b["mean"]) if k["n"] and b["n"] else float("nan")
            checks = {
                "kept n >= 100": k["n"] >= N_PASS,
                "kept > 0 both halves": k["n"] > 0 and k["h1"] > 0 and k["h2"] > 0,
                "t >= 2.7": k["n"] > 0 and k["t"] >= T_PASS,
                "beats unfiltered both halves": k["n"] > 0 and k["h1"] > base["h1"] and k["h2"] > base["h2"],
                "blocks >= 10%": share >= MIN_BLOCK,
                "blocked worse by >= 0.30 pp": gap == gap and gap >= MIN_GAP,
            }
            v = "PASS" if all(checks.values()) else "FAIL"
            failed = [c for c, ok in checks.items() if not ok]
            verdicts.append(f"{name} × {f}: {v}")
            out += [_row(f"{f}: kept", k, v), _row(f"{f}: blocked ({share:.0%})", b)]
            out.append(f"| {f}: kept − blocked | {gap:+.2f} pp | | | | | | | {'failed: ' + ', '.join(failed) if failed else ''} |")
        out.append("")
    return "\n".join(out), verdicts


if __name__ == "__main__":
    text, verdicts = report()
    print(text)
    print(verdicts)
