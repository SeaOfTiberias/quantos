#!/usr/bin/env python3
"""
QuantOS — Do candidate 18b's filters carry an edge in INDEX POINTS? (2026-09-30)
─────────────────────────────────────────────────────────────────────────────────
Written BEFORE it was run (Fable's research-plan step 1). 18b = candidate 18's
ORB signal gated to NIFTY on Monday/Friday and BANKNIFTY on days opening > 0.3%
away from the prior close (core/orb_scalping/entry_filter.py). Both conditions
were mined (2026-09-03 / 09-21) on OPTION P&L priced by the old model, which had
zero intraday decay and charged the calendar weekend -- so a weekday effect in
particular may be a pricing artifact. This asks the question with no option
pricing at all: on filtered days, do the V0 trades (current exit rules,
core/orb_scalping/exit_policies.py) earn more INDEX POINTS than on the other days?

Data: the cached Fyers 5-min candles (data_cache/orb_fix2_candles.pkl). BANKNIFTY
expiry days are skipped, as live. The prior close is the prior day's last 5-min
close, a proxy for the daily close the live filter uses.

PRE-REGISTERED rule (Fable, 2026-09-30):
  For each index, difference = mean points/trade (filtered days) - (other days),
  Welch one-sided test. If the difference is NOT positive at p < 0.10, that filter
  is classed as a pricing artifact.
  This test can only KILL a filter, never promote one: the conditions were mined
  on this same history, so a pass here is in-sample. The 18b prospective paper gate
  (2026-11-17) is unaffected either way.
Also reported, descriptively: the filtered subset on its own (mean points, t) and
net of the futures cost model used in docs/ORB_EXIT_POLICY_RESULTS.md.

Offline. Usage:
    python scripts/test_orb_18b_filters_index_points.py [--out docs/ORB_18B_FILTER_INDEX_POINTS.md]
"""
from __future__ import annotations

import argparse
import math
import pickle
import statistics
import sys
from pathlib import Path

from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orb_scalping.backtest import (  # noqa: E402
    BANKNIFTY_LOT_SIZE, NIFTY_LOT_SIZE, group_by_day, is_banknifty_monthly_expiry_day,
)
from core.orb_scalping.entry_filter import banknifty_entry_allowed, nifty_entry_allowed  # noqa: E402
from core.orb_scalping.exit_policies import ExitPolicy, simulate_day_with_policy  # noqa: E402
from scripts.backtest_orb_exits import futures_cost  # noqa: E402

CANDLES = Path("data_cache/orb_fix2_candles.pkl")
ALPHA = 0.10


def trades(candles, underlying: str) -> list[dict]:
    by_day = group_by_day(candles)
    days = sorted(by_day)
    lot = NIFTY_LOT_SIZE if underlying == "NIFTY" else BANKNIFTY_LOT_SIZE
    out, prev_close = [], None
    for day in days:
        dc = by_day[day]
        skip = underlying == "BANKNIFTY" and is_banknifty_monthly_expiry_day(day, set(days))
        t = None if skip else simulate_day_with_policy(dc, ExitPolicy())
        if t is not None:
            sign = 1 if t.direction == "CALL" else -1
            pts = (t.exit_price - t.entry_price) * sign
            filt = (nifty_entry_allowed(day) if underlying == "NIFTY"
                    else banknifty_entry_allowed(dc[0].open, prev_close))
            out.append(dict(day=day, pts=pts, filtered=filt,
                            net=pts * lot - futures_cost(t.entry_price, t.exit_price, lot)))
        prev_close = dc[-1].close
    return out


def welch_one_sided(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """(difference of means a-b, t, one-sided p for a > b)."""
    va, vb = statistics.variance(a), statistics.variance(b)
    se = math.sqrt(va / len(a) + vb / len(b))
    diff = statistics.mean(a) - statistics.mean(b)
    df = (va / len(a) + vb / len(b)) ** 2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
    t = diff / se
    return diff, t, float(stats.t.sf(t, df))


def t_of(xs: list[float]) -> float:
    return statistics.mean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs)))


def run(data: dict) -> str:
    out = ["# Candidate 18b filters — edge in index points?", "",
           "Method and pre-registered rule: `scripts/test_orb_18b_filters_index_points.py` docstring, committed "
           "before this run. V0 exit rules; points are measured in the trade's direction; no option pricing.", "",
           "| Index | Filter | Filtered N | Filtered pts/trade | Other N | Other pts/trade | Difference | p (one-sided) | Verdict |",
           "|---|---|---|---|---|---|---|---|---|"]
    detail = ["", "Filtered subset alone (descriptive):", "",
              "| Index | pts/trade | t | Net Rs/trade after futures costs | t (net) |", "|---|---|---|---|---|"]
    for und, key, name in (("NIFTY", "nifty", "Monday/Friday"), ("BANKNIFTY", "banknifty", "gap > 0.3%")):
        ts = trades(data[key], und)
        f = [t["pts"] for t in ts if t["filtered"]]
        r = [t["pts"] for t in ts if not t["filtered"]]
        diff, _, p = welch_one_sided(f, r)
        verdict = "survives (in-sample only)" if diff > 0 and p < ALPHA else "PRICING ARTIFACT"
        out.append(f"| {und} | {name} | {len(f)} | {statistics.mean(f):+.2f} | {len(r)} | {statistics.mean(r):+.2f} | "
                   f"{diff:+.2f} | {p:.3f} | {verdict} |")
        fn = [t["net"] for t in ts if t["filtered"]]
        detail.append(f"| {und} | {statistics.mean(f):+.2f} | {t_of(f):.2f} | {statistics.mean(fn):+,.0f} | {t_of(fn):.2f} |")
    return "\n".join(out + detail) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="docs/ORB_18B_FILTER_INDEX_POINTS.md")
    args = ap.parse_args(argv)
    report = run(pickle.loads(CANDLES.read_bytes()))
    Path(args.out).write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
