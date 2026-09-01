#!/usr/bin/env python3
"""
QuantOS — Candidate 18 Spread-Sample Stratified Analysis
──────────────────────────────────────────────────────────────────────
Fable's review (2026-07-31) of the Sampled-spread cost variant flagged
that a single blended spread rate per index hides a real risk: the one
post-close snapshot that made NIFTY fail (2026-07-28) happened to land on
BOTH NIFTY's weekly and BankNifty's monthly expiry -- plausibly an
outlier-wide-spread day, not a representative one. Blending expiry-day and
ordinary-day samples into one average (as `core/orb_scalping/costs.py`'s
SAMPLED_SPREAD_SLIPPAGE_BPS currently does) can't tell that apart. This
script re-slices `data_cache/orb_scalping_spread_samples.csv` (accumulated
by `deploy/systemd/quantos-orb-spread-probe.timer`) by whether the
CALENDAR DATE a sample was taken on was itself a NIFTY weekly / BankNifty
monthly expiry day, alongside the existing per-underlying/per-option-type
breakdown -- pure post-processing, no probe/timer changes needed.

Uses the UNADJUSTED expiry calendar (core/orb_scalping/expiry.py's
`nifty_weekly_expiry_unadjusted`, scripts/gutcheck_expiry_day_effect.py's
`calendar_expiry_date`) rather than the holiday-adjusted one, since this
script has no trading-day set of its own to adjust against (unlike the
backtest, which has the fetched candle set to derive one from) -- this
only misclassifies a date in the rare week an actual expiry Tuesday/
Thursday is itself a market holiday, flagged here rather than silently
assumed away.

Usage:
    python scripts/analyze_orb_spread_samples.py
    python scripts/analyze_orb_spread_samples.py --csv path/to/other.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orb_scalping.expiry import nifty_weekly_expiry_unadjusted  # noqa: E402
from scripts.gutcheck_expiry_day_effect import calendar_expiry_date  # noqa: E402

IST_OFFSET = timedelta(hours=5, minutes=30)
DEFAULT_CSV = Path("data_cache/orb_scalping_spread_samples.csv")
MIN_SAMPLE_FOR_MEAN = 3  # below this, report the raw values instead of a misleading mean

# Fable's adversarial review (2026-09-01) of the Stratified cost variant found
# two rows -- 2026-08-04 02:10 UTC (07:40 IST) and 2026-07-30 02:55 UTC
# (08:25 IST) -- sitting inside the accumulated sample set despite predating
# market open (09:15 IST). Neither matches the timer's own OnCalendar fires
# (04:05/06:30/09:45 UTC); both are leftover manual/hand-fired test runs from
# earlier sessions (one already traced via journalctl, see the module's git
# history). Their quotes are 10-15x every legitimate intraday sample and
# single-handedly manufactured the "expiry-day spread is roughly DOUBLE"
# finding for NIFTY -- the strategy only ever executes 09:35-15:20 IST, so an
# object filter on session hours removes them regardless of how they got
# there, rather than trying to enumerate every possible off-schedule cause.
SESSION_START_UTC = time(3, 45)   # 09:15 IST
SESSION_END_UTC = time(10, 0)     # 15:30 IST


def ist_date(sampled_at_utc: str) -> date:
    """`sampled_at_utc` is an ISO-8601 UTC timestamp (as written by
    probe_orb_scalping_real_spreads.py) -- convert to the IST calendar date
    the sample was actually taken on."""
    dt_utc = datetime.fromisoformat(sampled_at_utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return (dt_utc + IST_OFFSET).date()


def is_in_session(sampled_at_utc: str) -> bool:
    """True iff the sample's UTC wall-clock time falls inside the NSE
    trading session (09:15-15:30 IST). A pre-open or post-close quote is not
    a tradeable spread and must not enter any mean."""
    dt_utc = datetime.fromisoformat(sampled_at_utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return SESSION_START_UTC <= dt_utc.time() < SESSION_END_UTC


def is_nifty_weekly_expiry_day(d: date) -> bool:
    """True iff `d` is itself NIFTY's own weekly expiry date (unadjusted
    calendar -- see module docstring)."""
    return nifty_weekly_expiry_unadjusted(d) == d


def is_banknifty_monthly_expiry_day(d: date) -> bool:
    """True iff `d` is itself BankNifty's own monthly expiry date
    (unadjusted calendar -- see module docstring)."""
    return calendar_expiry_date(d.year, d.month) == d


def _blended_bps(pcts: list[float]) -> float:
    """Same conversion core/orb_scalping/costs.py's variants use:
    slippage_bps is charged on both legs, so round-trip spread_pct =
    2 * slippage_bps / 100 -> slippage_bps = 50 * spread_pct."""
    return 50 * (sum(pcts) / len(pcts))


def load_rows(csv_path: Path) -> list[dict]:
    """Returns (in-session rows used for every mean, discarded out-of-session
    rows -- reported, never silently swallowed)."""
    all_rows = list(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
    rows, discarded = [], []
    for r in all_rows:
        r["_ist_date"] = ist_date(r["sampled_at_utc"])
        r["_is_expiry_day"] = (
            is_nifty_weekly_expiry_day(r["_ist_date"]) if r["underlying"] == "NIFTY"
            else is_banknifty_monthly_expiry_day(r["_ist_date"])
        )
        (rows if is_in_session(r["sampled_at_utc"]) else discarded).append(r)
    return rows, discarded


def _report_bucket(label: str, pcts: list[float]) -> None:
    if not pcts:
        print(f"  {label}: n=0 (no samples yet)")
        return
    if len(pcts) < MIN_SAMPLE_FOR_MEAN:
        print(f"  {label}: n={len(pcts)} (too few for a mean) -- raw values: "
              f"{', '.join(f'{p:.2f}%' for p in pcts)}")
        return
    mean = sum(pcts) / len(pcts)
    print(f"  {label}: n={len(pcts)}  mean={mean:.3f}%  min={min(pcts):.3f}%  "
          f"max={max(pcts):.3f}%  -> slippage_bps={_blended_bps(pcts):.1f}")


def analyze(rows: list[dict], discarded: list[dict]) -> None:
    distinct_days = {r["_ist_date"] for r in rows}
    expiry_days = {r["_ist_date"] for r in rows if r["_is_expiry_day"]}
    print(f"{len(rows)} in-session rows, {len(distinct_days)} distinct IST calendar days "
          f"({len(expiry_days)} of those are an expiry day for the sampled underlying).")
    if discarded:
        print(f"{len(discarded)} row(s) discarded as out-of-session (before 09:15 or at/after "
              f"15:30 IST -- not a tradeable spread):")
        for r in discarded:
            print(f"    {r['sampled_at_utc']}  {r['underlying']} {r['option_type']}  "
                  f"spread={r.get('spread_pct_of_mid', '?')}%")
    print()

    for underlying in ("NIFTY", "BANKNIFTY"):
        print(f"=== {underlying} ===")
        for expiry_flag, expiry_label in ((False, "non-expiry-day"), (True, "expiry-day")):
            bucket_rows = [r for r in rows if r["underlying"] == underlying
                           and r["_is_expiry_day"] == expiry_flag]
            ce = [float(r["spread_pct_of_mid"]) for r in bucket_rows
                  if r["option_type"] == "CE" and r["spread_pct_of_mid"] != ""]
            pe = [float(r["spread_pct_of_mid"]) for r in bucket_rows
                  if r["option_type"] == "PE" and r["spread_pct_of_mid"] != ""]
            print(f" {expiry_label}:")
            _report_bucket("  CE", ce)
            _report_bucket("  PE", pe)
            if len(ce) >= MIN_SAMPLE_FOR_MEAN and len(pe) >= MIN_SAMPLE_FOR_MEAN:
                mean_ce, mean_pe = sum(ce) / len(ce), sum(pe) / len(pe)
                blended_mean = (mean_ce + mean_pe) / 2
                print(f"  blended (CE+PE averaged, matches costs.py's convention): "
                      f"{blended_mean:.3f}%  -> slippage_bps={50 * blended_mean:.1f}")
        print()

    if not expiry_days:
        print("No expiry-day samples yet for either underlying -- the current "
              "SAMPLED_SPREAD_SLIPPAGE_BPS constant in core/orb_scalping/costs.py "
              "is effectively a non-expiry-day-only rate by accident, not by "
              "design. Re-run this analysis once at least one NIFTY weekly or "
              "BankNifty monthly expiry day has been sampled by the timer.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"No log yet at {args.csv} -- nothing to analyze.")
        return 1

    rows, discarded = load_rows(args.csv)
    analyze(rows, discarded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
