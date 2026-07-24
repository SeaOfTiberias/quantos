#!/usr/bin/env python3
"""
QuantOS — Momentum Turnover Ablation
────────────────────────────────────────────────────────────────────────────
Methodology pre-committed in docs/MOMENTUM_TURNOVER_ABLATION_METHODOLOGY.md
before this ran. Isolates rebalance FREQUENCY as the one variable behind
S8-3's Sharpe/CAGR gap to Nifty Alpha 50 — same ranking function
(core/rotation/ranker.py, unchanged), same point-in-time universe, same
cost model, same capital/window as docs/S8_3_EQUITY_CURVE_RESULTS.md
(which serves as the weekly-cadence control, not re-run here). The only
change: rebalance on the last NIFTY trading day of each calendar QUARTER
instead of each week.

Usage:
    python scripts/ablate_momentum_turnover.py
    python scripts/ablate_momentum_turnover.py --years 3 --capital 1000000 --position-size 50000
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.regime.fetcher import ALPHA50_SYMBOL, NIFTY_SYMBOL  # noqa: E402
from core.rotation.equity_curve import (  # noqa: E402
    compute_alpha, simulate_index_buy_and_hold, simulate_portfolio,
)
from core.rotation.nifty500_reconstitution import build_point_in_time_universe  # noqa: E402
from core.rotation.ranker import LOOKBACK_DAYS, TOP_N, SymbolSeries, build_symbol_series  # noqa: E402
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402


# ─── The one thing this script changes vs backtest_equity_curve.py's weekly cadence ──

def quarterly_rebalance_dates(nifty_candles: list[OHLCV], warmup_days: int = LOOKBACK_DAYS) -> list[datetime]:
    """Last NIFTY trading day of each calendar quarter, after enough warmup
    for the 52-week-high window — same "last trading day of the period"
    logic as scripts/backtest_rs_momentum.py's rebalance_dates(), grouped
    by (year, quarter) instead of (year, ISO week)."""
    if len(nifty_candles) <= warmup_days:
        return []
    candles = nifty_candles[warmup_days:]
    dates = []
    for i, c in enumerate(candles):
        q = (c.timestamp.year, (c.timestamp.month - 1) // 3)
        is_last_of_quarter = (
            i == len(candles) - 1
            or ((candles[i + 1].timestamp.year, (candles[i + 1].timestamp.month - 1) // 3) != q)
        )
        if is_last_of_quarter:
            dates.append(c.timestamp)
    return dates


# ─── Report ─────────────────────────────────────────────────────────────────────

def _pct_gap_closed(weekly_val: float, quarterly_val: float, benchmark_val: float) -> str:
    """% of the gap-to-benchmark closed by the quarterly variant vs weekly.
    Positive = closed some of the gap, negative = widened it."""
    weekly_gap = benchmark_val - weekly_val
    if abs(weekly_gap) < 1e-9:
        return "n/a (no weekly gap to close)"
    quarterly_gap = benchmark_val - quarterly_val
    closed_pct = (1 - quarterly_gap / weekly_gap) * 100
    return f"{closed_pct:+.0f}%"


def summarize(weekly, quarterly, nifty_benchmark, nifty_alpha_q, alpha50_benchmark, alpha50_alpha_q,
              nifty_alpha_w: dict, alpha50_alpha_w: dict,
              top_n: int, capital: float, position_size: float, rebal_count_q: int) -> str:
    lines = [
        "# Momentum Turnover Ablation — Results",
        "",
        f"Methodology: docs/MOMENTUM_TURNOVER_ABLATION_METHODOLOGY.md. Weekly baseline is "
        f"docs/S8_3_EQUITY_CURVE_RESULTS.md's existing run (not re-run here — same "
        f"parameters, so it's a valid control). Quarterly variant: {rebal_count_q} rebalance "
        f"dates, same ₹{capital:,.0f} capital, ₹{position_size:,.0f}/position, top {top_n}, "
        f"same point-in-time Nifty 500 universe, same DELIVERY_COST_MODEL, exit_rule=rank_only "
        f"in both.",
        "",
        "## Weekly (control, from S8_3_EQUITY_CURVE_RESULTS.md)",
        "",
        f"- Total return: {weekly['total_return_pct']:.1f}%",
        f"- CAGR: {weekly['cagr_pct']:.1f}%",
        f"- Sharpe: {weekly['sharpe']:.2f}",
        f"- Max drawdown: {weekly['max_drawdown_pct']:.1f}%",
        f"- Trades: {weekly['trades']}",
        "",
        "## Quarterly (this ablation)",
        "",
        f"- Total return: {quarterly.total_return_pct:.1f}%",
        f"- CAGR: {quarterly.cagr_pct:.1f}%",
        f"- Sharpe: {quarterly.sharpe:.2f}",
        f"- Max drawdown: {quarterly.max_drawdown_pct:.1f}%",
        f"- Trades: {len(quarterly.trades)}",
        "",
        "## Gap closed vs Nifty Alpha 50 (the sharper peer bar)",
        "",
        f"- Weekly: CAGR {weekly['cagr_pct']:.1f}% vs Alpha 50 {alpha50_benchmark.cagr_pct:.1f}% "
        f"(alpha {alpha50_alpha_w['alpha_cagr_pct']:+.1f}pp)",
        f"- Quarterly: CAGR {quarterly.cagr_pct:.1f}% vs Alpha 50 {alpha50_benchmark.cagr_pct:.1f}% "
        f"(alpha {alpha50_alpha_q['alpha_cagr_pct']:+.1f}pp)",
        f"- CAGR gap closed by switching to quarterly: "
        f"{_pct_gap_closed(weekly['cagr_pct'], quarterly.cagr_pct, alpha50_benchmark.cagr_pct)}",
        f"- Sharpe gap closed by switching to quarterly: "
        f"{_pct_gap_closed(weekly['sharpe'], quarterly.sharpe, alpha50_benchmark.sharpe)}",
        "",
        "## Gap closed vs Nifty 500",
        "",
        f"- Weekly alpha (total return): {nifty_alpha_w['alpha_total_return_pct']:+.1f}pp",
        f"- Quarterly alpha (total return): {nifty_alpha_q['alpha_total_return_pct']:+.1f}pp",
        "",
        "## Benchmarks (same window/capital as both runs)",
        "",
        f"- Nifty 500: final ₹{nifty_benchmark.final_equity:,.0f}, CAGR {nifty_benchmark.cagr_pct:.1f}%, "
        f"Sharpe {nifty_benchmark.sharpe:.2f}",
        f"- Nifty Alpha 50: final ₹{alpha50_benchmark.final_equity:,.0f}, CAGR {alpha50_benchmark.cagr_pct:.1f}%, "
        f"Sharpe {alpha50_benchmark.sharpe:.2f}",
        "",
        "## Interpretation",
        "",
        "This is a diagnostic ablation, not a strategy validation — see the methodology "
        "doc's framing. A large gap closure means turnover/exit-tightness explains most of "
        "the weekly wrapper's underperformance vs Alpha 50, and a properly pre-registered "
        "lower-turnover momentum candidate is worth building. A small or negative gap "
        "closure rules turnover out as the primary explanation.",
    ]
    return "\n".join(lines)


# ─── Orchestration ───────────────────────────────────────────────────────────────

# Weekly control numbers, hardcoded from docs/S8_3_EQUITY_CURVE_RESULTS.md so this
# script doesn't need to re-fetch/re-run the weekly variant to report a comparison.
_WEEKLY_CONTROL = {
    "total_return_pct": 12.8, "cagr_pct": 4.0, "sharpe": 0.34,
    "max_drawdown_pct": 26.2, "trades": 2034,
}


async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 400)
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY daily candles {from_date.date()} -> {to_date.date()} ...")
    nifty_candles = await fetch_chunked_daily(broker, NIFTY_SYMBOL, from_date, to_date, sem)
    print(f"  {len(nifty_candles)} candles")

    print(f"Fetching NIFTY ALPHA 50 daily candles {from_date.date()} -> {to_date.date()} ...")
    alpha50_candles = await fetch_chunked_daily(broker, ALPHA50_SYMBOL, from_date, to_date, sem)
    print(f"  {len(alpha50_candles)} candles")

    current_universe = frozenset(
        ln.strip() for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#"))
    universe_snapshots = build_point_in_time_universe(current_universe)
    fetch_universe = sorted(frozenset().union(*(s.symbols for s in universe_snapshots)))
    print(f"Fetching {len(fetch_universe)} universe symbols (throttled 2-concurrent) ...")
    symbol_series: dict[str, SymbolSeries] = {}
    for n, symbol in enumerate(fetch_universe, 1):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(candles) >= LOOKBACK_DAYS:
            symbol_series[symbol] = build_symbol_series(candles)
        if n % 50 == 0:
            print(f"  {n}/{len(fetch_universe)} symbols fetched, {len(symbol_series)} usable so far")
    print(f"  {len(symbol_series)}/{len(fetch_universe)} symbols have enough history to ever be ranked")

    if len(nifty_candles) <= LOOKBACK_DAYS:
        print("ERROR: not enough NIFTY history for even one rebalance after warmup.")
        return 1

    warmed_up_candles = nifty_candles[LOOKBACK_DAYS:]
    daily_dates = [c.timestamp for c in warmed_up_candles]
    rebal_dates_q = set(quarterly_rebalance_dates(nifty_candles))
    print(f"  {len(daily_dates)} trading days, {len(rebal_dates_q)} quarterly rebalance dates")

    print(f"Simulating QUARTERLY portfolio (top {args.top_n}, ₹{args.capital:,.0f} capital, "
          f"₹{args.position_size:,.0f}/position) ...")
    quarterly = simulate_portfolio(
        daily_dates, rebal_dates_q, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=DELIVERY_COST_MODEL, exit_rule="rank_only",
        universe_snapshots=universe_snapshots,
    )
    print(f"  final equity ₹{quarterly.final_equity:,.0f}  CAGR {quarterly.cagr_pct:.1f}%  "
          f"Sharpe {quarterly.sharpe:.2f}  max DD {quarterly.max_drawdown_pct:.1f}%")

    nifty_closes = [(c.timestamp, c.close) for c in warmed_up_candles]
    nifty_benchmark = simulate_index_buy_and_hold(nifty_closes, initial_capital=args.capital)
    nifty_alpha_q = compute_alpha(quarterly, nifty_benchmark)

    window_start = daily_dates[0]
    alpha50_closes = [(c.timestamp, c.close) for c in alpha50_candles if c.timestamp >= window_start]
    alpha50_benchmark = simulate_index_buy_and_hold(alpha50_closes, initial_capital=args.capital)
    alpha50_alpha_q = compute_alpha(quarterly, alpha50_benchmark)

    # Weekly control's alpha vs the SAME benchmark curves (fair comparison —
    # same window/capital benchmarks, just the strategy side differs).
    class _WeeklyStub:
        total_return_pct = _WEEKLY_CONTROL["total_return_pct"]
        cagr_pct = _WEEKLY_CONTROL["cagr_pct"]
    nifty_alpha_w = compute_alpha(_WeeklyStub(), nifty_benchmark)
    alpha50_alpha_w = compute_alpha(_WeeklyStub(), alpha50_benchmark)

    report = summarize(_WEEKLY_CONTROL, quarterly, nifty_benchmark, nifty_alpha_q,
                        alpha50_benchmark, alpha50_alpha_q, nifty_alpha_w, alpha50_alpha_w,
                        args.top_n, args.capital, args.position_size, len(rebal_dates_q))
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--capital", type=float, default=1_000_000.0)
    parser.add_argument("--position-size", type=float, default=50_000.0)
    parser.add_argument("--out", default="docs/MOMENTUM_TURNOVER_ABLATION_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
