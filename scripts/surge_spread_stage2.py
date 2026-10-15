#!/usr/bin/env python3
"""
QuantOS — Candidate 23 Stage 2: bull call spreads on non-52-week-high surges
─────────────────────────────────────────────────────────────────────────────
docs/SURGE_SPREAD_STAGE2_METHODOLOGY.md, pre-registered before this ran.

Data: cached F&O bhavcopy (futures panel + stock-option CE rows) and cached
NSE results dates. No Fyers token needed. The first run parses the option
rows (~15 min) into data_cache/surge/option_rows.csv.gz.

Usage:
    python scripts/surge_spread_stage2.py                 # full run + report
    python scripts/surge_spread_stage2.py --prepare-only  # just build the option cache
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core.statarb.data import (  # noqa: E402
    DEFAULT_CACHE_DIR, SYMBOL_RENAMES, fetch_results_board_meetings, load_futures_panel,
)
from core.statarb.residuals import build_panel  # noqa: E402
from core.surge.events import find_events, results_rows  # noqa: E402
from core.surge.options import load_option_rows, needs_for_events  # noqa: E402

CUTOFF = date(2025, 1, 7)


def load_events():
    raw_syms = pd.read_csv(DEFAULT_CACHE_DIR / "futures_panel_all.csv", usecols=["symbol"]).symbol.unique()
    symbols = sorted({SYMBOL_RENAMES.get(s, s) for s in raw_syms})
    panel = build_panel(load_futures_panel(symbols, date.today(), allow_network=False))
    meetings = fetch_results_board_meetings(panel.symbols, 2019, panel.dates[-1].year, refresh_current=False)
    events, _ = find_events(panel, results_rows(panel, meetings))
    branch = [e for e in events if not e.cond["breakout52"]]
    return panel, branch


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--out", default="docs/SURGE_SPREAD_STAGE2_RESULTS.md")
    args = ap.parse_args()

    panel, branch = load_events()
    print(f"{len(branch)} branch events (breakout52=FALSE)")
    rows = load_option_rows(needs_for_events(branch, panel.dates))
    print(f"{len(rows)} option rows cached")
    if args.prepare_only:
        return 0

    from core.surge.report import build_report  # noqa: E402
    from core.surge.spreads import run_stage2  # noqa: E402
    result = run_stage2(panel, branch, rows, cutoff=CUTOFF)
    Path(args.out).write_text(build_report(result), encoding="utf-8")
    print(f"verdict: {result.verdict}; chosen: {result.chosen}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
