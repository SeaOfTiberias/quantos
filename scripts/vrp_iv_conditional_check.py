#!/usr/bin/env python3
"""
QuantOS — VRP IV-Conditional Gut-Check (read-only analysis, not a new strategy)
──────────────────────────────────────────────────────────────────────────────
Reruns the exact same VRP pipeline as scripts/backtest_vrp_strangle.py
(same cache, same selections/trades, same NET cost model) but buckets the
157 already-computed trades by entry-day IV (average of the call/put legs'
implied vol from core/options/vrp/strikes.py's StrikeSelection, already
computed during strike selection -- not re-derived) into terciles, and
reports NET profit factor/Sharpe per bucket.

Purpose: before reviving any AI/data-driven options-strategy suggestion
mechanism, check whether there's real support (from actual executed-
strategy P&L, not an abstract forward-return proxy) for conditioning
strategy choice on volatility level. Both prior attempts at a volatility-
regime signal in this project failed (S8-1 VIX-level classifier,
IV-minus-RV-spread regime v2) -- this checks a third, more direct
candidate using data already collected. Does not modify any VRP core
module; read-only, additive.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.vrp.bhavcopy import DEFAULT_PARSED_CACHE_DIR, load_cached_range  # noqa: E402
from core.options.vrp.costs import compute_net_stats  # noqa: E402
from core.options.vrp.simulator import simulate  # noqa: E402
from core.options.vrp.strikes import build_entry_cycles, select_strangle  # noqa: E402
from collections import defaultdict


def main() -> int:
    start, end = date(2023, 7, 24), date(2026, 7, 22)
    print(f"Loading cached NIFTY options {start} .. {end} ...")
    rows_by_date = defaultdict(list)
    for r in load_cached_range(start, end, DEFAULT_PARSED_CACHE_DIR):
        rows_by_date[r.trade_date].append(r)

    expiries_by_date = {d: {r.expiry for r in rs} for d, rs in rows_by_date.items()}
    cycles = build_entry_cycles(expiries_by_date)

    selections = []
    for c in cycles:
        sel = select_strangle(rows_by_date.get(c.entry_date, []), c.entry_date, c.expiry_date, c.dte)
        if sel is not None:
            selections.append(sel)
    print(f"{len(selections)} strangles selected")

    trades = simulate(selections, DEFAULT_PARSED_CACHE_DIR)
    assert len(trades) == len(selections), "simulate() must preserve 1:1 order with selections"

    # Pair each trade with its entry-day average IV (already computed during
    # strike selection -- core/options/vrp/strikes.py's StrikeSelection.iv).
    paired = [(sel.call.iv + sel.put.iv) / 2.0 for sel in selections]
    ivs = sorted(iv for iv in paired)
    n = len(ivs)
    t1, t2 = ivs[n // 3], ivs[2 * n // 3]
    print(f"IV terciles: low < {t1:.1%} <= mid < {t2:.1%} <= high  (n={n})")

    buckets = {"LOW": [], "MID": [], "HIGH": []}
    for iv, trade in zip(paired, trades):
        label = "LOW" if iv < t1 else ("HIGH" if iv >= t2 else "MID")
        buckets[label].append(trade)

    print(f"\n{'Bucket':<6} {'N':>4} {'WinRate':>8} {'AvgPnL%':>9} {'PF':>7} {'Sharpe':>8}")
    for label in ("LOW", "MID", "HIGH"):
        bucket_trades = buckets[label]
        if not bucket_trades:
            print(f"{label:<6} {'(empty)'}")
            continue
        stats = compute_net_stats(bucket_trades)
        print(f"{label:<6} {stats.n_trades:>4} {stats.win_rate:>7.1%} "
              f"{stats.avg_pnl_pct:>+8.2f}% {stats.profit_factor:>7.3f} {stats.sharpe:>8.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
