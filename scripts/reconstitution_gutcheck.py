#!/usr/bin/env python3
"""
QuantOS — Nifty 500 Index-Reconstitution Gut-Check (driver)
────────────────────────────────────────────────────────────────────────────
Fable's explicit recommendation before considering any backtest (see
memory: quantos-index-reconstitution-effect-feasibility): a cheap
diagnostic on whether Nifty 500 addition/removal correlates with a return
effect around the announcement and effective dates -- NOT a backtest (no
costs, no position sizing, no threshold).

Reuses core.rotation.nifty500_reconstitution.EVENTS (already in-code, no
fetch needed) for membership changes, and
core.fundamentals.pead.eq_bhavcopy for daily close prices (confirmed live
through 2026-07-23 during the feasibility check -- same fetch/cache
module, zero new pipeline).

Usage:
    python scripts/reconstitution_gutcheck.py
"""

import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fundamentals.pead.eq_bhavcopy import (  # noqa: E402
    DEFAULT_PARSED_CACHE_DIR, DEFAULT_RAW_CACHE_DIR, EqBhavcopyNotAvailable, fetch_and_parse,
)
from core.fundamentals.pead.nse_client import NseSession  # noqa: E402
from core.rotation.reconstitution_gutcheck import (  # noqa: E402
    DEFAULT_POST_EFFECTIVE_HORIZONS, build_legs, build_price_index, diagnose_all, missing_legs,
    summarize_anticipation, summarize_post_effective,
)

# Calendar-day buffer past the latest effective date, comfortably covering
# the longest post-effective horizon (20 trading days ~= 28-30 calendar
# days including weekends/holidays) plus slack -- same margin PEAD's
# gut-check used for its own forward-return window.
FORWARD_BUFFER_DAYS = 45


def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def fetch_equity_prices(nse: NseSession, start: date, end: date, delay: float) -> list:
    rows = []
    days = list(_weekdays(start, end))
    fetched, cached, holidays = 0, 0, 0
    for i, d in enumerate(days, 1):
        was_cached = (DEFAULT_PARSED_CACHE_DIR / f"{d:%Y%m%d}.csv").exists()
        try:
            day_rows = fetch_and_parse(nse, d, DEFAULT_RAW_CACHE_DIR, DEFAULT_PARSED_CACHE_DIR)
            rows.extend(day_rows)
            if was_cached:
                cached += 1
            else:
                fetched += 1
                if not (DEFAULT_RAW_CACHE_DIR / f"{d:%Y%m%d}.zip").exists():
                    time.sleep(delay)
        except EqBhavcopyNotAvailable:
            holidays += 1
        if i % 60 == 0 or i == len(days):
            print(f"  [{i}/{len(days)}] fetched={fetched} cached={cached} holidays={holidays} rows={len(rows)}")
    return rows


def _report(title: str, summaries) -> None:
    print(f"\n-- {title} ------------")
    for s in summaries:
        label = f"{s.event_type:>6} / {s.event_category:<5}"
        if s.n_legs == 0:
            print(f"  {label}  n=0 (no matched rows)")
            continue
        ret = f"{s.mean_return_pct:+.2f}%"
        win = f"{s.win_rate:.1%}"
        print(f"  {label}  n_legs={s.n_legs:<3} n_events={s.n_events:<2}  mean_return={ret:<9} win_rate={win}")


def main() -> int:
    legs = build_legs()
    n_broad_events = len({leg.effective_date for leg in legs if leg.event_category == "broad"})
    n_adhoc_events = len({leg.effective_date for leg in legs if leg.event_category == "adhoc"})
    print(f"Built {len(legs)} legs from {n_broad_events} broad-review dates + {n_adhoc_events} ad-hoc dates.")
    print(
        f"CAVEAT (see memory: quantos-index-reconstitution-effect-feasibility): the real "
        f"independent sample for the broad-review statistic is n={n_broad_events} dates, not "
        f"the {sum(1 for leg in legs if leg.event_category == 'broad')} broad-review legs it "
        f"contains. Ad-hoc results (n={n_adhoc_events} dates, 1 leg each) are spot-checks only "
        f"-- never pooled into the broad-review numbers below."
    )

    announcement_dates = [leg.announcement_date for leg in legs]
    effective_dates = [leg.effective_date for leg in legs]
    price_start = min(announcement_dates)
    price_end = min(max(effective_dates) + timedelta(days=FORWARD_BUFFER_DAYS), date.today())
    print(f"\nFetching NSE equity bhavcopy {price_start} .. {price_end} ...")

    nse = NseSession()
    eq_rows = fetch_equity_prices(nse, price_start, price_end, delay=0.3)
    print(f"  {len(eq_rows)} total equity close rows across the window")

    price_index = build_price_index(eq_rows)
    print(f"  {len(price_index)} unique symbols with price data")

    gaps = missing_legs(legs, price_index)
    if gaps:
        print(f"\n{len(gaps)} leg(s) with NO price data at all for their symbol (skipped, not zero-filled):")
        for leg in gaps:
            print(f"  {leg.symbol:<12} {leg.event_type:<6} effective={leg.effective_date} source={leg.source}")
    else:
        print("\nNo symbols entirely missing price data.")

    def _report_diagnostics(window: str, horizon=None) -> None:
        label = window if horizon is None else f"{window} ({horizon}d)"
        by_reason = diagnose_all(legs, price_index, window, horizon)
        excluded = sum(len(v) for v in by_reason.values())
        if not excluded:
            return
        print(f"\n{excluded} leg(s) excluded from {label} (partial-coverage/data-quality issues, not just total absence):")
        for reason, flagged in sorted(by_reason.items()):
            symbols = ", ".join(f"{leg.symbol}({leg.event_type})" for leg in flagged)
            print(f"  {reason} (n={len(flagged)}): {symbols}")

    print("\n-- Diagnostics: legs excluded per window/horizon beyond total-absence gaps above ------------")
    _report_diagnostics("anticipation")
    for h in DEFAULT_POST_EFFECTIVE_HORIZONS:
        _report_diagnostics("post_effective", h)

    print("\nNOT a backtest -- no costs, no position sizing, no threshold. See module docstring.")

    _report("ANTICIPATION window (announcement -> day before effective), RAW", summarize_anticipation(legs, price_index))
    _report(
        "ANTICIPATION window, MARKET-ADJUSTED (demeaned per-event, see module docstring)",
        summarize_anticipation(legs, price_index, market_adjusted=True),
    )
    _report(
        f"POST-EFFECTIVE window (effective -> +N trading days), RAW  [horizons={DEFAULT_POST_EFFECTIVE_HORIZONS}]",
        summarize_post_effective(legs, price_index),
    )
    _report(
        "POST-EFFECTIVE window, MARKET-ADJUSTED (demeaned per-event)",
        summarize_post_effective(legs, price_index, market_adjusted=True),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
