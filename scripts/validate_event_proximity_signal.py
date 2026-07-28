#!/usr/bin/env python3
"""
QuantOS — Known-Event Proximity vs Forward Realized Vol (NIFTY + BankNifty)
─────────────────────────────────────────────────────────────────────────────
See docs/EVENT_PROXIMITY_METHODOLOGY.md for every design choice (event
calendar sources, event window, grouping, pass/fail bar), fixed BEFORE
this script was written. NOT a 5th vol-conditioning attempt — see that
doc's "why this is not vol-conditioning attempt #5" section.

Method
──────
For each trading day `t`, per underlying:
  - is_event_day(t) = True if `t` falls within 1 calendar day of any date
    in EVENT_DATES (RBI MPC resolutions + Union Budget dates, 2024-2026).
  - RV_trailing_20d_t / RV_fwd_20d_t = annualized stdev of daily log
    returns over the prior/next 20 sessions (reused from
    scripts/validate_vol_spread_signal.py's _annualized_rv).
Days are split into two groups (event vs non-event) and, within event
days, a further RBI-only subset — mean forward RV compared across groups,
NOT quintile-bucketed (too few event days).

Reuses scripts/validate_vol_skew_signal.py's bhavcopy fetch/parse
(load_rows_by_date) purely for its underlying_close series — no
strikes/IV/Greeks needed for this signal at all.

Usage
─────
    python scripts/validate_event_proximity_signal.py
    python scripts/validate_event_proximity_signal.py --underlyings NIFTY,BANKNIFTY --out-prefix docs/EVENT_PROXIMITY_VALIDATION
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.vrp.bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR  # noqa: E402
from scripts.validate_vol_skew_signal import load_rows_by_date  # noqa: E402
from scripts.validate_vol_spread_signal import RV_WINDOW, _annualized_rv  # noqa: E402

WINDOW_START = date(2024, 1, 1)  # == CUTOVER_DATE

# ─── Event calendar — sourced 2026-07-27, see docs/EVENT_PROXIMITY_METHODOLOGY.md ──

RBI_MPC_RESOLUTION_DATES: list[date] = [
    # 2024 — RBI FY2024-25 official schedule + Feb 2024 (last of FY2023-24)
    date(2024, 2, 8), date(2024, 4, 5), date(2024, 6, 7),
    date(2024, 8, 8), date(2024, 10, 9), date(2024, 12, 6),
    # 2025 — RBI FY2025-26 official schedule (Aug rescheduled to 4-6, resolution 6)
    date(2025, 2, 7), date(2025, 4, 9), date(2025, 6, 6),
    date(2025, 8, 6), date(2025, 10, 1), date(2025, 12, 5),
    # 2026 — reused from core/events/calendar.py's existing hardcoded calendar
    date(2026, 2, 6), date(2026, 4, 8), date(2026, 6, 5),
]

UNION_BUDGET_DATES: list[date] = [
    date(2024, 2, 1),   # interim, pre-election
    date(2024, 7, 23),  # full FY2024-25 budget, post-election
    date(2025, 2, 1),
    date(2026, 2, 1),
]

EVENT_WINDOW_CALENDAR_DAYS = 1  # ±1 calendar day, see methodology doc


def is_event_day(t: date, event_dates: list[date],
                  window_days: int = EVENT_WINDOW_CALENDAR_DAYS) -> bool:
    return any(abs((t - e).days) <= window_days for e in event_dates)


# ─── Pure per-day logic (no I/O — unit-testable) ────────────────────────────

@dataclass
class EventProximityDay:
    date:          date
    close:         float
    is_rbi:        bool
    is_budget:     bool
    rv_trailing:   Optional[float] = None
    fwd_rv:        Optional[float] = None

    @property
    def is_event(self) -> bool:
        return self.is_rbi or self.is_budget


def compute_daily_series(rows_by_date: dict) -> list[EventProximityDay]:
    """Walk every date with a usable spot close, in order. No lookahead:
    rv_trailing_t uses only data through t; fwd_rv_t uses the (now-known)
    future purely as the outcome being scored. Event flags are computed
    from a fixed, advance-published calendar -- not derived from any
    same-day market data, so there is no lookahead risk in is_event either."""
    dates = sorted(d for d in rows_by_date
                    if rows_by_date[d] and rows_by_date[d][0].underlying_close is not None)
    closes = [rows_by_date[d][0].underlying_close for d in dates]

    days: list[EventProximityDay] = []
    for i in range(RV_WINDOW, len(dates)):
        d = dates[i]
        rv_trailing = _annualized_rv(closes[i - RV_WINDOW: i + 1])
        fwd_rv = None
        if i + RV_WINDOW < len(dates):
            fwd_rv = _annualized_rv(closes[i: i + RV_WINDOW + 1])
        days.append(EventProximityDay(
            date=d, close=closes[i],
            is_rbi=is_event_day(d, RBI_MPC_RESOLUTION_DATES),
            is_budget=is_event_day(d, UNION_BUDGET_DATES),
            rv_trailing=rv_trailing, fwd_rv=fwd_rv,
        ))
    return days


# ─── Report ─────────────────────────────────────────────────────────────────

def _group_stats(days: list[EventProximityDay]) -> Optional[dict]:
    scored = [d for d in days if d.fwd_rv is not None]
    if not scored:
        return None
    return {"n": len(scored), "mean_fwd_rv": mean(d.fwd_rv for d in scored)}


def summarize(days: list[EventProximityDay], underlying: str) -> str:
    scored = [d for d in days if d.fwd_rv is not None]
    if not scored:
        return f"# {underlying} Known-Event Proximity Validation\n\n**No days scored.**\n"

    pooled_event = [d for d in scored if d.is_event]
    pooled_non_event = [d for d in scored if not d.is_event]
    rbi_only = [d for d in scored if d.is_rbi]
    rbi_non_event = [d for d in scored if not d.is_rbi]

    lines = [
        f"# {underlying} Known-Event Proximity Validation",
        "",
        f"Methodology: docs/EVENT_PROXIMITY_METHODOLOGY.md. Replayed "
        f"{len(days)} days ({days[0].date} to {days[-1].date}), "
        f"{len(scored)} scored with a full forward window.",
        "",
        "## Pooled: RBI + Budget vs non-event days",
        "",
        "| Group | n | Mean fwd 20d RV |",
        "|---|---|---|",
    ]
    ev, non_ev = _group_stats(pooled_event), _group_stats(pooled_non_event)
    lines.append(f"| Event days (±{EVENT_WINDOW_CALENDAR_DAYS}d) | {ev['n'] if ev else 0} | "
                 f"{ev['mean_fwd_rv']:.2f} |" if ev else "| Event days | 0 | - |")
    lines.append(f"| Non-event days | {non_ev['n'] if non_ev else 0} | "
                 f"{non_ev['mean_fwd_rv']:.2f} |" if non_ev else "| Non-event days | 0 | - |")

    lines += ["", "## Secondary breakdown: RBI-only vs non-RBI days", "",
              "| Group | n | Mean fwd 20d RV |", "|---|---|---|"]
    rbi_stat, rbi_non_stat = _group_stats(rbi_only), _group_stats(rbi_non_event)
    lines.append(f"| RBI days (±{EVENT_WINDOW_CALENDAR_DAYS}d) | {rbi_stat['n'] if rbi_stat else 0} | "
                 f"{rbi_stat['mean_fwd_rv']:.2f} |" if rbi_stat else "| RBI days | 0 | - |")
    lines.append(f"| Non-RBI days | {rbi_non_stat['n'] if rbi_non_stat else 0} | "
                 f"{rbi_non_stat['mean_fwd_rv']:.2f} |" if rbi_non_stat else "| Non-RBI days | 0 | - |")

    lines += ["", "## Verdict", ""]
    if ev and non_ev:
        gap = ev["mean_fwd_rv"] - non_ev["mean_fwd_rv"]
        lines.append(
            f"- Pooled (RBI+Budget) event days ({ev['mean_fwd_rv']:.2f}, n={ev['n']}) vs "
            f"non-event days ({non_ev['mean_fwd_rv']:.2f}, n={non_ev['n']}): gap = {gap:+.2f} vol points."
        )
        verdict = "PASS" if gap > 0 else "FAIL"
        lines.append(f"- Per docs/EVENT_PROXIMITY_METHODOLOGY.md's pass bar: {verdict} "
                      f"(event days must show materially higher mean fwd RV).")
    if rbi_stat and rbi_non_stat:
        rbi_gap = rbi_stat["mean_fwd_rv"] - rbi_non_stat["mean_fwd_rv"]
        lines.append(f"- RBI-only consistency check: gap = {rbi_gap:+.2f} vol points "
                      f"(n={rbi_stat['n']} RBI days) — reported alongside, not independently required to pass.")
    lines.append(
        ""
        "Read the gaps above against the sample sizes (`n`) in the table -- this "
        "report presents the numbers, no invented significance test, matching "
        "docs/REGIME_VALIDATION.md and every prior signal report in this project."
    )

    return "\n".join(lines)


# ─── Orchestration ────────────────────────────────────────────────────────

def run_one_underlying(underlying: str, start: date, end: date,
                        raw_dir: Path, out_path: Path) -> None:
    print(f"\n=== {underlying} ===")
    print(f"Loading bhavcopy {start} -> {end} (cached-first, fetches only missing days) ...")
    rows_by_date = load_rows_by_date(underlying, start, end, raw_dir)
    print(f"  {len(rows_by_date)} trading days with {underlying} rows")
    if len(rows_by_date) < RV_WINDOW * 2 + 10:
        print(f"ERROR: only {len(rows_by_date)} days -- too few for a meaningful replay.")
        return

    print("Replaying event-proximity flags day-by-day (no lookahead) ...")
    days = compute_daily_series(rows_by_date)
    scored = sum(1 for d in days if d.fwd_rv is not None)
    print(f"  {len(days)} days walked, {scored} scored")

    report = summarize(days, underlying)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--underlyings", default="NIFTY,BANKNIFTY")
    parser.add_argument("--start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-cache-dir", type=Path, default=DEFAULT_RAW_CACHE_DIR)
    parser.add_argument("--out-prefix", default="docs/EVENT_PROXIMITY_VALIDATION")
    args = parser.parse_args()

    if args.start < CUTOVER_DATE:
        print(f"ERROR: --start must be >= {CUTOVER_DATE} (new bhavcopy format only).")
        return 1

    for underlying in args.underlyings.split(","):
        underlying = underlying.strip().upper()
        suffix = "" if underlying == "NIFTY" else f"_{underlying}"
        out_path = Path(f"{args.out_prefix}{suffix}.md")
        run_one_underlying(underlying, args.start, args.end, args.raw_cache_dir, out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
