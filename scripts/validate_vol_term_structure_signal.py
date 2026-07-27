#!/usr/bin/env python3
"""
QuantOS — Vol-Conditioning Signal Validation: ATM IV Term Structure (NIFTY + BankNifty)
─────────────────────────────────────────────────────────────────────────────────────────
4th vol-conditioning attempt after three failures (core/regime/classifier.py's
VIX-level bands, docs/VOL_SPREAD_VALIDATION.md's IV-minus-RV spread,
docs/VOL_SKEW_VALIDATION.md's option skew). See
docs/VOL_TERM_STRUCTURE_METHODOLOGY.md for every design choice (expiry-pair
selection, strike selection, spread construction, bucketing, pass/fail bar),
fixed BEFORE this script was written.

Method
──────
For each trading day with cached NSE bhavcopy data, per underlying:
  - Spot = that day's UndrlygPric (shared across every row that day).
  - Front-month / back-month = the 1st / 2nd nearest listed expiries with
    >=3 calendar days to trade date.
  - ATM strike (each expiry independently) = nearest strike to spot.
  - ATM_IV for one expiry = mean(call IV, put IV) at that strike, via
    core/options/greeks.py's Black-Scholes bisection solver — days/expiries
    are skipped (not fed a fallback constant) if either leg would hit
    implied_volatility()'s intrinsic-value/DTE<=0 fallback path.
  - Spread_t = ATM_IV_front,t − ATM_IV_back,t (positive = backwardation).
Then, using the (now-known) future spot series:
  - RV_trailing_20d_t / RV_fwd_20d_t = annualized stdev of daily log
    returns over the prior/next 20 sessions.
Days are bucketed into quintiles of Spread_t (data-driven cutpoints from
the full sample) and each bucket's mean forward RV is reported.

Reuses scripts/validate_vol_skew_signal.py's OptionRow / raw-zip parser /
load_rows_by_date (same bhavcopy fetch, same underlying-filtered parse) and
scripts/validate_vol_spread_signal.py's quintile_cutoffs/assign_bucket/
_annualized_rv — no reimplementation of either.

This is deliberately NOT connected to VRP's trade data or the
Iron-Condor-mislabeled-straddle CSV — see
docs/VOL_TERM_STRUCTURE_METHODOLOGY.md's "mandatory sequencing" section.

Usage
─────
    python scripts/validate_vol_term_structure_signal.py
    python scripts/validate_vol_term_structure_signal.py --underlyings NIFTY,BANKNIFTY --out-prefix docs/VOL_TERM_STRUCTURE_VALIDATION

No live broker connection needed — reads the already-cached raw bhavcopy
zips, network only on a cache gap.
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.greeks import DEFAULT_RISK_FREE_RATE, implied_volatility  # noqa: E402
from core.options.models import OptionType  # noqa: E402
from core.options.vrp.bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR  # noqa: E402
from scripts.validate_vol_skew_signal import (  # noqa: E402
    OptionRow, _would_hit_iv_fallback, load_rows_by_date,
)
from scripts.validate_vol_spread_signal import (  # noqa: E402
    RV_WINDOW, NUM_BUCKETS, TRADING_DAYS_PER_YEAR,
    _annualized_rv, assign_bucket, quintile_cutoffs,
)

MIN_DTE = 3                        # calendar days, same guard as VOL_SKEW
MONEYNESS_TOLERANCE_PCT = 0.015     # ATM strike must be within 1.5% of spot

WINDOW_START = date(2024, 1, 1)    # == CUTOVER_DATE


# ─── Pure per-day term-structure logic (no I/O — unit-testable) ────────────

def select_expiry_pair(expiries: list[date], trade_date: date,
                        min_dte: int = MIN_DTE) -> Optional[tuple[date, date]]:
    """(front, back) = the 1st and 2nd nearest listed expiries with
    >=min_dte calendar days remaining, or None if fewer than 2 qualify."""
    candidates = sorted(e for e in expiries if (e - trade_date).days >= min_dte)
    if len(candidates) < 2:
        return None
    return candidates[0], candidates[1]


def select_atm_row(rows: list[OptionRow], spot: float, option_type: OptionType) -> Optional[OptionRow]:
    """Nearest strike to spot (ties broken toward the lower strike, so the
    rule is deterministic). Returns None if no candidate exists at all."""
    candidates = [r for r in rows if r.option_type == option_type]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (abs(r.strike - spot), r.strike))
    return candidates[0]


def _within_atm_tolerance(row: OptionRow, spot: float) -> bool:
    return abs(row.strike - spot) / spot <= MONEYNESS_TOLERANCE_PCT


def _compute_atm_iv_for_expiry(
    expiry_rows: list[OptionRow], spot: float, expiry: date, trade_date: date,
) -> tuple[Optional[float], str]:
    """mean(call IV, put IV) at the ATM strike for one expiry, or
    (None, skip_reason) if the ATM strike/leg data isn't usable."""
    call_row = select_atm_row(expiry_rows, spot, OptionType.CALL)
    put_row = select_atm_row(expiry_rows, spot, OptionType.PUT)
    if call_row is None or put_row is None:
        return None, "no_atm_candidate"
    if not _within_atm_tolerance(call_row, spot) or not _within_atm_tolerance(put_row, spot):
        return None, "moneyness_tolerance"

    dte = (expiry - trade_date).days
    if _would_hit_iv_fallback(call_row.settle_price, spot, call_row.strike, dte, OptionType.CALL):
        return None, "iv_fallback_call"
    if _would_hit_iv_fallback(put_row.settle_price, spot, put_row.strike, dte, OptionType.PUT):
        return None, "iv_fallback_put"

    call_iv = implied_volatility(
        market_price=call_row.settle_price, spot=spot, strike=call_row.strike,
        days_to_expiry=dte, option_type=OptionType.CALL, risk_free_rate=DEFAULT_RISK_FREE_RATE,
    )
    put_iv = implied_volatility(
        market_price=put_row.settle_price, spot=spot, strike=put_row.strike,
        days_to_expiry=dte, option_type=OptionType.PUT, risk_free_rate=DEFAULT_RISK_FREE_RATE,
    )
    return (call_iv + put_iv) / 2.0, ""


def compute_term_structure_for_date(
    rows: list[OptionRow], trade_date: date,
) -> tuple[Optional[float], Optional[float], str]:
    """Returns (spot, spread, skip_reason). skip_reason == "" on success."""
    if not rows:
        return None, None, "no_rows"
    spot = rows[0].underlying_close
    if spot is None:
        return None, None, "no_underlying_close"

    pair = select_expiry_pair(sorted(set(r.expiry for r in rows)), trade_date)
    if pair is None:
        return spot, None, "insufficient_expiries"
    front, back = pair

    front_rows = [r for r in rows if r.expiry == front]
    back_rows = [r for r in rows if r.expiry == back]

    front_iv, front_reason = _compute_atm_iv_for_expiry(front_rows, spot, front, trade_date)
    if front_iv is None:
        return spot, None, f"front_{front_reason}"
    back_iv, back_reason = _compute_atm_iv_for_expiry(back_rows, spot, back, trade_date)
    if back_iv is None:
        return spot, None, f"back_{back_reason}"

    return spot, front_iv - back_iv, ""


@dataclass
class TermStructureDay:
    date:         date
    spot:         float
    spread:       Optional[float]
    skip_reason:  str
    rv_trailing:  Optional[float] = None
    fwd_rv:       Optional[float] = None


def compute_daily_series(rows_by_date: dict) -> list[TermStructureDay]:
    """Walk every date with a usable spot close, in order. No lookahead:
    spread_t and rv_trailing_t use only data through t; fwd_rv_t uses the
    (now-known) future purely as the outcome being scored."""
    dates = sorted(d for d in rows_by_date
                    if rows_by_date[d] and rows_by_date[d][0].underlying_close is not None)
    closes = [rows_by_date[d][0].underlying_close for d in dates]

    days: list[TermStructureDay] = []
    for i in range(RV_WINDOW, len(dates)):
        d = dates[i]
        spot, spread, reason = compute_term_structure_for_date(rows_by_date[d], d)
        rv_trailing = _annualized_rv(closes[i - RV_WINDOW: i + 1])
        fwd_rv = None
        if i + RV_WINDOW < len(dates):
            fwd_rv = _annualized_rv(closes[i: i + RV_WINDOW + 1])
        days.append(TermStructureDay(
            date=d, spot=spot if spot is not None else closes[i], spread=spread,
            skip_reason=reason, rv_trailing=rv_trailing, fwd_rv=fwd_rv,
        ))
    return days


# ─── Report ─────────────────────────────────────────────────────────────────

def summarize(days: list[TermStructureDay], underlying: str) -> str:
    scored = [d for d in days if d.spread is not None and d.fwd_rv is not None]
    skip_counts: dict = {}
    for d in days:
        if d.spread is None:
            skip_counts[d.skip_reason] = skip_counts.get(d.skip_reason, 0) + 1

    if not scored:
        return f"# {underlying} ATM IV Term Structure Validation\n\n**No days scored.**\n"

    cutoffs = quintile_cutoffs([d.spread for d in scored])
    by_bucket: dict = {b: [] for b in range(1, NUM_BUCKETS + 1)}
    for d in scored:
        by_bucket[assign_bucket(d.spread, cutoffs)].append(d)

    bucket_stats = {}
    for b, bd in by_bucket.items():
        if not bd:
            continue
        bucket_stats[b] = {
            "n": len(bd),
            "mean_spread": mean(d.spread for d in bd),
            "mean_fwd_rv": mean(d.fwd_rv for d in bd),
        }

    lines = [
        f"# {underlying} ATM IV Term Structure Validation",
        "",
        f"Methodology: docs/VOL_TERM_STRUCTURE_METHODOLOGY.md. Replayed "
        f"{len(days)} days ({days[0].date} to {days[-1].date}), "
        f"{len(scored)} scored with a valid spread and full forward window.",
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
        "## Forward realized vol by term-structure-spread quintile",
        "",
        "(Q1 = most negative spread i.e. deepest contango/calm shape, "
        "Q5 = most positive spread i.e. deepest backwardation/stress shape.)",
        "",
        "| Bucket | n | Mean spread | Mean fwd 20d RV |",
        "|---|---|---|---|",
    ]
    for b in range(1, NUM_BUCKETS + 1):
        st = bucket_stats.get(b)
        if not st:
            lines.append(f"| Q{b} | 0 | - | - |")
            continue
        lines.append(f"| Q{b} | {st['n']} | {st['mean_spread']:+.2f} | {st['mean_fwd_rv']:.2f} |")

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
            f"- Per docs/VOL_TERM_STRUCTURE_METHODOLOGY.md's pass bar: "
            f"{'PASS' if monotonic and gap > 0 else 'FAIL'} "
            f"(monotonic AND Q5 > Q1 required)."
        )
    lines.append(
        ""
        "Read the gaps above against the sample sizes (`n`) in the table -- this "
        "report presents the numbers, no invented significance test, matching "
        "docs/REGIME_VALIDATION.md and every prior vol-conditioning report."
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

    print("Replaying term structure day-by-day (no lookahead) ...")
    days = compute_daily_series(rows_by_date)
    scored = sum(1 for d in days if d.spread is not None and d.fwd_rv is not None)
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
    parser.add_argument("--out-prefix", default="docs/VOL_TERM_STRUCTURE_VALIDATION")
    args = parser.parse_args()

    if args.start < CUTOVER_DATE:
        print(f"ERROR: --start must be >= {CUTOVER_DATE} (new bhavcopy format only, "
              f"see docs/VOL_TERM_STRUCTURE_METHODOLOGY.md's data-source section).")
        return 1

    for underlying in args.underlyings.split(","):
        underlying = underlying.strip().upper()
        suffix = "" if underlying == "NIFTY" else f"_{underlying}"
        out_path = Path(f"{args.out_prefix}{suffix}.md")
        run_one_underlying(underlying, args.start, args.end, args.raw_cache_dir, out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
