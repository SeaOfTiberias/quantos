#!/usr/bin/env python3
"""
QuantOS — Vol-Conditioning Signal Validation: Option Skew (NIFTY + BankNifty)
──────────────────────────────────────────────────────────────────────────────
Third vol-conditioning attempt after two failures (core/regime/classifier.py's
VIX-level bands, docs/VOL_SPREAD_VALIDATION.md's IV-minus-RV spread). See
docs/VOL_SKEW_METHODOLOGY.md for every design choice (strike/expiry
selection, skew construction, bucketing, pass/fail bar), fixed BEFORE this
script was written, and docs/VOL_SKEW_METHODOLOGY_BANKNIFTY_ADDENDUM.md for
the second-underlying extension.

Method
──────
For each trading day with cached NSE bhavcopy data:
  - Spot = that day's UndrlygPric (shared across every row that day).
  - Expiry = nearest listed expiry with >=3 calendar days to trade date.
  - OTM put/call = nearest strike to spot*0.95 / spot*1.05 respectively,
    skipped if actual moneyness is outside [3%, 7%].
  - IV for each leg via core/options/greeks.py's Black-Scholes bisection
    solver, using that leg's settlement price — days are skipped (not fed a
    fallback constant) if either leg would hit implied_volatility()'s
    intrinsic-value/DTE<=0 fallback path.
  - Skew_t = IV_put_OTM,t - IV_call_OTM,t.
Then, using the (now-known) future NIFTY/BankNifty spot series:
  - RV_trailing_20d_t / RV_fwd_20d_t = annualized stdev of daily log
    returns over the prior/next 20 sessions.
Days are bucketed into quintiles of Skew_t (data-driven cutpoints from the
full sample) and each bucket's mean forward RV is reported. Reuses
quintile_cutoffs/assign_bucket/_annualized_rv/NUM_BUCKETS directly from
scripts/validate_vol_spread_signal.py rather than reimplementing them.

Data source: core/options/vrp/bhavcopy.py's already-cached raw bhavcopy
zips (data_cache/nse_bhavcopy/raw/), re-parsed here with an
underlying-filtered parser distinct from that module's NIFTY-only parsed
cache -- VRP's own parsed cache is never read or written by this script.
No live broker connection needed.

This is deliberately NOT connected to VRP's trade data or the
Iron-Condor-mislabeled-straddle CSV reviewed 2026-07-25 -- see
docs/VOL_SKEW_METHODOLOGY.md's "mandatory sequencing" section for why.

Usage
─────
    python scripts/validate_vol_skew_signal.py
    python scripts/validate_vol_skew_signal.py --underlyings NIFTY,BANKNIFTY --out-prefix docs/VOL_SKEW_VALIDATION
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

from core.options.greeks import DEFAULT_RISK_FREE_RATE, implied_volatility  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.options.vrp.bhavcopy import (  # noqa: E402
    BhavcopyNotAvailable, CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR, fetch_raw,
)
from scripts.validate_vol_spread_signal import (  # noqa: E402
    RV_WINDOW, NUM_BUCKETS, TRADING_DAYS_PER_YEAR,
    _annualized_rv, assign_bucket, quintile_cutoffs,
)

TARGET_OTM_PCT = 0.05          # 5% OTM target, each side -- see methodology doc
MONEYNESS_TOLERANCE_PCT = 0.02  # actual OTM% must fall in [3%, 7%]
MIN_DTE = 3                     # calendar days, skip 0-2 DTE pin/gamma noise

WINDOW_START = date(2024, 1, 1)  # == CUTOVER_DATE; new bhavcopy format only


# ─── Minimal per-underlying raw-zip row (mirrors BhavcopyOptionRow's fields
# this script actually needs) ──────────────────────────────────────────────

@dataclass(frozen=True)
class OptionRow:
    expiry:            date
    strike:            float
    option_type:       OptionType
    settle_price:      float
    underlying_close:  Optional[float]


def parse_raw_zip_for_underlying(raw_zip: bytes, underlying: str) -> list[OptionRow]:
    """Filters the untouched raw bhavcopy zip to one underlying's index-option
    (IDO) rows. New-format schema only (see WINDOW_START) -- this script
    never reads legacy-format bhavcopy files, so no dual-schema branch is
    needed here, unlike core/options/vrp/bhavcopy.py's parser."""
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        names = zf.namelist()
        raw_csv = zf.read(names[0]).decode("utf-8")
    rows = []
    for r in csv.DictReader(io.StringIO(raw_csv)):
        if r["FinInstrmTp"] != "IDO" or r["TckrSymb"] != underlying:
            continue
        rows.append(OptionRow(
            expiry=date.fromisoformat(r["XpryDt"]),
            strike=float(r["StrkPric"]),
            option_type=OptionType.CALL if r["OptnTp"] == "CE" else OptionType.PUT,
            settle_price=float(r["SttlmPric"]),
            underlying_close=float(r["UndrlygPric"]) if r.get("UndrlygPric") else None,
        ))
    return rows


# ─── Pure per-day skew logic (no I/O -- unit-testable with synthetic rows) ──

def select_expiry(expiries: list[date], trade_date: date, min_dte: int = MIN_DTE) -> Optional[date]:
    candidates = sorted(e for e in expiries if (e - trade_date).days >= min_dte)
    return candidates[0] if candidates else None


def select_otm_row(rows: list[OptionRow], spot: float, option_type: OptionType) -> Optional[OptionRow]:
    """Nearest strike to the 5%-OTM target; ties broken toward the strike
    further OTM (smaller strike for a put, larger for a call) so the rule is
    deterministic. Returns None if no candidate exists at all."""
    candidates = [r for r in rows if r.option_type == option_type]
    if not candidates:
        return None
    target = spot * (1 - TARGET_OTM_PCT) if option_type == OptionType.PUT else spot * (1 + TARGET_OTM_PCT)
    tiebreak = (lambda r: r.strike) if option_type == OptionType.PUT else (lambda r: -r.strike)
    candidates.sort(key=lambda r: (abs(r.strike - target), tiebreak(r)))
    return candidates[0]


def _within_moneyness_tolerance(row: OptionRow, spot: float) -> bool:
    actual_otm_pct = abs(row.strike - spot) / spot
    return (TARGET_OTM_PCT - MONEYNESS_TOLERANCE_PCT) <= actual_otm_pct <= (TARGET_OTM_PCT + MONEYNESS_TOLERANCE_PCT)


def _would_hit_iv_fallback(market_price: float, spot: float, strike: float,
                            dte: int, option_type: OptionType) -> bool:
    """Mirrors implied_volatility()'s own fallback preconditions (DTE<=0,
    price<=0, price<=intrinsic) so this validation can SKIP a day rather
    than silently absorb its 0.18 default into the sample."""
    if dte <= 0 or market_price <= 0:
        return True
    intrinsic = (max(0.0, spot - strike) if option_type == OptionType.CALL
                 else max(0.0, strike - spot))
    return market_price <= intrinsic


def compute_skew_for_date(rows: list[OptionRow], trade_date: date) -> tuple[Optional[float], Optional[float], str]:
    """Returns (spot, skew, skip_reason). skip_reason == "" on success."""
    if not rows:
        return None, None, "no_rows"
    spot = rows[0].underlying_close
    if spot is None:
        return None, None, "no_underlying_close"

    expiry = select_expiry(sorted(set(r.expiry for r in rows)), trade_date)
    if expiry is None:
        return spot, None, "no_valid_expiry"

    expiry_rows = [r for r in rows if r.expiry == expiry]
    put_row = select_otm_row(expiry_rows, spot, OptionType.PUT)
    call_row = select_otm_row(expiry_rows, spot, OptionType.CALL)
    if put_row is None or call_row is None:
        return spot, None, "no_otm_candidate"
    if not _within_moneyness_tolerance(put_row, spot) or not _within_moneyness_tolerance(call_row, spot):
        return spot, None, "moneyness_tolerance"

    dte = (expiry - trade_date).days
    if _would_hit_iv_fallback(put_row.settle_price, spot, put_row.strike, dte, OptionType.PUT):
        return spot, None, "iv_fallback_put"
    if _would_hit_iv_fallback(call_row.settle_price, spot, call_row.strike, dte, OptionType.CALL):
        return spot, None, "iv_fallback_call"

    put_iv = implied_volatility(
        market_price=put_row.settle_price, spot=spot, strike=put_row.strike,
        days_to_expiry=dte, option_type=OptionType.PUT, risk_free_rate=DEFAULT_RISK_FREE_RATE,
    )
    call_iv = implied_volatility(
        market_price=call_row.settle_price, spot=spot, strike=call_row.strike,
        days_to_expiry=dte, option_type=OptionType.CALL, risk_free_rate=DEFAULT_RISK_FREE_RATE,
    )
    return spot, put_iv - call_iv, ""


@dataclass
class SkewDay:
    date:         date
    spot:         float
    skew:         Optional[float]
    skip_reason:  str
    rv_trailing:  Optional[float] = None
    fwd_rv:       Optional[float] = None


def compute_daily_series(rows_by_date: dict[date, list[OptionRow]]) -> list[SkewDay]:
    """Walk every date with a usable spot close, in order. No lookahead:
    skew_t and rv_trailing_t use only data through t; fwd_rv_t uses the
    (now-known) future purely as the outcome being scored."""
    dates = sorted(d for d in rows_by_date
                    if rows_by_date[d] and rows_by_date[d][0].underlying_close is not None)
    closes = [rows_by_date[d][0].underlying_close for d in dates]

    days: list[SkewDay] = []
    for i in range(RV_WINDOW, len(dates)):
        d = dates[i]
        spot, skew, reason = compute_skew_for_date(rows_by_date[d], d)
        rv_trailing = _annualized_rv(closes[i - RV_WINDOW: i + 1])
        fwd_rv = None
        if i + RV_WINDOW < len(dates):
            fwd_rv = _annualized_rv(closes[i: i + RV_WINDOW + 1])
        days.append(SkewDay(
            date=d, spot=spot if spot is not None else closes[i], skew=skew,
            skip_reason=reason, rv_trailing=rv_trailing, fwd_rv=fwd_rv,
        ))
    return days


# ─── Report ─────────────────────────────────────────────────────────────────

def summarize(days: list[SkewDay], underlying: str) -> str:
    scored = [d for d in days if d.skew is not None and d.fwd_rv is not None]
    skip_counts: dict[str, int] = {}
    for d in days:
        if d.skew is None:
            skip_counts[d.skip_reason] = skip_counts.get(d.skip_reason, 0) + 1

    if not scored:
        return f"# {underlying} Option Skew Validation\n\n**No days scored.**\n"

    cutoffs = quintile_cutoffs([d.skew for d in scored])
    by_bucket: dict[int, list[SkewDay]] = {b: [] for b in range(1, NUM_BUCKETS + 1)}
    for d in scored:
        by_bucket[assign_bucket(d.skew, cutoffs)].append(d)

    bucket_stats = {}
    for b, bd in by_bucket.items():
        if not bd:
            continue
        bucket_stats[b] = {
            "n": len(bd),
            "mean_skew": mean(d.skew for d in bd),
            "mean_fwd_rv": mean(d.fwd_rv for d in bd),
        }

    lines = [
        f"# {underlying} Option Skew Validation",
        "",
        f"Methodology: docs/VOL_SKEW_METHODOLOGY.md"
        + ("" if underlying == "NIFTY" else " + docs/VOL_SKEW_METHODOLOGY_BANKNIFTY_ADDENDUM.md")
        + f". Replayed {len(days)} days ({days[0].date} to {days[-1].date}), "
        f"{len(scored)} scored with a valid skew and full forward window.",
        "",
        "## Skipped days",
        "",
    ]
    if skip_counts:
        for reason, n in sorted(skip_counts.items()):
            lines.append(f"- `{reason}`: {n}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Forward realized vol by skew quintile",
        "",
        "(Q1 = lowest/most-negative skew i.e. calls pricier than puts, "
        "Q5 = highest skew i.e. puts pricing richest.)",
        "",
        "| Bucket | n | Mean skew | Mean fwd 20d RV |",
        "|---|---|---|---|",
    ]
    for b in range(1, NUM_BUCKETS + 1):
        st = bucket_stats.get(b)
        if not st:
            lines.append(f"| Q{b} | 0 | - | - |")
            continue
        lines.append(f"| Q{b} | {st['n']} | {st['mean_skew']:+.2f} | {st['mean_fwd_rv']:.2f} |")

    lines += ["", "## Verdict", ""]
    present = [b for b in range(1, NUM_BUCKETS + 1) if b in bucket_stats]
    monotonic = all(
        bucket_stats[present[i]]["mean_fwd_rv"] <= bucket_stats[present[i + 1]]["mean_fwd_rv"]
        for i in range(len(present) - 1)
    ) if len(present) == NUM_BUCKETS else False

    q1, q5 = bucket_stats.get(1), bucket_stats.get(NUM_BUCKETS)
    if q1 and q5:
        gap = q5["mean_fwd_rv"] - q1["mean_fwd_rv"]
        lines.append(
            f"- Q5 mean fwd RV ({q5['mean_fwd_rv']:.2f}, n={q5['n']}) vs "
            f"Q1 ({q1['mean_fwd_rv']:.2f}, n={q1['n']}): gap = {gap:+.2f} vol points."
        )
        lines.append(f"- Full Q1→Q5 sequence monotonically non-decreasing: {monotonic}.")
        lines.append(
            f"- Per docs/VOL_SKEW_METHODOLOGY.md's pass bar: "
            f"{'PASS' if monotonic and gap > 0 else 'FAIL'} "
            f"(monotonic AND Q5 > Q1 required)."
        )
    lines.append(
        ""
        "Read the gaps above against the sample sizes (`n`) in the table -- this "
        "report presents the numbers, no invented significance test, matching "
        "docs/REGIME_VALIDATION.md and docs/VOL_SPREAD_VALIDATION.md's style."
    )

    return "\n".join(lines)


# ─── Fetch + orchestration (I/O -- cached-file reads, network only on a gap) ─

def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def load_rows_by_date(underlying: str, start: date, end: date,
                       raw_dir: Path) -> dict[date, list[OptionRow]]:
    rows_by_date: dict[date, list[OptionRow]] = {}
    for d in _weekdays(start, end):
        try:
            raw = fetch_raw(d, raw_dir)
        except BhavcopyNotAvailable:
            continue
        rows = parse_raw_zip_for_underlying(raw, underlying)
        if rows:
            rows_by_date[d] = rows
    return rows_by_date


def run_one_underlying(underlying: str, start: date, end: date,
                        raw_dir: Path, out_path: Path) -> None:
    print(f"\n=== {underlying} ===")
    print(f"Loading bhavcopy {start} -> {end} (cached-first, fetches only missing days) ...")
    rows_by_date = load_rows_by_date(underlying, start, end, raw_dir)
    print(f"  {len(rows_by_date)} trading days with {underlying} rows")
    if len(rows_by_date) < RV_WINDOW * 2 + 10:
        print(f"ERROR: only {len(rows_by_date)} days -- too few for a meaningful replay.")
        return

    print("Replaying skew day-by-day (no lookahead) ...")
    days = compute_daily_series(rows_by_date)
    scored = sum(1 for d in days if d.skew is not None and d.fwd_rv is not None)
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
    parser.add_argument("--out-prefix", default="docs/VOL_SKEW_VALIDATION")
    args = parser.parse_args()

    if args.start < CUTOVER_DATE:
        print(f"ERROR: --start must be >= {CUTOVER_DATE} (new bhavcopy format only, "
              f"see docs/VOL_SKEW_METHODOLOGY.md's window section).")
        return 1

    for underlying in args.underlyings.split(","):
        underlying = underlying.strip().upper()
        suffix = "" if underlying == "NIFTY" else f"_{underlying}"
        out_path = Path(f"{args.out_prefix}{suffix}.md")
        run_one_underlying(underlying, args.start, args.end, args.raw_cache_dir, out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
