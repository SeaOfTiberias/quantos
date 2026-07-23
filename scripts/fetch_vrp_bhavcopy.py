#!/usr/bin/env python3
"""
QuantOS — VRP Phase 1: Fetch + Cache NSE Bhavcopy (driver)
──────────────────────────────────────────────────────────────
Walks every weekday in a date range, fetching + parsing NSE's daily F&O
bhavcopy via core/options/vrp/bhavcopy.py and caching both the raw zip and
the NIFTY-option-only parsed CSV to disk (see that module's docstring for
the two-cache design and the format-cutover logic).

No NSE holiday calendar: a non-trading weekday 404s and is counted as a
holiday, not an error. Resumable: already-cached dates (raw or parsed) are
served from disk, so re-running this after a partial run or a failure picks
up where it left off without re-fetching anything.

Default window: 3 years ending today. Chosen to span both bhavcopy schema
generations (exercising the CUTOVER_DATE logic for real, not just in the
unit tests) and at least two known high-volatility NIFTY episodes within it
(the 2024-06-04 election-result crash, the 2025-04/05 geopolitical-tension
spike) -- VRP's whole thesis is about the gap between implied and realized
vol, so a window of only calm markets would be a biased sample before a
single trade is even simulated.

Usage:
    python scripts/fetch_vrp_bhavcopy.py
    python scripts/fetch_vrp_bhavcopy.py --start 2023-07-24 --end 2026-07-23
    python scripts/fetch_vrp_bhavcopy.py --delay 0.5 --sanity-check 2024-06-04
"""

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from core.options.vrp.bhavcopy import (  # noqa: E402
    BhavcopyNotAvailable, DEFAULT_PARSED_CACHE_DIR, DEFAULT_RAW_CACHE_DIR,
    fetch_and_parse, load_cached_range,
)


def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            yield d
        d += timedelta(days=1)


def run(start: date, end: date, raw_dir: Path, parsed_dir: Path, delay: float) -> dict:
    session = requests.Session()
    stats = {"from_cache": 0, "fetched": 0, "holidays": 0, "errors": 0, "rows": 0}
    days = list(_weekdays(start, end))

    for i, d in enumerate(days, 1):
        raw_cached = (raw_dir / f"{d:%Y%m%d}.zip").exists()
        parsed_cached = (parsed_dir / f"{d:%Y%m%d}.csv").exists()
        try:
            rows = fetch_and_parse(d, raw_dir, parsed_dir, session=session)
            stats["rows"] += len(rows)
            if parsed_cached:
                stats["from_cache"] += 1
            else:
                stats["fetched"] += 1
                if not raw_cached:
                    time.sleep(delay)  # be polite to NSE -- only after a real network hit
        except BhavcopyNotAvailable:
            stats["holidays"] += 1
        except Exception as e:  # noqa: BLE001 -- one bad day must not kill a 750-day run
            stats["errors"] += 1
            print(f"  ERROR {d}: {e}", file=sys.stderr)

        if i % 50 == 0 or i == len(days):
            print(f"  [{i}/{len(days)}] {d} -- fetched={stats['fetched']} "
                  f"cached={stats['from_cache']} holidays={stats['holidays']} "
                  f"errors={stats['errors']} rows={stats['rows']}")

    return stats


def sanity_check(target: date, parsed_dir: Path) -> None:
    """Eyeball check: does the ATM straddle price on `target` look like a
    real elevated-IV read relative to a calm day earlier in the same window?
    Only meaningful for new-format (2024+) dates, which carry underlying_close;
    the legacy schema has no spot price to find an ATM strike against."""
    rows = list(load_cached_range(target, target, parsed_dir))
    if not rows:
        print(f"sanity check: no cached data for {target} (fetch it first)")
        return
    spot = next((r.underlying_close for r in rows if r.underlying_close), None)
    if spot is None:
        print(f"sanity check: {target} has no underlying_close (legacy-schema date, skipping)")
        return

    # Nearest weekly/monthly expiry present that day.
    nearest_expiry = min({r.expiry for r in rows}, key=lambda e: abs((e - target).days))
    same_expiry = [r for r in rows if r.expiry == nearest_expiry]
    atm_strike = min({r.strike for r in same_expiry}, key=lambda k: abs(k - spot))
    ce = next((r for r in same_expiry if r.strike == atm_strike and r.option_type.value == "CE"), None)
    pe = next((r for r in same_expiry if r.strike == atm_strike and r.option_type.value == "PE"), None)
    if not ce or not pe:
        print(f"sanity check: {target} missing one leg of the ATM straddle at strike {atm_strike}")
        return

    straddle = ce.close + pe.close
    implied_move_pct = straddle / spot * 100
    dte = (nearest_expiry - target).days
    print(
        f"sanity check {target}: spot={spot:.1f} nearest_expiry={nearest_expiry} "
        f"(DTE={dte}) ATM_strike={atm_strike:.0f} straddle={straddle:.1f} "
        f"({implied_move_pct:.2f}% of spot)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    today = date.today()
    ap.add_argument("--start", type=date.fromisoformat, default=today.replace(year=today.year - 3))
    ap.add_argument("--end", type=date.fromisoformat, default=today)
    ap.add_argument("--raw-cache-dir", type=Path, default=DEFAULT_RAW_CACHE_DIR)
    ap.add_argument("--parsed-cache-dir", type=Path, default=DEFAULT_PARSED_CACHE_DIR)
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between real network fetches")
    ap.add_argument("--sanity-check", type=date.fromisoformat, action="append", default=[],
                     help="after fetching, print an ATM-straddle eyeball check for this date "
                          "(repeatable)")
    args = ap.parse_args()

    print(f"Fetching NSE bhavcopy {args.start} .. {args.end} "
          f"(raw -> {args.raw_cache_dir}, parsed -> {args.parsed_cache_dir})")
    stats = run(args.start, args.end, args.raw_cache_dir, args.parsed_cache_dir, args.delay)

    print("\n-- Summary --------------------------------------------")
    print(f"Trading days with data : {stats['fetched'] + stats['from_cache']}")
    print(f"  newly fetched        : {stats['fetched']}")
    print(f"  served from cache    : {stats['from_cache']}")
    print(f"Holidays/weekends skip : {stats['holidays']}")
    print(f"Errors                 : {stats['errors']}")
    print(f"Total NIFTY option rows: {stats['rows']}")

    for target in args.sanity_check:
        sanity_check(target, args.parsed_cache_dir)

    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
