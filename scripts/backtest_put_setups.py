#!/usr/bin/env python3
"""
QuantOS — Put setups backtest: mirrored Darvas (A), without the near-low gate (B-A), failed rally (C)
──────────────────────────────────────────────────────────────────────────────────────────────────────
Pre-registered in docs/PUT_SETUPS_PREREG_2026-10-25.md (committed 0d930c6 before this ran).
Reads the screener backtest's bars (~/.quantos/bt_fno/bars.pkl). Results are appended to the doc.

    python scripts/backtest_put_setups.py [--workers 4]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import backtest_fno_screener as bt  # noqa: E402
from core.fno_screener.screener import bar_date, invert_bars, setup_rank  # noqa: E402

DOC = Path("docs/PUT_SETUPS_PREREG_2026-10-25.md")
OUT = bt.OUT_DIR / "put_setups.json"
WIN_FROM, WIN_TO = date(2025, 9, 2), date(2026, 10, 16)
OOW_FROM, OOW_TO = date(2024, 10, 23), date(2025, 9, 1)
COOLDOWN = 10
COST = 0.10
N_BOOT, SEED, PCTL = 10_000, 20261025, 100 / 60          # 1.67th percentile: one-sided 0.05 / 3
MIN_N, MIN_DAYS = 100, 40
H = (1, 3, 5)

_BARS: dict = {}


def _init() -> None:
    global _BARS
    _BARS = bt.load_bars()


def _darvas_puts(i: int) -> list[tuple]:
    """Session i: (date, symbol, tier, rank_A) for every inverted-bar entry that is in a downtrend
    and FRESH / OUT <= 5 sessions, any tier. rank_A = screener setup_rank (None for LAGGARD)."""
    from core.discovery.momentum_shortlist import build_shortlist
    t = bar_date(_BARS[bt.MARKET][i])
    real = {}
    for s, bs in _BARS.items():
        if s == bt.MARKET:
            continue
        cut = [c for c in bs if bar_date(c) <= t][-bt.WINDOW_BARS:]
        if cut and bar_date(cut[-1]) == t:
            real[s] = cut
    if not real:
        return []
    inv = {s: invert_bars(b) for s, b in real.items()}
    as_of = max(b[-1].timestamp for b in inv.values())
    out = []
    for e in build_shortlist(inv, as_of):
        if not e.trend_up:
            continue
        fresh = e.breakout_state == "FRESH"
        out_ok = e.breakout_state == "OUT" and e.days_above_ceil is not None and e.days_above_ceil <= 5
        if fresh or out_ok:
            r = setup_rank(e, 5)
            out.append((t.isoformat(), e.symbol, e.momentum_tier, r if r in (0, 1) else None))
    return out


def _sma(xs: list[float], n: int, k: int) -> Optional[float]:
    return sum(xs[k - n + 1:k + 1]) / n if k >= n - 1 else None


def _ema_series(xs: list[float], n: int) -> list[float]:
    a, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else out[-1] + a * (x - out[-1]))
    return out


def failed_rally(bars: list) -> list[int]:
    """Indices t where variant C fires (pre-registration, conditions 1-5)."""
    c = [b.close for b in bars]
    ema21 = _ema_series(c, 21)
    hits = []
    for t in range(60, len(bars)):
        s50, s50_10 = _sma(c, 50, t), _sma(c, 50, t - 10)
        if s50 is None or s50_10 is None or not s50 < s50_10 or not c[t] < s50:
            continue
        tested = False
        for k in range(t - 5, t):
            sk = _sma(c, 50, k)
            if sk is not None and bars[k].high >= min(ema21[k], sk):
                tested = True
                break
        if not tested:
            continue
        if not max(b.high for b in bars[t - 5:t]) < max(b.high for b in bars[t - 30:t - 5]):
            continue
        if c[t] < bars[t - 1].low:
            hits.append(t)
    return hits


def dedupe(entries: list[tuple[date, str]], cal_pos: dict) -> list[tuple[date, str]]:
    last: dict[str, int] = {}
    out = []
    for d, s in sorted(entries):
        i = cal_pos[d]
        if s in last and i - last[s] < COOLDOWN:
            continue
        last[s] = i
        out.append((d, s))
    return out


def stats(rows: list[dict], mid: date, window: str) -> dict:
    ex5 = [r["ex5"] for r in rows if r["ex5"] is not None]
    oc5 = [r["oc5"] for r in rows if r["oc5"] is not None]
    by_day: dict = defaultdict(list)
    for r in rows:
        if r["ex5"] is not None:
            by_day[r["date"]].append(r["ex5"])
    days = list(by_day)
    rng = random.Random(SEED)
    boots = []
    for _ in range(N_BOOT if days else 0):
        pool = [x for d in (rng.choice(days) for _ in days) for x in by_day[d]]
        boots.append(mean(pool))
    boots.sort()
    lo = boots[int(len(boots) * PCTL / 100)] if boots else None
    h1 = [r["ex5"] for r in rows if r["ex5"] is not None and r["date"] < mid]
    h2 = [r["ex5"] for r in rows if r["ex5"] is not None and r["date"] >= mid]

    def m(k, sub=rows):
        v = [r[k] for r in sub if r[k] is not None]
        return round(mean(v), 3) if v else None
    up = [r for r in rows if r["nifty_up"]]
    dn = [r for r in rows if not r["nifty_up"]]
    s = {"window": window, "n": len(rows), "days": len({r["date"] for r in rows}),
         "ex1": m("ex1"), "ex3": m("ex3"), "ex5": m("ex5"), "ex5_boot_lo": round(lo, 3) if lo is not None else None,
         "ex5_h1": round(mean(h1), 3) if h1 else None, "ex5_h2": round(mean(h2), 3) if h2 else None,
         "oc5_net": round(mean(oc5) - COST, 3) if oc5 else None,
         "win5": round(100 * sum(x > 0 for x in ex5) / len(ex5), 1) if ex5 else None,
         "ex5_nifty_above_ema20": m("ex5", up), "n_nifty_above": len(up),
         "ex5_nifty_below_ema20": m("ex5", dn), "n_nifty_below": len(dn)}
    s["checks"] = {
        "1 ex5>0 and boot lo>0": bool(s["ex5"] is not None and s["ex5"] > 0 and lo is not None and lo > 0),
        "2 both halves >0": bool(h1 and h2 and mean(h1) > 0 and mean(h2) > 0),
        "3 oc5 - 0.10% > 0": bool(s["oc5_net"] is not None and s["oc5_net"] > 0),
        "4 n>=100 on >=40 days": s["n"] >= MIN_N and s["days"] >= MIN_DAYS,
    }
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-doc", action="store_true", help="don't append results to the pre-registration")
    a = ap.parse_args(argv)

    bars = bt.load_bars()
    cal = bt.sessions(bars)
    pos = {d: i for i, d in enumerate(cal)}
    by_sym = {s: {bar_date(c): c for c in bs} for s, bs in bars.items()}
    syms = [s for s in bars if s != bt.MARKET]
    nifty = [c.close for c in bars[bt.MARKET]]
    nifty_ema = bt._ema(nifty)

    # ── A / B: inverted-bar Darvas, every window session ──
    idx = [i for i, d in enumerate(cal) if WIN_FROM <= d <= WIN_TO and i >= bt.WINDOW_BARS]
    print(f"A/B: {len(idx)} sessions {cal[idx[0]]} .. {cal[idx[-1]]}", flush=True)
    raw_ab = []
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init) as ex:
        for k, rows in enumerate(ex.map(_darvas_puts, idx, chunksize=4)):
            raw_ab += rows
            if k % 40 == 0:
                print(f"  {k}/{len(idx)}", flush=True)
    a_entries = [(date.fromisoformat(d), s) for d, s, tier, r in raw_ab if r is not None]
    bminus = [(date.fromisoformat(d), s) for d, s, tier, r in raw_ab if tier == "LAGGARD"]

    # ── C: failed rally, both windows ──
    c_all = []
    for s in syms:
        bs = bars[s]
        for t in failed_rally(bs):
            c_all.append((bar_date(bs[t]), s))
    in_win = lambda d: WIN_FROM <= d <= WIN_TO          # noqa: E731
    in_oow = lambda d: OOW_FROM <= d <= OOW_TO          # noqa: E731

    # ── forward moves ──
    def fwd(sym, i, h):
        if i + h >= len(cal):
            return None, None
        b0, b1, bh = by_sym[sym].get(cal[i]), by_sym[sym].get(cal[i + 1]), by_sym[sym].get(cal[i + h])
        if not (b0 and b1 and bh):
            return None, None
        cc, oc = (bh.close / b0.close - 1) * 100, (bh.close / b1.open - 1) * 100
        if abs(cc) > bt.MAX_MOVE_PCT or abs(oc) > bt.MAX_MOVE_PCT:
            return None, None
        return -cc, -oc

    base: dict = {}

    def baseline(i, h):
        if (i, h) not in base:
            xs = [v for s in syms if (v := fwd(s, i, h)[0]) is not None]
            base[(i, h)] = mean(xs) if xs else None
        return base[(i, h)]

    def outcome(d, s):
        i = pos[d]
        r = {"date": d, "symbol": s, "nifty_up": nifty[i] >= nifty_ema[i]}
        for h in H:
            cc, oc = fwd(s, i, h)
            b = baseline(i, h)
            r[f"ex{h}"] = None if cc is None or b is None else cc - b
            r[f"oc{h}"] = oc
        return r

    win_days = [d for d in cal if in_win(d)]
    mid = win_days[len(win_days) // 2]
    oow_days = [d for d in cal if in_oow(d)]
    oow_mid = oow_days[len(oow_days) // 2]
    sets = {
        "A baseline": [outcome(d, s) for d, s in dedupe(a_entries, pos)],
        "B-A LAGGARD increment": [outcome(d, s) for d, s in dedupe(bminus, pos)],
        "C failed rally": [outcome(d, s) for d, s in dedupe([x for x in c_all if in_win(x[0])], pos)],
    }
    c_oow = [outcome(d, s) for d, s in dedupe([x for x in c_all if in_oow(x[0])], pos)]
    res = {name: stats(rows, mid, f"{WIN_FROM}..{WIN_TO}") for name, rows in sets.items()}
    res["C failed rally"]["out_of_window"] = stats(c_oow, oow_mid, f"{OOW_FROM}..{OOW_TO}")
    oow_ok = res["C failed rally"]["out_of_window"]["ex5"]
    res["C failed rally"]["checks"]["5 out-of-window ex5>0"] = bool(oow_ok is not None and oow_ok > 0)
    a_keys = {(s, pos[d]) for d, s in a_entries}
    c_rows = sets["C failed rally"]
    res["C failed rally"]["overlap_with_A_pct"] = round(100 * sum(
        any((r["symbol"], pos[r["date"]] - k) in a_keys for k in range(0, 6)) for r in c_rows) / len(c_rows), 1) \
        if c_rows else None
    for v in res.values():
        v["PASS"] = all(v["checks"].values())

    OUT.write_text(json.dumps(res, indent=1, default=str))
    lines = ["", "## Results (2026-10-25)", "",
             f"Run by `scripts/backtest_put_setups.py`; raw numbers in `~/.quantos/bt_fno/put_setups.json`. "
             f"Halves split at {mid}. `ex` = % move in the put's favour minus the same-day universe average.", "",
             "| Variant | n | days | ex1 | ex3 | ex5 | ex5 boot 1.67% | ex5 H1 | ex5 H2 | oc5 − 0.10% | win5 | Result |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, v in res.items():
        lines.append(f"| {name} | {v['n']} | {v['days']} | {v['ex1']} | {v['ex3']} | {v['ex5']} | {v['ex5_boot_lo']} | "
                     f"{v['ex5_h1']} | {v['ex5_h2']} | {v['oc5_net']} | {v['win5']}% | **{'PASS' if v['PASS'] else 'FAIL'}** |")
    o = res["C failed rally"]["out_of_window"]
    lines += ["", f"C out-of-window ({o['window']}): n {o['n']} on {o['days']} days, ex5 {o['ex5']}, "
                  f"halves {o['ex5_h1']} / {o['ex5_h2']}, oc5 − 0.10% {o['oc5_net']}. "
                  f"C entries with an A entry for the same stock in the 5 sessions before: "
                  f"{res['C failed rally']['overlap_with_A_pct']}%.", "",
              "Checks failed per variant:", ""]
    for name, v in res.items():
        bad = [k for k, ok in v["checks"].items() if not ok]
        lines.append(f"- **{name}**: {', '.join(bad) if bad else 'none'}. Nifty above EMA20: ex5 "
                     f"{v['ex5_nifty_above_ema20']} (n {v['n_nifty_above']}); below: {v['ex5_nifty_below_ema20']} "
                     f"(n {v['n_nifty_below']}).")
    text = "\n".join(lines) + "\n"
    if not a.no_doc:
        with DOC.open("a", encoding="utf-8") as f:
            f.write(text)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
