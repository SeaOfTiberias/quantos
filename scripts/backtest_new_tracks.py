#!/usr/bin/env python3
"""
QuantOS — New tracks backtest: surge bull put credit spreads (A) and EUR/USD-GBP/USD cointegration (B)
──────────────────────────────────────────────────────────────────────────────────────────────────────
Pre-registered in docs/NEW_TRACKS_PREREG_2026-10-24.md (committed before this ran).
Results are appended to that file.

    python scripts/backtest_new_tracks.py --prepare     # track A data passes only (cached)
    python scripts/backtest_new_tracks.py               # both tracks, Stage 1 + Stage 2, report
"""

from __future__ import annotations

import argparse
import pickle
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.evaluator import TIERS, Gates, stage1, stage2  # noqa: E402
from core.options.vrp.bhavcopy import DEFAULT_RAW_CACHE_DIR  # noqa: E402
from core.surge import put_credit as pc  # noqa: E402
from core.surge.spreads import FALLBACK_NOTIONAL  # noqa: E402

DOC = Path("docs/NEW_TRACKS_PREREG_2026-10-24.md")
P1_CACHE = pc.CACHE / "pc_pass1.pkl"
P2_CACHE = pc.CACHE / "pc_pass2.pkl"
SPLIT_A, SPLIT_B = date(2023, 7, 1), date(2013, 7, 1)
EVENTS_TO = date(2026, 9, 24)      # pre-registration: 2,571 events, 2020-03-02 to 2026-09-24
WORKERS = 4


def bhav_days() -> list[tuple[date, Path]]:
    out = []
    for p in sorted(DEFAULT_RAW_CACHE_DIR.glob("*.zip")):
        try:
            out.append((date(int(p.stem[:4]), int(p.stem[4:6]), int(p.stem[6:8])), p))
        except ValueError:
            continue
    return out


def load_events():
    from scripts.surge_spread_stage2 import load_events as le
    panel, branch = le()
    return panel, branch


def pass1(symbols: set[str]):
    if P1_CACHE.exists():
        return pickle.loads(P1_CACHE.read_bytes())
    days = bhav_days()
    cal = [d for d, _ in days]
    jobs = [(p, d, symbols, cal) for d, p in days]
    futs, ivs = [], []
    with ProcessPoolExecutor(WORKERS) as ex:
        for n, (f, iv) in enumerate(ex.map(pc.pass1_day, jobs, chunksize=8), 1):
            futs += f
            ivs += iv
            if n % 200 == 0:
                print(f"  pass 1: {n}/{len(jobs)} days", flush=True)
    fut = pd.DataFrame(futs, columns=["date", "symbol", "expiry", "close"])
    ivr = pd.DataFrame(ivs, columns=["date", "symbol", "expiry", "F", "K", "ce", "pe"])
    P1_CACHE.parent.mkdir(parents=True, exist_ok=True)
    P1_CACHE.write_bytes(pickle.dumps((fut, ivr)))
    return fut, ivr


def gate_events(panel, events, fut, ivr):
    cal = pc.Calendar([d for d, _ in bhav_days()])
    ranks = pc.iv_rank(pc.atm_iv(ivr))
    fexp = defaultdict(set)
    fclose = {}
    fby = defaultdict(dict)                      # (symbol, expiry) -> {date: futures close}
    for r in fut.itertuples():
        fexp[(r.symbol, r.date)].add(r.expiry)
        fclose[(r.symbol, r.date, r.expiry)] = r.close
        fby[(r.symbol, r.expiry)][r.date] = r.close
    skips, chosen = Counter(), []
    for e in events:
        d = panel.dates[e.t]
        rk = ranks.get((e.symbol, d))
        if rk is None:
            skips["no IV rank (< 200 IV days)"] += 1
            continue
        if rk < pc.IVR_GATE:
            skips["IV rank < 0.70"] += 1
            continue
        ex = pc.pick_expiry(fexp.get((e.symbol, d), ()), d, cal, pc.TRADE_MIN_TDAYS)
        if ex is None:
            skips["no expiry with >= 10 trading days"] += 1
            continue
        F = fclose.get((e.symbol, d, ex))
        if not F:
            near = sorted(x for x in fexp.get((e.symbol, d), ()) if x > d)
            F = fclose.get((e.symbol, d, near[0])) if near else None
        if not F:
            skips["no futures price"] += 1
            continue
        chosen.append((e.symbol, d, ex, F, rk))
    return chosen, skips, cal, fby, len(ranks)


def pass2(chosen, cal):
    if P2_CACHE.exists():
        cached_keys, rows = pickle.loads(P2_CACHE.read_bytes())
        if cached_keys == sorted((s, d, e) for s, d, e, _, _ in chosen):
            return rows
    wanted = defaultdict(lambda: defaultdict(set))
    for s, d, e, _, _ in chosen:
        last = cal.last_before(e) or cal.days[-1]
        for x in cal.days[cal.pos[d]:cal.pos[last] + 1]:
            wanted[x][s].add(e)
    paths = dict((d, p) for d, p in bhav_days())
    jobs = [(paths[d], d, {s: set(v) for s, v in w.items()}) for d, w in sorted(wanted.items())]
    rows = []
    with ProcessPoolExecutor(WORKERS) as ex:
        for n, r in enumerate(ex.map(pc.pass2_day, jobs, chunksize=8), 1):
            rows += r
            if n % 200 == 0:
                print(f"  pass 2: {n}/{len(jobs)} days", flush=True)
    df = pd.DataFrame(rows, columns=["date", "symbol", "expiry", "strike", "close", "settle", "contracts", "lot"])
    P2_CACHE.write_bytes(pickle.dumps((sorted((s, d, e) for s, d, e, _, _ in chosen), df)))
    return df


def track_a(prepare_only: bool = False):
    panel, events = load_events()
    events = [e for e in events if panel.dates[e.t] <= EVENTS_TO]     # the pre-registered range
    symbols = set(panel.symbols)
    print(f"track A: {len(events)} events, {len(symbols)} symbols", flush=True)
    fut, ivr = pass1(symbols)
    chosen, skips, cal, fby, n_ranks = gate_events(panel, events, fut, ivr)
    print(f"track A: {len(chosen)} events pass the IV-rank gate", flush=True)
    pe = pass2(chosen, cal)
    if prepare_only:
        return None
    lot24 = pe[(pe["lot"] > 0) & (pe["date"] >= date(2024, 1, 1))].sort_values("date").groupby("symbol")["lot"].first()
    by = {k: g for k, g in pe.groupby(["symbol", "expiry"])}
    trades, fb_total = [], Counter()
    for s, d, e, F, rk in chosen:
        g = by.get((s, e))
        if g is None:
            skips["no put rows"] += 1
            continue
        pick = pc.choose_strikes(g[g["date"] == d], F, d, e)
        if pick is None:
            skips["no strikes in the delta bands"] += 1
            continue
        sh, lo = pick
        credit = float(sh["close"] - lo["close"])
        width = float(sh["strike"] - lo["strike"])
        if not (0 < credit < width):
            skips["credit not in (0, width)"] += 1
            continue
        lot = int(sh["lot"]) if sh["lot"] > 0 else int(lot24.get(s, 0)) or max(1, round(FALLBACK_NOTIONAL / F))
        legs = g[g["strike"].isin([sh["strike"], lo["strike"]])]
        rows = {(r.date, r.strike): (r.close, r.settle, r.contracts) for r in legs.itertuples()}
        futs = fby.get((s, e), {})
        ex_d, vals, why, fb = pc.walk(s, d, e, float(sh["strike"]), float(lo["strike"]), credit, lot, rows, futs, cal)
        fb_total += fb
        if ex_d is None or ex_d not in vals:
            skips["open at data end" if why == "open at data end" else "no exit price"] += 1
            continue
        vals = {k: v for k, v in vals.items() if k <= ex_d}
        marks = {sc: pc.marks_for(d, credit, width, lot, float(sh["close"]), float(lo["close"]), vals, c)
                 for sc, c in pc.SCENARIOS.items()}
        trades.append(pc.PutTrade(s, d, ex_d, e, float(sh["strike"]), float(lo["strike"]), credit, width, lot, why, marks))
    return trades, skips, fb_total, cal, len(events), n_ranks


def track_b():
    from core.fx_coint import model as fx
    df = fx.load()
    out = {sc: fx.run(df, sc) for sc in fx.PIPS}
    cal = [d.date() for d in df.index if d.date() >= date(2000, 1, 3)]
    return out, cal


def fmt(x, pct=False):
    if x != x:
        return "n/a"
    return f"{x:+.2%}" if pct else f"{x:.2f}"


def s1_row(name, s):
    return (f"| {name} | {s.n} | {fmt(s.pf)} | {fmt(s.sharpe)} | {s.win:.0%} | {fmt(s.mean, True)} | "
            f"{fmt(s.pf_halves[0])} / {fmt(s.pf_halves[1])} ({s.n_halves[0]} / {s.n_halves[1]}) | "
            f"{fmt(s.boot_lo, True)} | {'PASS' if s.passed else 'FAIL'} |")


def s2_rows(name, trades, cal):
    out, passed = [], []
    for tier in TIERS:
        r = stage2(trades, cal, tier)
        passed.append((tier, r.passed))
        out.append(f"| {name} | ₹{tier:,.0f} | ₹{r.end:,.0f} | {r.max_dd:.1%} | {r.taken} | {r.lockouts} | "
                   f"{r.busy} | {r.no_edge} | {r.kills} | {r.warmup} | {'PASS' if r.passed else 'FAIL'} |")
    return out, passed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prepare", action="store_true")
    a = ap.parse_args()
    if a.prepare:
        track_a(prepare_only=True)
        return 0
    A = track_a()
    a_trades, a_skips, a_fb, a_cal, a_events, a_ranks = A
    a_days = [d for d in a_cal.days if d >= min(t.entry for t in a_trades)] if a_trades else a_cal.days
    (b_runs, b_cal) = track_b()

    lines = ["", "---", "", "## Results", "",
             f"Run {date.today()}: `python scripts/backtest_new_tracks.py`. Stressed costs gate; Base is shown for "
             "reference. Gates as pre-registered; bootstrap bound = 2.5th percentile (two tracks).", ""]
    s1 = {}
    s1["A stressed"] = stage1([t.eval_trade("stressed") for t in a_trades], a_days, SPLIT_A, Gates(min_trades=100))
    s1["A base"] = stage1([t.eval_trade("base") for t in a_trades], a_days, SPLIT_A, Gates(min_trades=100))
    s1["B stressed"] = stage1(b_runs["stressed"][0], b_cal, SPLIT_B, Gates(min_trades=30))
    s1["B base"] = stage1(b_runs["base"][0], b_cal, SPLIT_B, Gates(min_trades=30))

    lines += ["### Stage 1 (per-trade screen)", "",
              "| Track, costs | Trades | PF | Sharpe | Won | Mean return on risk | PF halves (n) | Bootstrap 2.5% | Verdict |",
              "|---|---|---|---|---|---|---|---|---|",
              s1_row("A surge bull put credit, Stressed", s1["A stressed"]),
              s1_row("A surge bull put credit, Base (reference)", s1["A base"]),
              s1_row("B EUR/USD–GBP/USD, Stressed 4 pips", s1["B stressed"]),
              s1_row("B EUR/USD–GBP/USD, Base 1 pip (reference)", s1["B base"]), ""]
    for k in ("A stressed", "B stressed"):
        failed = [c for c, ok in s1[k].checks.items() if not ok]
        lines.append(f"- {k}: " + ("all checks pass." if not failed else "failed " + ", ".join(failed) + "."))
    lines.append("")

    lines += ["### Stage 2 (real-NAV quarter-Kelly, Stressed)", "",
              "Reported for both tracks; it only counts for a Stage 1 pass.", "",
              "| Track | Start | End | Max DD | Taken | Lot-lockouts | Capital busy | No edge (f ≤ 0) | Kill days | Warm-up | Verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    a2, a2p = s2_rows("A", [t.eval_trade("stressed") for t in a_trades], a_days)
    b2, b2p = s2_rows("B", b_runs["stressed"][0], b_cal)
    lines += a2 + b2 + [""]

    def floor(passed):
        ok = [t for t, p in passed if p]
        return f"₹{min(ok):,.0f}" if ok else "none"

    def golive(s, passed):
        return "PASS (paper first)" if s.passed and any(p for _, p in passed) else "FAIL"

    def maxdd(trades, cal):
        return max(stage2(trades, cal, t).max_dd for t in TIERS)

    lines += ["### Go-live decision matrix", "",
              "| Strategy | Asset class | Net PF | Sharpe | Max DD (worst tier) | Capital floor | Go-live |",
              "|---|---|---|---|---|---|---|",
              f"| Surge bull put credit spread | Stock options (NSE) | {fmt(s1['A stressed'].pf)} | "
              f"{fmt(s1['A stressed'].sharpe)} | {maxdd([t.eval_trade('stressed') for t in a_trades], a_days):.1%} | "
              f"{floor(a2p)} | {golive(s1['A stressed'], a2p)} |",
              f"| EUR/USD–GBP/USD cointegration | Currency futures (NSE cross) | {fmt(s1['B stressed'].pf)} | "
              f"{fmt(s1['B stressed'].sharpe)} | {maxdd(b_runs['stressed'][0], b_cal):.1%} | {floor(b2p)} | "
              f"{golive(s1['B stressed'], b2p)} |", ""]

    reasons = Counter(t.reason for t in a_trades)
    lines += ["### Track A detail", "",
              f"- {a_events} candidate-23 events; {a_ranks:,} symbol-days with an IV rank.",
              "- Skipped: " + ", ".join(f"{k} {v}" for k, v in a_skips.most_common()) + ".",
              f"- {len(a_trades)} trades. Exits: " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()) + ".",
              f"- Price fallbacks over all marks: settlement {a_fb['settle']}, intrinsic {a_fb['intrinsic']}.",
              f"- Median credit / width: {pd.Series([t.credit / t.width for t in a_trades]).median():.0%}" if a_trades else "",
              "", "### Track B detail", ""]
    for sc, (tr, counts) in b_runs.items():
        lines.append(f"- {sc}: {counts['days']:,} days, {counts['fit_ok']:,} flat days with all three tests passing, "
                     f"{counts['signals']} entries, {len(tr)} trades.")
    lines.append("")

    text = DOC.read_text(encoding="utf-8")
    text = text.split("\n---\n\n## Results")[0].rstrip("\n") + "\n"
    DOC.write_text(text + "\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
