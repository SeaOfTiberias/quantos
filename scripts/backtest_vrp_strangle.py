#!/usr/bin/env python3
"""
QuantOS — VRP Phase 2+3+4: Short-Strangle Backtest Driver
──────────────────────────────────────────────────────────
Runs docs/VRP_METHODOLOGY.md's pre-committed rule set against the Phase 1
bhavcopy cache: reconstructs entry cycles + strikes (Phase 2,
core/options/vrp/strikes.py), computes pooled per-trade P&L from real
recorded prices (Phase 3, core/options/vrp/simulator.py), then applies real,
time-varying NSE transaction costs (Phase 4, core/options/vrp/costs.py) to
get a NET result. Reports GROSS and NET side by side -- the gap between them
is itself the finding, not just the final number.

Usage:
    python scripts/backtest_vrp_strangle.py
    python scripts/backtest_vrp_strangle.py --out docs/VRP_BACKTEST_RESULTS.md
"""

import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.options.vrp.bhavcopy import DEFAULT_PARSED_CACHE_DIR, load_cached_range  # noqa: E402
from core.options.vrp.costs import compute_net_stats  # noqa: E402
from core.options.vrp.simulator import compute_stats, simulate  # noqa: E402
from core.options.vrp.strikes import build_entry_cycles, select_strangle  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2023, 7, 24))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 22))
    ap.add_argument("--parsed-cache-dir", type=Path, default=DEFAULT_PARSED_CACHE_DIR)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    print(f"Loading cached NIFTY options {args.start} .. {args.end} ...")
    rows_by_date = defaultdict(list)
    for r in load_cached_range(args.start, args.end, args.parsed_cache_dir):
        rows_by_date[r.trade_date].append(r)
    print(f"{len(rows_by_date)} cached trading days, {sum(len(v) for v in rows_by_date.values())} rows")

    expiries_by_date = {d: {r.expiry for r in rs} for d, rs in rows_by_date.items()}
    cycles = build_entry_cycles(expiries_by_date)
    print(f"{len(cycles)} entry cycles reconstructed")

    selections = []
    skipped = 0
    for c in cycles:
        sel = select_strangle(rows_by_date.get(c.entry_date, []), c.entry_date, c.expiry_date, c.dte)
        if sel is None:
            skipped += 1
            continue
        selections.append(sel)
    print(f"{len(selections)} strangles selected, {skipped} cycles skipped (no valid strikes/spot)")

    trades = simulate(selections, args.parsed_cache_dir)
    gross = compute_stats(trades)
    net = compute_net_stats(trades)

    fallback_calls = sum(1 for t in trades if t.call_method == "fallback_pct_otm")
    fallback_puts = sum(1 for t in trades if t.put_method == "fallback_pct_otm")

    def _print_block(title: str, stats) -> None:
        print(f"\n-- VRP Short Strangle -- {title} -----------------")
        print(f"Trades                 : {stats.n_trades} ({stats.n_missing_settlement} missing settlement data)")
        print(f"Win rate               : {stats.win_rate:.1%}")
        print(f"Avg P&L (% of credit)  : {stats.avg_pnl_pct:+.2f}%")
        print(f"Profit factor          : {stats.profit_factor:.3f}")
        print(f"Sharpe (annualized)    : {stats.sharpe:.3f}")
        print(f"Max drawdown (pct pts) : {stats.max_drawdown_pct:.2f}")

    _print_block("GROSS, pre-cost", gross)
    _print_block("NET, post-cost", net)
    print(f"\nDelta-fallback strikes : {fallback_calls} calls / {fallback_puts} puts of {len(trades)}")

    if args.out:
        _write_report(args.out, gross, net, args.start, args.end, fallback_calls, fallback_puts, len(trades))
        print(f"\nWrote {args.out}")

    return 0


def _stats_lines(stats) -> list:
    return [
        f"- Trades: {stats.n_trades} ({stats.n_missing_settlement} cycles skipped -- missing settlement data)",
        f"- Win rate: {stats.win_rate:.1%}",
        f"- Avg P&L (pct of credit collected): {stats.avg_pnl_pct:+.2f}%",
        f"- Profit factor: {stats.profit_factor:.3f}",
        f"- Sharpe (annualized, weekly cycles): {stats.sharpe:.3f}",
        f"- Max drawdown (cumulative pct-of-credit points): {stats.max_drawdown_pct:.2f}",
    ]


def _write_report(out: Path, gross, net, start: date, end: date, fallback_calls: int,
                   fallback_puts: int, n_trades: int) -> None:
    lines = [
        "# VRP Short Strangle Backtest -- Gross vs Net Result",
        "",
        f"Methodology: docs/VRP_METHODOLOGY.md (pre-committed 2026-07-23, before this ran). "
        f"Window: {start} to {end}.",
        "",
        "## GROSS (pre-cost)",
        "",
        *_stats_lines(gross),
        "",
        "## NET (post-cost, real time-varying NSE F&O charges -- see core/options/vrp/costs.py)",
        "",
        *_stats_lines(net),
        "",
        f"- Strikes that fell back to fixed 2% OTM (delta unreliable that day): "
        f"{fallback_calls} calls / {fallback_puts} puts of {n_trades} trades",
        "",
        "## Caveats",
        "",
        "- Entry premium = real recorded close on the entry date. Exit value = intrinsic "
        "payout (max(0, settlement - strike) / max(0, strike - settlement)) computed from "
        "the underlying's real recorded final settlement value on the contract's own expiry "
        "date -- NOT read directly off that contract's own settle_price row, which NSE "
        "overwrites with the shared underlying settlement value on expiry day itself (see "
        "core/options/vrp/simulator.py's module docstring for the full gotcha).",
        "- Spot/forward estimate used for STRIKE SELECTION (not for P&L) is a put-call-parity "
        "synthesis from that day's own option prices (see core/options/vrp/strikes.py), not a "
        "separately-fetched index quote.",
        "- NET costs are real, sourced, time-varying NSE F&O charges (brokerage, STT on sell "
        "and on exercise, exchange transaction charge, SEBI turnover fee, GST) -- see "
        "core/options/vrp/costs.py's module docstring for exact rates, effective dates, and "
        "sources. Two approximations flagged there explicitly: the exchange transaction charge "
        "uses the current uniform rate across the whole window (pre-2024-10-01 NSE used a "
        "volume-tiered slab system with no single equivalent number), and lot size is not "
        "modeled at all -- checked and confirmed immaterial for this strategy's premium range "
        "(max 699.9 points seen across all trades; the brokerage flat cap only binds above "
        "~2,667 points at NIFTY's smallest lot size this window ever used).",
        "- No margin/cost-of-carry modeled -- a short strangle ties up margin for its whole "
        "life, and that opportunity cost isn't in either number above.",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
