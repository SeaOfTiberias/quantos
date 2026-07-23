#!/usr/bin/env python3
"""
QuantOS — PEAD Phase 1: Fetch + Build Point-in-Time PAT Table (driver)
────────────────────────────────────────────────────────────────────────
Walks NSE's `corporates-financial-results` bulk metadata API month by
month, filters down to Nifty 500 point-in-time constituents with a real,
fetchable XBRL filing, extracts each filing's own-quarter PAT, and joins
same-symbol/same-quarter filings one year apart to compute a YoY earnings
surprise. See core/fundamentals/pead/ for the underlying modules and
memory: quantos-pead-earnings-feasibility for how this data source was
confirmed live before this pipeline was built.

This is DATA ONLY -- no signal thresholds, entry/exit rules, or backtest
here. That's explicitly out of scope for Phase 1 (see the module
docstrings), same split VRP used between its bhavcopy pipeline and its
later strikes/simulator phases.

**Window truncated 2026-07-23, user's explicit decision**: default
`--start` is `EARLIEST_RELIABLE_START` (2023-09-29, not the earlier
2018-03-31 XBRL-coverage date) -- see pipeline.py's module docstring for
why. Passing an earlier `--start` is allowed but warned about loudly: this
project already shipped one point-in-time universe bug (S8-3) from
silently trusting a frozen-snapshot fallback, and isn't repeating that
silently here.

Usage:
    python scripts/fetch_pead_fundamentals.py
    python scripts/fetch_pead_fundamentals.py --start 2023-09-29 --end 2026-07-23
    python scripts/fetch_pead_fundamentals.py --delay 0.5
"""

import argparse
import csv
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fundamentals.pead.nse_client import NseSession, NseSessionError  # noqa: E402
from core.fundamentals.pead.pipeline import (  # noqa: E402
    DEFAULT_METADATA_CACHE_DIR,
    DEFAULT_XBRL_CACHE_DIR,
    EARLIEST_RELIABLE_START,
    RECONSTITUTION_COVERAGE_START,
    compute_yoy_surprise,
    dedupe_consolidated_preferred,
    discover_filings,
    fetch_and_extract_pat,
    filter_usable,
    restrict_to_universe,
)
from core.rotation.nifty500_reconstitution import build_point_in_time_universe  # noqa: E402


def _load_current_universe(path: Path) -> frozenset:
    return frozenset(
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    )


def run(args) -> dict:
    nse = NseSession()

    if args.start < RECONSTITUTION_COVERAGE_START:
        print(
            f"WARNING: --start {args.start} is before {RECONSTITUTION_COVERAGE_START}, the "
            f"earliest date core/rotation/nifty500_reconstitution.py has real point-in-time "
            f"membership events for. Filings broadcast before {RECONSTITUTION_COVERAGE_START} "
            f"will be DROPPED (see restrict_to_universe's docstring), not silently "
            f"misclassified -- but this means your effective start is still "
            f"{RECONSTITUTION_COVERAGE_START}, not {args.start}.",
            file=sys.stderr,
        )

    print(f"Discovering filings {args.start} .. {args.end} (bulk, monthly chunks, all NSE companies) ...")
    all_rows = list(discover_filings(nse, args.start, args.end, args.metadata_cache_dir))
    print(f"  {len(all_rows)} raw quarterly-results filings")

    usable_rows = filter_usable(all_rows)
    print(f"  {len(usable_rows)} with a real, fetchable XBRL link")

    deduped_rows = dedupe_consolidated_preferred(usable_rows)
    print(f"  {len(deduped_rows)} after consolidated/standalone dedup")

    current_universe = _load_current_universe(args.universe)
    snapshots = build_point_in_time_universe(current_universe)
    universe_rows = restrict_to_universe(deduped_rows, snapshots)
    print(f"  {len(universe_rows)} in the Nifty 500 point-in-time universe as of their own disclosure date")

    print("Fetching + parsing XBRL for each retained filing ...")
    filings = []
    errors = 0
    for i, row in enumerate(universe_rows, 1):
        cached = (args.xbrl_cache_dir / f"{row['seqNumber']}.xml").exists()
        try:
            filing = fetch_and_extract_pat(nse, row, args.xbrl_cache_dir)
        except NseSessionError as e:
            errors += 1
            print(f"  ERROR seq={row['seqNumber']} {row['symbol']}: {e}", file=sys.stderr)
            continue
        if filing is not None:
            filings.append(filing)
        if not cached:
            time.sleep(args.delay)  # be polite to NSE -- only after a real network hit
        if i % 200 == 0 or i == len(universe_rows):
            print(f"  [{i}/{len(universe_rows)}] extracted={len(filings)} errors={errors}")

    print(f"  {len(filings)} filings with a successfully extracted quarterly PAT")

    signal_rows = compute_yoy_surprise(filings)
    print(f"  {len(signal_rows)} with a same-symbol/same-quarter prior-year match (YoY-computable)")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "symbol", "broadcast_date", "quarter_start", "quarter_end",
            "pat", "pat_prior_year", "yoy_surprise_pct",
        ])
        for row in sorted(signal_rows, key=lambda r: (r.symbol, r.quarter_start)):
            writer.writerow([
                row.symbol, row.broadcast_date.isoformat(),
                row.quarter_start.isoformat(), row.quarter_end.isoformat(),
                row.pat, row.pat_prior_year, f"{row.yoy_surprise_pct:.4f}",
            ])
    print(f"Wrote {len(signal_rows)} rows -> {args.output}")

    return {
        "raw_filings": len(all_rows),
        "usable_xbrl": len(usable_rows),
        "deduped": len(deduped_rows),
        "in_universe": len(universe_rows),
        "pat_extracted": len(filings),
        "yoy_computable": len(signal_rows),
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=date.fromisoformat, default=EARLIEST_RELIABLE_START)
    ap.add_argument("--end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--universe", type=Path, default=Path("agent/universe_nifty500.txt"))
    ap.add_argument("--metadata-cache-dir", type=Path, default=DEFAULT_METADATA_CACHE_DIR)
    ap.add_argument("--xbrl-cache-dir", type=Path, default=DEFAULT_XBRL_CACHE_DIR)
    ap.add_argument("--output", type=Path, default=Path("data_cache/pead_nse/point_in_time_pat.csv"))
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between real XBRL network fetches")
    args = ap.parse_args()

    stats = run(args)

    print("\n-- Summary --------------------------------------------")
    for k, v in stats.items():
        print(f"{k:16s}: {v}")

    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
