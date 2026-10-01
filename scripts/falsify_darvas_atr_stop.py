#!/usr/bin/env python3
"""
QuantOS — Falsification pass on the Darvas ATR-stop PASS (2026-10-01)
──────────────────────────────────────────────────────────────────────
Written BEFORE it was run (feedback rule: on any PASS, attack it before building).
Bucket B (box width 35-50%) cleared its bar on 2026-09-24
(docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md). The window, 2023-09..2026-09, was a
strong market for Indian mid/small caps, so the obvious ways it could be fake:

  K1 BETA. The trades only made what the market made. Each trade's return is
     compared with NIFTY 50 over the same entry->exit dates (NIFTY daily closes
     from the cached 5-min candles, data_cache/orb_fix2_candles.pkl).
     KILL if Bucket B's mean market-adjusted return, after Stressed costs, is <= 0.
     Caveat: NIFTY 50 under-states a mid/small-cap benchmark, so a pass on K1 is
     weak evidence; a fail is strong.
  K2 A FEW LUCKY TRADES. KILL if Bucket B's total net return is <= 0 after
     removing its top 5% of trades by return.
  K3 SAMPLING NOISE. 10,000-trade bootstrap of Bucket B's mean net return per
     trade, resampling whole entry WEEKS (trades in the same week share a market
     and are not independent). KILL if the 90% interval's lower end is <= 0.

Any KILL means the PASS is not good enough for capital; it says nothing about a
discretionary panel. All three are on the same 2280 cached trades; no refit, no
new parameters. Buckets A and C are reported alongside for comparison only.

Usage: python scripts/falsify_darvas_atr_stop.py [--out docs/DARVAS_ATR_STOP_FALSIFICATION.md]
"""
from __future__ import annotations

import argparse
import bisect
import json
import pickle
import random
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.backtest_darvas_box_width import BUCKETS, STRESSED_COST_MODEL  # noqa: E402
from scripts.backtest_darvas_trailing_stop import all_trades  # noqa: E402

RESULTS = Path.home() / ".quantos" / "darvas_atr_stop_results.json"
CANDLES = Path("data_cache/orb_fix2_candles.pkl")
POSITION_RS = 100_000.0
BOOT = 10_000
SEED = 20261001


def nifty_daily(candles) -> tuple[list[date], list[float]]:
    by_day: dict[date, float] = {}
    for c in sorted(candles, key=lambda c: c.timestamp):
        by_day[c.timestamp.date()] = c.close
    days = sorted(by_day)
    return days, [by_day[d] for d in days]


def close_on_or_before(days, closes, d: date) -> float | None:
    i = bisect.bisect_right(days, d) - 1
    return closes[i] if i >= 0 else None


def net_return(t: dict) -> float:
    qty = max(1, int(POSITION_RS // t["entry_price"]))
    cost = STRESSED_COST_MODEL.cost_of(t["entry_price"], t["exit_price"], qty, "BUY")
    return ((t["exit_price"] - t["entry_price"]) * qty - cost) / (t["entry_price"] * qty)


def d(s: str) -> date:
    return datetime.fromisoformat(s).date()


def analyse(trades: list[dict], days, closes) -> dict:
    nets, adj = [], []
    for t in trades:
        n = net_return(t)
        nets.append(n)
        a, b = close_on_or_before(days, closes, d(t["entry_date"])), close_on_or_before(days, closes, d(t["exit_date"]))
        if a and b:
            adj.append(n - (b / a - 1))
    k = max(1, round(0.05 * len(nets)))
    trimmed = sorted(nets)[:-k]
    weeks: dict[tuple, list[float]] = {}
    for t, n in zip(trades, nets):
        weeks.setdefault(d(t["entry_date"]).isocalendar()[:2], []).append(n)
    groups = list(weeks.values())
    rng, means = random.Random(SEED), []
    for _ in range(BOOT):
        pick = [x for _ in groups for x in rng.choice(groups)]
        means.append(statistics.mean(pick))
    means.sort()
    return dict(n=len(nets), mean=statistics.mean(nets), adj_n=len(adj), adj_mean=statistics.mean(adj),
                trim_k=k, trim_total=sum(trimmed), total=sum(nets), weeks=len(groups),
                lo=means[int(0.05 * BOOT)], hi=means[int(0.95 * BOOT)])


def run() -> str:
    days, closes = nifty_daily(pickle.loads(CANDLES.read_bytes())["nifty"])
    events = all_trades(json.loads(RESULTS.read_text()))
    out = ["# Darvas ATR-stop — falsification pass", "",
           "Kill conditions pre-registered in `scripts/falsify_darvas_atr_stop.py` (committed before this run). "
           f"Net = Stressed costs on a Rs{POSITION_RS:,.0f} position; returns per trade.", "",
           "| Bucket | N | Mean net | Mean net minus NIFTY (K1) | Total net | Total without top 5% (K2) | "
           "Entry weeks | 90% CI of mean, week bootstrap (K3) |", "|---|---|---|---|---|---|---|---|"]
    verdict = []
    for label, pred in BUCKETS:
        r = analyse([t for t in events if pred(t["width_pct"])], days, closes)
        out.append(f"| {label} | {r['n']} | {r['mean']:+.2%} | {r['adj_mean']:+.2%} (n={r['adj_n']}) | "
                   f"{r['total']:+.1%} | {r['trim_total']:+.1%} (−{r['trim_k']}) | {r['weeks']} | "
                   f"{r['lo']:+.2%} .. {r['hi']:+.2%} |")
        if label == "35-50%":
            verdict = [("K1 beta", r["adj_mean"] > 0), ("K2 few trades", r["trim_total"] > 0), ("K3 noise", r["lo"] > 0)]
    out += ["", "## Bucket B verdict", ""]
    out += [f"- {name}: {'survives' if ok else '**KILLED**'}" for name, ok in verdict]
    out += ["", f"**{'PASS SURVIVES all three checks' if all(ok for _, ok in verdict) else 'PASS DOES NOT SURVIVE -- not ready for capital'}**"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/DARVAS_ATR_STOP_FALSIFICATION.md")
    args = ap.parse_args(argv)
    report = run()
    Path(args.out).write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
