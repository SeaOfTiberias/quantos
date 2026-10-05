#!/usr/bin/env python3
"""
QuantOS — Darvas ATR-stop, OUT-OF-SAMPLE on 2016-2023 (2026-10-05)
───────────────────────────────────────────────────────────────────
Written BEFORE it was run. The ATR-stop rule (scripts/backtest_darvas_atr_stop.py,
Bucket B = box width 35-50%) was found and passed on 2023-09..2026-09. The
falsification pass (docs/DARVAS_ATR_STOP_FALSIFICATION.md) showed it is not just
beta, but its 277 trades cannot separate it from luck (week-bootstrap 90% CI
-0.76%..+2.10%). This runs the SAME FROZEN RULES on years the rule never saw.

Data: NSE's own daily equity bhavcopies (core/fundamentals/pead/eq_bhavcopy.py raw
cache), EQ series, 2016-01-01..2023-12-31. They list every traded stock on each
day, including names that were later delisted or merged -- no survivorship from
the data source.
  - Split/bonus adjustment: NSE's PREVCLOSE is adjusted on an ex-date; where
    PREVCLOSE differs from the prior day's CLOSE by more than 1%, all earlier bars
    of that symbol are scaled by PREVCLOSE / prior CLOSE (volume inversely).
  - Universe (a Nifty 500 proxy; NSE's 2016-2023 constituent history is not on
    hand): on each 1 Jan and 1 Jul, the 500 symbols with the highest median daily
    traded value over the prior 126 sessions. Breakouts count only for symbols in
    the universe on the breakout date (same eligibility rule as the original).
  - Lookback: analyse_symbol sees at most the trailing 756 sessions (3 years), as
    the original run's 3-year fetch window did. Rules otherwise untouched: the
    original find_atr_trades is called as is.
Window: breakouts 2016-07-01..2023-09-21 (the original window starts 2023-09-22);
exits may run into the data to 2023-12-29; still-open trades are marked to market,
as in the original.

PRE-REGISTERED verdict on Bucket B (35-50%), Stressed costs. ALL must hold:
  V1 has_positive_edge (PF > 1 and Sharpe > 0.5) -- the original bar.
  V2 mean net return per trade minus the EQUAL-WEIGHT universe return over the
     same entry->exit dates > 0 (a mid/small-cap-fair benchmark, unlike NIFTY 50).
  V3 week-clustered bootstrap (10,000) 90% CI of mean net return per trade has
     its lower end > 0 -- the check the in-sample PASS failed.
PASS -> the rule is a candidate for small real capital (the user decides size).
FAIL -> Darvas ATR-stop is closed as a capital strategy.
Buckets A and C and per-year results are descriptive only.

Usage: python scripts/backtest_darvas_atr_stop_oos.py [--workers 4]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import random
import statistics
import sys
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.brokers.base import OHLCV  # noqa: E402
from core.fundamentals.pead.eq_bhavcopy import DEFAULT_RAW_CACHE_DIR  # noqa: E402
from core.rotation.nifty500_reconstitution import UniverseSnapshot  # noqa: E402

DATA_FROM, DATA_TO = date(2016, 1, 1), date(2023, 12, 31)
BREAKOUT_FROM, BREAKOUT_TO = date(2016, 7, 1), date(2023, 9, 21)
LOOKBACK = 756
UNIVERSE_SIZE, UNIVERSE_WINDOW = 500, 126
ADJ_THRESHOLD = 0.01
BOOT, SEED = 10_000, 20261005
POSITION_RS = 100_000.0
CACHE = Path.home() / ".quantos" / "darvas_atr_stop_oos_results.json"
OUT = Path("docs/DARVAS_ATR_STOP_OOS_RESULTS.md")
UTC = timezone.utc


# ─── Data ─────────────────────────────────────────────────────────────────────

def load_bhavcopies() -> dict[str, list[dict]]:
    """symbol -> rows sorted by date: date, o, h, l, c, prev, vol, val."""
    by_sym: dict[str, list[dict]] = defaultdict(list)
    d = DATA_FROM
    while d <= DATA_TO:
        p = DEFAULT_RAW_CACHE_DIR / f"{d:%Y%m%d}.zip"
        if d.weekday() < 5 and p.exists():
            with zipfile.ZipFile(p) as zf:
                text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
            for r in csv.DictReader(io.StringIO(text)):
                if r.get("SERIES", "").strip() != "EQ":
                    continue
                try:
                    row = dict(date=d, o=float(r["OPEN"]), h=float(r["HIGH"]), l=float(r["LOW"]),
                               c=float(r["CLOSE"]), prev=float(r["PREVCLOSE"]),
                               vol=float(r["TOTTRDQTY"]), val=float(r["TOTTRDVAL"]))
                except (KeyError, ValueError):
                    continue
                if row["c"] > 0 and row["o"] > 0:
                    by_sym[r["SYMBOL"].strip()].append(row)
        d += timedelta(days=1)
    return by_sym


def adjust(rows: list[dict]) -> list[dict]:
    """Back-adjust for splits/bonuses using NSE's ex-date PREVCLOSE."""
    rows = [dict(r) for r in rows]
    for i in range(1, len(rows)):
        prior_close = rows[i - 1]["c"]
        f = rows[i]["prev"] / prior_close if prior_close else 1.0
        if abs(f - 1) > ADJ_THRESHOLD:
            for r in rows[:i]:
                for k in ("o", "h", "l", "c", "prev"):
                    r[k] *= f
                r["vol"] /= f
    return rows


def to_ohlcv(rows: list[dict]) -> list[OHLCV]:
    return [OHLCV(timestamp=datetime(r["date"].year, r["date"].month, r["date"].day, tzinfo=UTC),
                  open=r["o"], high=r["h"], low=r["l"], close=r["c"], volume=r["vol"]) for r in rows]


def build_universe(by_sym: dict[str, list[dict]]) -> list[UniverseSnapshot]:
    vals: dict[date, dict[str, float]] = defaultdict(dict)
    for s, rows in by_sym.items():
        for r in rows:
            vals[r["date"]][s] = r["val"]
    days = sorted(vals)
    snaps = []
    rebal = [date(y, m, 1) for y in range(2016, 2024) for m in (1, 7)]
    for k, rd in enumerate(rebal):
        i = bisect.bisect_left(days, rd)
        window = days[max(0, i - UNIVERSE_WINDOW):i] or days[:UNIVERSE_WINDOW]
        per: dict[str, list[float]] = defaultdict(list)
        for d in window:
            for s, v in vals[d].items():
                per[s].append(v)
        ranked = sorted(per, key=lambda s: statistics.median(per[s]), reverse=True)[:UNIVERSE_SIZE]
        until = datetime(rebal[k + 1].year, rebal[k + 1].month, 1, tzinfo=UTC) if k + 1 < len(rebal) else None
        snaps.append(UniverseSnapshot(valid_from=datetime(rd.year, rd.month, 1, tzinfo=UTC),
                                      valid_until=until, symbols=frozenset(ranked)))
    return snaps


# ─── Trades (the original, frozen rules) ──────────────────────────────────────

def _worker(args):
    symbol, daily, snapshots = args
    import scripts.backtest_darvas_atr_stop as atr
    from core.darvas.weekly_discovery import analyse_symbol as _orig
    atr.analyse_symbol = lambda s, d, cfg=None: _orig(s, d[-LOOKBACK:], cfg)
    try:
        trades = atr.find_atr_trades(symbol, daily, snapshots)
    except Exception as e:  # one bad series must not kill the run
        return symbol, {"error": repr(e)}
    lo, hi = BREAKOUT_FROM.isoformat(), (BREAKOUT_TO + timedelta(days=1)).isoformat()
    return symbol, {"trades": [t for t in trades if lo <= t["breakout_date"][:10] < hi]}


# ─── Verdict ──────────────────────────────────────────────────────────────────

def ew_index(by_sym_adj: dict[str, list[dict]], snapshots) -> tuple[list[date], list[float]]:
    """Equal-weight daily index of the point-in-time universe (adjusted closes)."""
    rets: dict[date, list[float]] = defaultdict(list)
    from core.rotation.nifty500_reconstitution import eligible_symbols_asof
    for s, rows in by_sym_adj.items():
        for a, b in zip(rows, rows[1:]):
            if (b["date"] - a["date"]).days > 10:
                continue
            dt = datetime(b["date"].year, b["date"].month, b["date"].day, tzinfo=UTC)
            if s in eligible_symbols_asof(snapshots, dt):
                rets[b["date"]].append(b["c"] / a["c"] - 1)
    days = sorted(rets)
    level, out = 1.0, []
    for d in days:
        level *= 1 + statistics.mean(rets[d])
        out.append(level)
    return days, out


def net_return(t: dict, cost_model) -> float:
    qty = max(1, int(POSITION_RS // t["entry_price"]))
    cost = cost_model.cost_of(t["entry_price"], t["exit_price"], qty, "BUY")
    return ((t["exit_price"] - t["entry_price"]) * qty - cost) / (t["entry_price"] * qty)


def summarize(results: dict, ew_days, ew_lvl) -> str:
    from scripts.backtest_darvas_box_width import BUCKETS, STRESSED_COST_MODEL, _metrics, _passes, _row
    from scripts.backtest_darvas_trailing_stop import all_trades

    def lvl(d: date):
        i = bisect.bisect_right(ew_days, d) - 1
        return ew_lvl[i] if i >= 0 else None

    events = all_trades(results)
    errors = [s for s, r in results.items() if "error" in r]
    out = ["# Darvas ATR-stop — out-of-sample 2016-2023", "",
           "Pre-registered in `scripts/backtest_darvas_atr_stop_oos.py` (committed before this run). Frozen rules; "
           "NSE bhavcopy data incl. later-delisted names; liquidity-ranked top-500 universe; Stressed costs.", "",
           f"{len(results)} symbols, {len(errors)} errored, {len(events)} breakout trades "
           f"({sum(t['reason'] == 'still-open' for t in events)} still open at data end, marked to market).", "",
           "| Bucket | Trades | Win rate | PF | Sharpe | Net P&L% | Avg hold | Mean net | Minus EW universe | 90% CI (week bootstrap) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    verdict = None
    for label, pred in BUCKETS:
        tr = [t for t in events if pred(t["width_pct"])]
        m = _metrics(tr, STRESSED_COST_MODEL)
        if m is None or not tr:
            out.append(f"| {label} | {len(tr)} | too few | | | | | | | |")
            continue
        nets = [net_return(t, STRESSED_COST_MODEL) for t in tr]
        adj = []
        for t, n in zip(tr, nets):
            a, b = lvl(date.fromisoformat(t["entry_date"][:10])), lvl(date.fromisoformat(t["exit_date"][:10]))
            if a and b:
                adj.append(n - (b / a - 1))
        weeks = defaultdict(list)
        for t, n in zip(tr, nets):
            weeks[date.fromisoformat(t["entry_date"][:10]).isocalendar()[:2]].append(n)
        groups, rng, means = list(weeks.values()), random.Random(SEED), []
        for _ in range(BOOT):
            pick = [x for _ in groups for x in rng.choice(groups)]
            means.append(statistics.mean(pick))
        means.sort()
        lo, hi = means[int(0.05 * BOOT)], means[int(0.95 * BOOT)]
        row = _row(label, len(tr), m).rstrip(" |")
        out.append(f"{row} | {statistics.mean(nets):+.2%} | {statistics.mean(adj):+.2%} | {lo:+.2%} .. {hi:+.2%} |")
        if label == "35-50%":
            verdict = [("V1 PF > 1 and Sharpe > 0.5", _passes(m)),
                       ("V2 beats the equal-weight universe", statistics.mean(adj) > 0),
                       ("V3 bootstrap lower bound > 0", lo > 0)]
            years = defaultdict(list)
            for t, n in zip(tr, nets):
                years[t["entry_date"][:4]].append(n)
            by_year = ", ".join(f"{y}: {statistics.mean(v):+.2%} (n={len(v)})" for y, v in sorted(years.items()))
    out += ["", "## Bucket B verdict", ""]
    if verdict is None:
        out.append("**Too few Bucket B trades for a verdict.**")
    else:
        out += [f"- {n}: {'holds' if ok else '**FAILS**'}" for n, ok in verdict]
        out += ["", f"Per year (mean net): {by_year}", "",
                f"**{'PASS -- candidate for small real capital' if all(ok for _, ok in verdict) else 'FAIL -- closed as a capital strategy'}**"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="first N universe symbols only (smoke test)")
    args = ap.parse_args(argv)
    raw = load_bhavcopies()
    print(f"loaded {len(raw)} symbols", flush=True)
    snapshots = build_universe(raw)
    members = sorted(frozenset().union(*(s.symbols for s in snapshots)))
    print(f"{len(members)} symbols ever in the universe", flush=True)
    adj = {s: adjust(raw[s]) for s in members}
    results = json.loads(CACHE.read_text()) if CACHE.exists() and not args.limit else {}
    todo = [s for s in members if s not in results][: args.limit]
    jobs = [(s, to_ohlcv(adj[s]), snapshots) for s in todo if len(adj[s]) >= 60]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for n, (sym, res) in enumerate(ex.map(_worker, jobs, chunksize=1), 1):
            results[sym] = res
            if not args.limit:
                CACHE.write_text(json.dumps(results))
            print(f"[{n}/{len(jobs)}] {sym}: {len(res.get('trades', []))} trades", flush=True)
    if args.limit:          # smoke test: plumbing only, no performance numbers
        return 0
    ew_days, ew_lvl = ew_index(adj, snapshots)
    report = summarize(results, ew_days, ew_lvl)
    OUT.write_text(report, encoding="utf-8")
    sys.stdout.buffer.write(report.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
