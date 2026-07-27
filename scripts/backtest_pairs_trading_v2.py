#!/usr/bin/env python3
"""
QuantOS — Pairs Trading v2: Roll-Adjustment + Corporate-Action Fix Backtest
──────────────────────────────────────────────────────────────────────────
Candidate 17, a bug-fix re-run of candidate 12
(scripts/backtest_pairs_trading.py). See
docs/PAIRS_TRADING_V2_METHODOLOGY.md for what changed and why -- in short,
Fable's 2026-07-26 review of candidate 12 found two real construction bugs
(no corporate-action guard, unadjusted futures-roll splicing) and
recommended fixing both before any future pairs-trading candidate. Every
other design choice (universe, cointegration test, walk-forward schedule,
frozen per-fold hedge ratio, entry/exit rules, cost model) is held
IDENTICAL to candidate 12 -- reuses scripts/backtest_pairs_trading.py's
own universe/loading/reporting helpers directly rather than
reimplementing them, so this really is "the same backtest, two bugs
fixed," not a redesign.

Usage:
    python scripts/backtest_pairs_trading_v2.py
    python scripts/backtest_pairs_trading_v2.py --start 2024-01-01 --out docs/PAIRS_TRADING_V2_RESULTS.md
"""

import argparse
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.vrp.bhavcopy import CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR  # noqa: E402
from core.pairs.backtest import run_walk_forward  # noqa: E402
from core.pairs.roll_adjust import build_adjusted_series  # noqa: E402
from core.pairs.universe import (  # noqa: E402
    SECTOR_INDEX_NAMES, build_pairs_universe, build_sector_map, candidate_pairs,
    symbol_sector_counts,
)
from scripts.backtest_pairs_trading import load_stf_price_data, summarize_trades  # noqa: E402

WINDOW_START = CUTOVER_DATE

# Candidate 12's original pooled/per-fold numbers, hardcoded from
# docs/PAIRS_TRADING_RESULTS.md so this script doesn't need to re-run the
# unfixed version to report a comparison -- same "_WEEKLY_CONTROL
# hardcoded" precedent scripts/ablate_momentum_turnover.py already set.
_V1_POOLED = {"n_trades": 4705, "total_net_pnl": -3_819_293, "profit_factor": 0.94, "sharpe_ratio": -0.17}
_V1_FOLD_PF = [1.23, 1.08, 1.29, 1.15, 1.07, 0.91, 0.68, 0.62]


def build_adjusted_price_data(price_data: dict) -> tuple[dict, dict[str, int]]:
    """core/pairs/roll_adjust.py's back-adjustment, run once per symbol
    over its FULL series (point-in-time-safe by construction -- see the
    methodology doc -- so building it once globally and slicing per-fold
    afterward, same as the raw series already was, introduces no
    lookahead). Returns (adjusted_price_data, {symbol: n_unadjusted_seams})
    for symbols with at least one seam left unadjusted (a missing
    same-day next-month price -- disclosed, not silently absorbed)."""
    adjusted: dict = {}
    seam_counts: dict[str, int] = {}
    for symbol, series in price_data.items():
        ordered = sorted(series, key=lambda d: d.trade_date)
        adj_series, n_unadjusted = build_adjusted_series(ordered)
        adjusted[symbol] = adj_series
        if n_unadjusted:
            seam_counts[symbol] = n_unadjusted
    return adjusted, seam_counts


def build_v2_report(folds, universe: dict, candidates: list, seam_counts: dict, out_path: Path) -> str:
    all_trades = [t for fold in folds for t in fold.trades]
    pooled = summarize_trades(all_trades)
    total_corp_action_excluded = sum(f.n_pairs_excluded_corp_action for f in folds)
    total_seams_unadjusted = sum(seam_counts.values())

    lines = [
        "# Pairs Trading v2 Backtest Results (Candidate 17)",
        "",
        f"Methodology: docs/PAIRS_TRADING_V2_METHODOLOGY.md (bug-fix re-run of candidate 12, "
        f"docs/PAIRS_TRADING_METHODOLOGY.md). {len(universe)} sectors qualifying, "
        f"{len(candidates)} same-sector candidate pairs, {len(folds)} walk-forward folds -- "
        f"identical universe/schedule/cost-model to candidate 12.",
        "",
        "## New-fix disclosures",
        "",
        f"- Pairs excluded (either leg, either window) by the corporate-action jump guard, "
        f"summed across all folds: {total_corp_action_excluded}.",
        f"- Symbols with at least one futures-roll seam left UNADJUSTED (missing a same-day "
        f"next-month price at that roll): {len(seam_counts)}, {total_seams_unadjusted} seams total.",
        "",
        "## Universe",
        "",
        "| Sector | Qualifying symbols |",
        "|---|---|",
    ]
    for sector in sorted(universe):
        lines.append(f"| {sector} | {len(universe[sector])} |")

    lines += [
        "",
        "## Per-fold breakdown, v2 vs v1",
        "",
        "| Formation | Trading | Pairs tested | Pairs passed | Corp-action excluded | Trades | Net P&L | PF (v2) | PF (v1) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, fold in enumerate(folds):
        s = summarize_trades(fold.trades)
        pf_str = f"{s['profit_factor']:.2f}" if s['n_trades'] else "-"
        v1_pf = f"{_V1_FOLD_PF[i]:.2f}" if i < len(_V1_FOLD_PF) else "-"
        lines.append(
            f"| {fold.formation_start} to {fold.formation_end} | "
            f"{fold.trading_start} to {fold.trading_end} | {fold.n_pairs_tested} | "
            f"{fold.n_pairs_passed} | {fold.n_pairs_excluded_corp_action} | {s['n_trades']} | "
            f"{s['total_net_pnl']:+.0f} | {pf_str} | {v1_pf} |"
        )

    passed = pooled["n_trades"] > 0 and pooled["profit_factor"] > 1.0 and pooled["sharpe_ratio"] > 0.5
    lines += [
        "",
        "## Pooled result, v2 vs v1 (net of the same F&O futures cost model)",
        "",
        "| | v2 (this run) | v1 (candidate 12, original) |",
        "|---|---|---|",
        f"| Trades | {pooled['n_trades']} | {_V1_POOLED['n_trades']} |",
        f"| Win rate | {pooled['win_rate']*100:.1f}% | - |",
        f"| Total net P&L | Rs {pooled['total_net_pnl']:+,.0f} | Rs {_V1_POOLED['total_net_pnl']:+,.0f} |",
        f"| Profit factor | {pooled['profit_factor']:.2f} | {_V1_POOLED['profit_factor']:.2f} |",
        f"| Sharpe | {pooled['sharpe_ratio']:.2f} | {_V1_POOLED['sharpe_ratio']:.2f} |",
        "",
        "## Verdict",
        "",
    ]
    if pooled["n_trades"] == 0:
        lines.append("**No trades generated** -- see per-fold breakdown for why.")
    else:
        lines.append(
            f"Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), "
            f"computed on the pooled trading-window trades net of costs: **{'PASS' if passed else 'FAIL'}**."
        )
        lines.append(
            "\nBoth fixes are confirmed real construction bugs per Fable's 2026-07-26 review -- "
            "this re-run answers whether fixing them changes the verdict, not whether they were "
            "worth fixing (they were, independent of this outcome). Read the per-fold PF columns "
            "above, especially folds 6-8 (candidate 12's original collapse: PF 0.91, 0.68, 0.62), "
            "before trusting the pooled row alone -- same discipline candidate 12's own report used."
        )

    report = "\n".join(lines) + "\n"
    out_path.write_text(report, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-cache-dir", type=Path, default=DEFAULT_RAW_CACHE_DIR)
    parser.add_argument("--out", default="docs/PAIRS_TRADING_V2_RESULTS.md")
    args = parser.parse_args()

    if args.start < CUTOVER_DATE:
        print(f"ERROR: --start must be >= {CUTOVER_DATE} (new bhavcopy format only).")
        return 1

    print("Fetching NSE sectoral index constituent lists ...")
    sector_map = build_sector_map(SECTOR_INDEX_NAMES)
    for name, symbols in sorted(sector_map.items()):
        print(f"  {name}: {len(symbols)} constituents")

    print(f"\nLoading STF daily near-month prices {args.start} -> {args.end} (cached-first) ...")
    price_data = load_stf_price_data(args.start, args.end, args.raw_cache_dir)

    print("Building roll-adjusted series per symbol (Fix 2) ...")
    price_data, seam_counts = build_adjusted_price_data(price_data)
    if seam_counts:
        print(f"  {len(seam_counts)} symbols had at least one unadjusted roll seam "
              f"({sum(seam_counts.values())} seams total, disclosed in the report)")

    latest_date = max(max(d.trade_date for d in series) for series in price_data.values())
    latest_stf = {sym for sym, series in price_data.items()
                  if any(d.trade_date == latest_date for d in series)}
    print(f"  {len(latest_stf)} symbols with STF data as of {latest_date}")

    universe = build_pairs_universe(sector_map, latest_stf)
    counts = symbol_sector_counts(universe)
    multi_sector = sum(1 for c in counts.values() if c > 1)
    print(f"\n{len(universe)} sectors qualify (>=2 futures-listed symbols): "
          f"{sum(len(v) for v in universe.values())} symbol-sector taggings, "
          f"{multi_sector} symbols tagged under >1 sector")

    candidates = candidate_pairs(universe)
    print(f"{len(candidates)} same-sector candidate pairs")

    print("\nRunning walk-forward formation/trading simulation (roll-adjusted + corp-action guard) ...")
    folds = run_walk_forward(candidates, price_data, args.start, latest_date)
    print(f"{len(folds)} folds")
    for fold in folds:
        print(f"  {fold.formation_start}..{fold.formation_end} -> "
              f"{fold.trading_start}..{fold.trading_end}: "
              f"{fold.n_pairs_passed}/{fold.n_pairs_tested} pairs passed "
              f"({fold.n_pairs_excluded_corp_action} corp-action excluded), "
              f"{len(fold.trades)} trades")

    out_path = Path(args.out)
    build_v2_report(folds, universe, candidates, seam_counts, out_path)
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
