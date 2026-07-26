#!/usr/bin/env python3
"""
QuantOS — F&O Monthly Expiry-Day Effect Gut-Check
──────────────────────────────────────────────────────────────────────────────
Candidate 13 (see docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md, fixed
BEFORE this script was run). Tests whether NIFTY daily |return| is
elevated around monthly F&O expiry -- a cheap descriptive gut-check, NOT a
backtest (no costs, no position sizing, no signal threshold), same
sequencing every prior candidate in this project used (PEAD, index
reconstitution) before ever reaching a full backtest.

Data: NIFTY underlying_close from core/options/vrp/bhavcopy.py's already-
cached raw bhavcopy zips (data_cache/nse_bhavcopy/raw/), new-format schema
only (2024-01-01 onward, see CUTOVER_DATE). No live broker connection
needed -- the whole window is already on disk.

Expiry-date construction (last Thursday through 2025-08-31, last Tuesday
from 2025-09-01 onward per SEBI/HO/MRD/TPD-1/P/CIR/2025/76, holiday
rolled to the nearest EARLIER real trading day) matches the methodology
doc exactly -- do not change this logic after seeing a result; see that
doc's "what would make this untrustworthy" section.

Usage
─────
    python scripts/gutcheck_expiry_day_effect.py
    python scripts/gutcheck_expiry_day_effect.py --out docs/EXPIRY_DAY_EFFECT_GUTCHECK_RESULTS.md
"""

import argparse
import csv
import io
import sys
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.vrp.bhavcopy import (  # noqa: E402
    BhavcopyNotAvailable, CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR, fetch_raw,
)

WINDOW_START = date(2024, 1, 1)  # == CUTOVER_DATE; new bhavcopy format only, underlying_close unpopulated before this

# Last Thursday convention for any raw expiry date on/before this; last
# Tuesday from the next calendar day on. See methodology doc for the full
# SEBI/NSE circular citation trail and the superseded March-2025 Monday proposal.
LAST_THURSDAY_CUTOFF = date(2025, 8, 31)

GROUPS = ("expiry", "pre_expiry", "post_expiry", "other")


# ─── Expiry-date construction (pure, unit-testable) ─────────────────────────

def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """weekday: Monday=0 ... Sunday=6."""
    next_month_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    d = next_month_first - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def calendar_expiry_date(year: int, month: int) -> date:
    """Un-adjusted expiry weekday for `year`-`month`, before holiday
    adjustment. Last Thursday if that date falls on/before
    LAST_THURSDAY_CUTOFF, else last Tuesday -- see methodology doc."""
    thursday = _last_weekday_of_month(year, month, 3)
    if thursday <= LAST_THURSDAY_CUTOFF:
        return thursday
    return _last_weekday_of_month(year, month, 1)


def adjust_for_holiday(d: date, trading_days: set) -> date:
    """Rolls to the nearest EARLIER date present in `trading_days` -- no
    hardcoded holiday calendar, same "bhavcopy row = trading day" rule
    every prior bhavcopy-based script in this project uses."""
    while d not in trading_days:
        d -= timedelta(days=1)
    return d


def expiry_dates_in_range(start: date, end: date, trading_days: set) -> list:
    """One holiday-adjusted expiry date per calendar month touching
    [start, end]."""
    out = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        raw = calendar_expiry_date(year, month)
        out.append(adjust_for_holiday(raw, trading_days))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return sorted(set(out))


# ─── Day classification (pure, unit-testable) ────────────────────────────────

@dataclass(frozen=True)
class Overlap:
    kind: str    # "pre_expiry_overlap" or "post_expiry_overlap"
    target: date
    from_expiry: date


def classify_days(trading_days_sorted: list, expiries: list) -> tuple:
    """Returns (labels, overlaps). `expiry` takes priority over
    `pre_expiry`/`post_expiry`, which take priority over `other` -- see
    methodology doc. `overlaps` records any pre/post target that lands on
    an already-`expiry` day (an unusually short month), logged rather than
    assumed impossible."""
    labels = {d: "other" for d in trading_days_sorted}
    idx = {d: i for i, d in enumerate(trading_days_sorted)}
    expiry_set = [e for e in expiries if e in idx]

    for e in expiry_set:
        labels[e] = "expiry"

    overlaps = []
    for e in expiry_set:
        i = idx[e]
        if i > 0:
            pre = trading_days_sorted[i - 1]
            if labels[pre] == "other":
                labels[pre] = "pre_expiry"
            elif labels[pre] == "expiry":
                overlaps.append(Overlap("pre_expiry_overlap", pre, e))
        if i + 1 < len(trading_days_sorted):
            post = trading_days_sorted[i + 1]
            if labels[post] == "other":
                labels[post] = "post_expiry"
            elif labels[post] == "expiry":
                overlaps.append(Overlap("post_expiry_overlap", post, e))
    return labels, overlaps


# ─── NIFTY spot loader (I/O -- cached-file reads, network only on a gap) ────

def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _parse_nifty_underlying_close(raw_zip: bytes) -> Optional[float]:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        raw_csv = zf.read(zf.namelist()[0]).decode("utf-8")
    for r in csv.DictReader(io.StringIO(raw_csv)):
        if r["FinInstrmTp"] == "IDO" and r["TckrSymb"] == "NIFTY" and r.get("UndrlygPric"):
            return float(r["UndrlygPric"])
    return None


def load_nifty_closes(start: date, end: date, raw_dir: Path) -> dict:
    closes = {}
    for d in _weekdays(start, end):
        try:
            raw = fetch_raw(d, raw_dir)
        except BhavcopyNotAvailable:
            continue
        spot = _parse_nifty_underlying_close(raw)
        if spot is not None:
            closes[d] = spot
    return closes


# ─── Report ───────────────────────────────────────────────────────────────

def summarize(closes: dict, overlaps: list) -> str:
    dates_sorted = sorted(closes)
    trading_days = set(dates_sorted)
    expiries = expiry_dates_in_range(dates_sorted[0], dates_sorted[-1], trading_days)
    labels, found_overlaps = classify_days(dates_sorted, expiries)
    overlaps.extend(found_overlaps)

    returns_by_group = {g: [] for g in GROUPS}
    for i in range(1, len(dates_sorted)):
        d = dates_sorted[i]
        prev = dates_sorted[i - 1]
        ret_pct = (closes[d] / closes[prev] - 1) * 100
        returns_by_group[labels[d]].append(ret_pct)

    lines = [
        "# F&O Monthly Expiry-Day Effect Gut-Check",
        "",
        "Methodology: docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md. "
        f"NIFTY spot, {dates_sorted[0]} to {dates_sorted[-1]} "
        f"({len(dates_sorted)} trading days, {len(expiries)} expiries).",
        "",
    ]
    if overlaps:
        lines.append("## Overlaps (short-month expiry/pre/post collision)")
        lines.append("")
        for ov in overlaps:
            lines.append(f"- `{ov.kind}`: {ov.target} (from expiry {ov.from_expiry})")
        lines.append("")

    lines += [
        "## Mean |daily return| by day-group",
        "",
        "| Group | n | Mean return % | Mean \\|return\\| % |",
        "|---|---|---|---|",
    ]
    stats = {}
    for g in GROUPS:
        rets = returns_by_group[g]
        if not rets:
            lines.append(f"| {g} | 0 | - | - |")
            continue
        m_ret = mean(rets)
        m_abs = mean(abs(r) for r in rets)
        stats[g] = {"n": len(rets), "mean_return": m_ret, "mean_abs_return": m_abs}
        lines.append(f"| {g} | {len(rets)} | {m_ret:+.3f} | {m_abs:.3f} |")

    lines += ["", "## Verdict", ""]
    baseline = stats.get("other")
    if baseline:
        for g in ("expiry", "pre_expiry", "post_expiry"):
            st = stats.get(g)
            if not st:
                continue
            gap = st["mean_abs_return"] - baseline["mean_abs_return"]
            gap_pct = (gap / baseline["mean_abs_return"] * 100) if baseline["mean_abs_return"] else 0.0
            lines.append(
                f"- `{g}` mean |return| ({st['mean_abs_return']:.3f}%, n={st['n']}) vs "
                f"`other` ({baseline['mean_abs_return']:.3f}%, n={baseline['n']}): "
                f"gap = {gap:+.3f}pp ({gap_pct:+.1f}% relative)."
            )
    lines.append(
        ""
        "Read the gaps above against the sample sizes (`n`) in the table -- "
        f"only ~{len(expiries)} expiries in this window, the disclosed thin-sample "
        "limitation in the methodology doc. No demeaning, no market adjustment, "
        "no invented significance test, same style as docs/VOL_SPREAD_VALIDATION.md "
        "and docs/VOL_SKEW_VALIDATION.md."
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-cache-dir", type=Path, default=DEFAULT_RAW_CACHE_DIR)
    parser.add_argument("--out", default="docs/EXPIRY_DAY_EFFECT_GUTCHECK_RESULTS.md")
    args = parser.parse_args()

    if args.start < CUTOVER_DATE:
        print(f"ERROR: --start must be >= {CUTOVER_DATE} (new bhavcopy format only, "
              f"see docs/EXPIRY_DAY_EFFECT_GUTCHECK_METHODOLOGY.md).")
        return 1

    print(f"Loading NIFTY spot {args.start} -> {args.end} (cached-first) ...")
    closes = load_nifty_closes(args.start, args.end, args.raw_cache_dir)
    print(f"  {len(closes)} trading days with NIFTY spot")
    if len(closes) < 60:
        print(f"ERROR: only {len(closes)} days -- too few for a meaningful gut-check.")
        return 1

    overlaps: list = []
    report = summarize(closes, overlaps)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    if overlaps:
        print(f"  {len(overlaps)} overlap(s) logged -- see report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
