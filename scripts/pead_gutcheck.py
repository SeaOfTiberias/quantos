#!/usr/bin/env python3
"""
QuantOS — PEAD Gut-Check (driver)
────────────────────────────────────────────────────────────────────────────
Fable's explicit recommendation before Phase 2 (see memory:
quantos-pead-earnings-feasibility): pull forward returns for the
point-in-time PAT table scripts/fetch_pead_fundamentals.py already built,
and check whether return sign/magnitude after `broadcast_date` correlates
with `yoy_surprise_pct` at all -- a quick, cheap look, not a backtest (no
costs, no position sizing, no Sharpe/profit-factor).

Reads data_cache/pead_nse/point_in_time_pat.csv (run
scripts/fetch_pead_fundamentals.py first if that doesn't exist yet),
fetches NSE equity bhavcopy for the date range it needs (see
core/fundamentals/pead/eq_bhavcopy.py), and reports per-horizon
correlation + positive/negative-surprise mean-return stats.

Usage:
    python scripts/pead_gutcheck.py
    python scripts/pead_gutcheck.py --pat-csv data_cache/pead_nse/point_in_time_pat.csv
"""

import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fundamentals.pead.eq_bhavcopy import (  # noqa: E402
    DEFAULT_PARSED_CACHE_DIR, DEFAULT_RAW_CACHE_DIR, EqBhavcopyNotAvailable, fetch_and_parse,
)
from core.fundamentals.pead.gutcheck import build_price_index, summarize  # noqa: E402
from core.fundamentals.pead.nse_client import NseSession  # noqa: E402
from core.fundamentals.pead.pipeline import PeadSignalRow  # noqa: E402

# Extra calendar-day buffer past the latest broadcast date, comfortably
# covering the longest horizon (20 trading days ~= 28-30 calendar days
# including weekends/holidays) plus slack.
FORWARD_BUFFER_DAYS = 45


def _load_pat_rows(path: Path) -> list[PeadSignalRow]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(PeadSignalRow(
                symbol=r["symbol"],
                broadcast_date=datetime.fromisoformat(r["broadcast_date"]),
                quarter_start=date.fromisoformat(r["quarter_start"]),
                quarter_end=date.fromisoformat(r["quarter_end"]),
                pat=float(r["pat"]), pat_prior_year=float(r["pat_prior_year"]),
                yoy_surprise_pct=float(r["yoy_surprise_pct"]),
            ))
    return rows


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
        if i % 30 == 0 or i == len(days):
            print(f"  [{i}/{len(days)}] fetched={fetched} cached={cached} holidays={holidays} rows={len(rows)}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pat-csv", type=Path, default=Path("data_cache/pead_nse/point_in_time_pat.csv"))
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()

    if not args.pat_csv.exists():
        print(f"ERROR: {args.pat_csv} doesn't exist -- run scripts/fetch_pead_fundamentals.py first.", file=sys.stderr)
        return 1

    pat_rows = _load_pat_rows(args.pat_csv)
    print(f"Loaded {len(pat_rows)} point-in-time PAT rows ({len(set(r.symbol for r in pat_rows))} unique symbols)")

    broadcast_dates = [r.broadcast_date.date() for r in pat_rows]
    price_start, price_end = min(broadcast_dates), max(broadcast_dates) + timedelta(days=FORWARD_BUFFER_DAYS)
    price_end = min(price_end, date.today())
    print(f"Fetching NSE equity bhavcopy {price_start} .. {price_end} for forward-return prices ...")

    nse = NseSession()
    eq_rows = fetch_equity_prices(nse, price_start, price_end, args.delay)
    print(f"  {len(eq_rows)} total equity close rows across the window")

    price_index = build_price_index(eq_rows)
    print(f"  {len(price_index)} unique symbols with price data")

    def _report(title: str, summaries) -> None:
        print(f"\n-- {title} ------------")
        for s in summaries:
            print(f"Horizon: {s.horizon_trading_days} trading days (n={s.n})")
            if s.n == 0:
                print("  no matched rows (insufficient price coverage)\n")
                continue
            corr_str = f"{s.correlation:+.4f}" if s.correlation is not None else "n/a"
            print(f"  correlation(yoy_surprise_pct, forward_return_pct): {corr_str}")
            if s.market_return_pct is not None:
                print(f"  sample cross-sectional mean return (subtracted): {s.market_return_pct:+.2f}%")
            print(f"  positive surprise (n={s.positive_surprise_n}): "
                  f"mean return {s.positive_surprise_mean_return_pct:+.2f}%, "
                  f"win rate {s.positive_surprise_win_rate:.1%}"
                  if s.positive_surprise_n else "  positive surprise: n=0")
            print(f"  negative surprise (n={s.negative_surprise_n}): "
                  f"mean return {s.negative_surprise_mean_return_pct:+.2f}%, "
                  f"win rate {s.negative_surprise_win_rate:.1%}"
                  if s.negative_surprise_n else "  negative surprise: n=0")
            print()

    print("\nNOT a backtest -- no costs, no position sizing, no threshold. See script docstring.")
    _report("RAW forward returns", summarize(pat_rows, price_index))
    _report(
        "MARKET-ADJUSTED forward returns (demeaned by this sample's own cross-sectional "
        "mean per horizon -- strips a shared market-wide move, see gutcheck.py docstring)",
        summarize(pat_rows, price_index, market_adjusted=True),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
