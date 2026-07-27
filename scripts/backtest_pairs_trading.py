#!/usr/bin/env python3
"""
QuantOS — Sector-Cointegrated Stock-Futures Pairs Trading Backtest
────────────────────────────────────────────────────────────────────
Candidate 12. See docs/PAIRS_TRADING_METHODOLOGY.md for every design
choice (universe, cointegration test, walk-forward schedule, entry/exit
rules, cost model), pre-registered BEFORE this script was written.

Data source: core/options/vrp/bhavcopy.py's already-cached raw NSE F&O
bhavcopy zips (data_cache/nse_bhavcopy/raw/), re-parsed here for STF
(single-stock-futures) rows -- same "own raw-zip parser, doesn't touch
VRP's NIFTY-only parsed cache" pattern scripts/validate_vol_skew_signal.py
already established. No live broker/Fyers token needed.

Usage:
    python scripts/backtest_pairs_trading.py
    python scripts/backtest_pairs_trading.py --start 2024-01-01 --out docs/PAIRS_TRADING_RESULTS.md
"""

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backtest.parser import BacktestTrade, _compute_metrics  # noqa: E402
from core.options.vrp.bhavcopy import (  # noqa: E402
    BhavcopyNotAvailable, CUTOVER_DATE, DEFAULT_RAW_CACHE_DIR, fetch_raw,
)
from core.pairs.backtest import FuturesDay, PairTrade, run_walk_forward  # noqa: E402
from core.pairs.universe import (  # noqa: E402
    SECTOR_INDEX_NAMES, build_pairs_universe, build_sector_map, candidate_pairs,
    parse_stf_near_month, symbol_sector_counts,
)

WINDOW_START = CUTOVER_DATE  # == 2024-01-01; new bhavcopy format only, see methodology doc


def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def load_stf_price_data(start: date, end: date, raw_cache_dir: Path) -> dict[str, list[FuturesDay]]:
    """Walks every weekday in [start, end], reading (cache-first) the raw
    bhavcopy and extracting each symbol's near-month STF row. Network only
    on a genuine cache gap -- every date in this window is already cached
    locally from prior VRP/vol-skew sessions."""
    price_data: dict[str, list[FuturesDay]] = defaultdict(list)
    n_days = 0
    for d in _weekdays(start, end):
        try:
            raw = fetch_raw(d, raw_cache_dir)
        except BhavcopyNotAvailable:
            continue
        near_month = parse_stf_near_month(raw, d)
        if not near_month:
            continue
        n_days += 1
        for symbol, row in near_month.items():
            price_data[symbol].append(FuturesDay(
                d, row.close, row.lot_size, row.expiry,
                next_month_close=row.next_month_close,
            ))
    print(f"  loaded {n_days} trading days with STF data, {len(price_data)} distinct symbols")
    return dict(price_data)


def _notional_basis(t: PairTrade) -> float:
    """Combined entry notional across both legs (price * lot_size * lots for
    each leg) -- the basis this report uses for %-return figures
    (core/backtest/parser.py's BacktestTrade is built for a single-symbol
    position; a pair trade has two, so this is an explicit, disclosed
    choice of basis, not something the parser assumes)."""
    return (
        abs(t.entry_price_a) * t.lot_size_a * t.lots_a
        + abs(t.entry_price_b) * t.lot_size_b * t.lots_b
    )


def to_backtest_trades(trades: list[PairTrade]) -> list[BacktestTrade]:
    bt_trades = []
    for i, t in enumerate(trades):
        notional = _notional_basis(t)
        profit_pct = (t.gross_pnl / notional * 100.0) if notional else 0.0
        bars_held = max(1, (t.exit_date - t.entry_date).days)
        bt_trades.append(BacktestTrade(
            trade_num=i + 1, direction="Long" if t.direction_a == "BUY" else "Short",
            qty=1, entry_date=datetime.combine(t.entry_date, datetime.min.time()), entry_price=notional,
            exit_date=datetime.combine(t.exit_date, datetime.min.time()), exit_price=notional + t.gross_pnl,
            profit=t.gross_pnl, profit_pct=profit_pct, cum_profit=0.0,
            bars_held=bars_held, costs=t.cost,
        ))
    cum = 0.0
    for bt in sorted(bt_trades, key=lambda x: x.entry_date):
        cum += bt.profit
        bt.cum_profit = cum
    return bt_trades


def summarize_trades(trades: list[PairTrade]) -> dict:
    bt_trades = to_backtest_trades(trades)
    metrics = _compute_metrics(bt_trades)
    return {
        "n_trades": metrics.total_trades,
        "win_rate": metrics.win_rate,
        "total_net_pnl": sum(t.net_pnl for t in trades),
        "profit_factor": metrics.profit_factor,
        "sharpe_ratio": metrics.sharpe_ratio,
    }


def build_report(
    folds, universe: dict, candidates: list, out_path: Path,
) -> str:
    all_trades = [t for fold in folds for t in fold.trades]
    pooled = summarize_trades(all_trades)

    lines = [
        "# Pairs Trading Backtest Results (Candidate 12)",
        "",
        f"Methodology: docs/PAIRS_TRADING_METHODOLOGY.md. "
        f"{len(universe)} sectors qualifying (>=2 futures-listed symbols each), "
        f"{len(candidates)} same-sector candidate pairs, {len(folds)} walk-forward folds.",
        "",
        "## Universe",
        "",
        "| Sector | Qualifying symbols |",
        "|---|---|",
    ]
    for sector in sorted(universe):
        lines.append(f"| {sector} | {len(universe[sector])} |")

    lines += ["", "## Per-fold breakdown", "", "| Formation | Trading | Pairs tested | Pairs passed | Trades | Net P&L | Profit factor |", "|---|---|---|---|---|---|---|"]
    for fold in folds:
        s = summarize_trades(fold.trades)
        pf_str = f"{s['profit_factor']:.2f}" if s['n_trades'] else "-"
        lines.append(
            f"| {fold.formation_start} to {fold.formation_end} | "
            f"{fold.trading_start} to {fold.trading_end} | {fold.n_pairs_tested} | "
            f"{fold.n_pairs_passed} | {s['n_trades']} | {s['total_net_pnl']:+.0f} | "
            f"{pf_str} |"
        )

    lines += [
        "",
        "## Pooled result (all folds, net of the F&O futures cost model)",
        "",
        f"- Trades: {pooled['n_trades']}",
        f"- Win rate: {pooled['win_rate']*100:.1f}%",
        f"- Total net P&L: Rs {pooled['total_net_pnl']:+,.0f}",
        f"- Profit factor: {pooled['profit_factor']:.2f}",
        f"- Sharpe (core/backtest/parser.py convention, %-return basis = combined pair notional): "
        f"{pooled['sharpe_ratio']:.2f}",
        "",
        "## Verdict",
        "",
    ]
    if pooled["n_trades"] == 0:
        lines.append("**No trades generated** -- see per-fold breakdown for why (likely 0 pairs passing cointegration).")
    else:
        passed = pooled["profit_factor"] > 1.0 and pooled["sharpe_ratio"] > 0.5
        lines.append(
            f"Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), "
            f"computed on the pooled trading-window trades net of costs: "
            f"**{'PASS' if passed else 'FAIL'}**."
        )
        lines.append(
            ""
            "Per the methodology doc's own disclosed limitation: no multiple-testing "
            "correction was applied to the p<0.05 cointegration threshold, and this is "
            "only ~"  + str(len(folds)) + " walk-forward folds -- read the per-fold table "
            "above, not just the pooled row, before trusting this."
        )

    report = "\n".join(lines) + "\n"
    out_path.write_text(report, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--raw-cache-dir", type=Path, default=DEFAULT_RAW_CACHE_DIR)
    parser.add_argument("--out", default="docs/PAIRS_TRADING_RESULTS.md")
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

    print("\nRunning walk-forward formation/trading simulation ...")
    folds = run_walk_forward(candidates, price_data, args.start, latest_date)
    print(f"{len(folds)} folds")
    for fold in folds:
        print(f"  {fold.formation_start}..{fold.formation_end} -> "
              f"{fold.trading_start}..{fold.trading_end}: "
              f"{fold.n_pairs_passed}/{fold.n_pairs_tested} pairs passed, "
              f"{len(fold.trades)} trades")

    out_path = Path(args.out)
    build_report(folds, universe, candidates, out_path)
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
