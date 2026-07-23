#!/usr/bin/env python3
"""
QuantOS — S8-3 Rotation: Real Capital-Tracked Equity Curve (orchestration)
────────────────────────────────────────────────────────────────────────────
docs/S8_3_BACKTEST_RESULTS.md's headline numbers (profit factor 1.18, Sharpe
0.63) are pooled per-trade statistics — see core/rotation/equity_curve.py's
docstring for why those can't answer "what does my real ₹10L become." This
script runs that module against real Nifty 500 history to answer exactly
that, plus alpha vs two buy-and-hold benchmarks over the identical
window/capital: Nifty 500 (the strategy's own trading universe) and Nifty
Alpha 50 (a closer peer bar, since it's itself a momentum/alpha strategy
index rather than a broad-market cap-weighted one).

Baseline rank-dropout exit only (exit_rule="rank_only") — the stop_loss and
ema_cross variants core/rotation/equity_curve.py also supports are out of
scope for this run by explicit decision (2026-07-21): the ask was narrowed
to "what does PF/Sharpe mean for ₹10L" + "alpha vs Nifty", not an exit-rule
comparison.

Fetch pattern, universe, cost model, and rebalance-date logic are all reused
from scripts/backtest_rs_momentum.py (same broker calls, same
agent/universe_nifty500.txt, same DELIVERY_COST_MODEL) so this can't
silently diverge from what S8-3 was actually backtested/live-traded with.

Usage:
    python scripts/backtest_equity_curve.py
    python scripts/backtest_equity_curve.py --years 3 --capital 1000000 --position-size 50000
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.regime.fetcher import ALPHA50_SYMBOL, NIFTY_SYMBOL  # noqa: E402
from core.rotation.equity_curve import (  # noqa: E402
    compute_alpha, simulate_index_buy_and_hold, simulate_portfolio,
)
from core.rotation.nifty500_reconstitution import build_point_in_time_universe  # noqa: E402
from core.rotation.ranker import LOOKBACK_DAYS, TOP_N, SymbolSeries, build_symbol_series  # noqa: E402
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL, rebalance_dates  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402


# ─── Report ─────────────────────────────────────────────────────────────────────

def _benchmark_section(title: str, benchmark, alpha) -> list:
    return [
        f"## {title}",
        "",
        f"- Final equity: ₹{benchmark.final_equity:,.0f}",
        f"- Total return: {benchmark.total_return_pct:.1f}%",
        f"- CAGR: {benchmark.cagr_pct:.1f}%",
        f"- Sharpe: {benchmark.sharpe:.2f}",
        f"- Max drawdown: {benchmark.max_drawdown_pct:.1f}%",
        "",
        f"Alpha vs {title} — total return: {alpha['alpha_total_return_pct']:+.1f} pts, "
        f"CAGR: {alpha['alpha_cagr_pct']:+.1f} pts, "
        f"strategy beats it: {'Yes' if alpha['strategy_beats_benchmark'] else 'No'}",
        "",
    ]


def summarize(strategy, nifty_benchmark, nifty_alpha, alpha50_benchmark, alpha50_alpha,
              top_n: int, capital: float, position_size: float,
              n_symbols_used: int, n_symbols_total: int, rebal_count: int) -> str:
    lines = [
        "# S8-3 Rotation — Real Capital-Tracked Equity Curve",
        "",
        f"What docs/S8_3_BACKTEST_RESULTS.md's pooled per-trade stats (profit factor "
        f"1.18, Sharpe 0.63) actually mean for a real ₹{capital:,.0f} account: one "
        f"simulated account, real position sizing (₹{position_size:,.0f} across the top "
        f"{top_n}, via core/rotation/executor.py's own sizing), daily mark-to-market. "
        f"Baseline rank-dropout exit only — no stop-loss/EMA variants (out of scope for "
        f"this run, see script docstring). {n_symbols_used}/{n_symbols_total} universe "
        f"symbols had enough history to ever be ranked, {rebal_count} rebalance dates.",
        "",
        "## Strategy",
        "",
        f"- Initial capital: ₹{strategy.initial_capital:,.0f}",
        f"- Final equity: ₹{strategy.final_equity:,.0f}",
        f"- Total return: {strategy.total_return_pct:.1f}%",
        f"- CAGR: {strategy.cagr_pct:.1f}%",
        f"- Sharpe: {strategy.sharpe:.2f}",
        f"- Max drawdown: {strategy.max_drawdown_pct:.1f}% (₹{strategy.max_drawdown_rs:,.0f})",
        f"- Trades: {len(strategy.trades)}",
        "",
    ]
    lines += _benchmark_section("Nifty 500 benchmark (buy-and-hold, same window/capital)",
                                 nifty_benchmark, nifty_alpha)
    lines += _benchmark_section("Nifty Alpha 50 benchmark (buy-and-hold, same window/capital)",
                                 alpha50_benchmark, alpha50_alpha)
    lines += [
        "## Caveats",
        "",
        "- Delivery-style cost model with an approximated (doubled sell-leg) STT rate — "
        "same as docs/S8_3_MOMENTUM_METHODOLOGY.md.",
        "- Point-in-time Nifty 500 membership: each week's ranking is restricted to the "
        "actual constituents as of that week (core/rotation/nifty500_reconstitution.py, "
        "reconstructed from NSE's semi-annual reconstitution press releases), not today's "
        "list applied retroactively. This corrects the survivorship bias in the original "
        "run (quantos-equity-curve-and-fable-review) — a stock since dropped from the "
        "index can now be ranked/held in the weeks it actually was a constituent, and a "
        "recently-added one is excluded from weeks before it joined.",
        "- Nifty Alpha 50 benchmark is buy-and-hold on the index level only — it does NOT "
        "get the same point-in-time constituent treatment (nobody is trading its "
        "membership here, so there's no survivorship bias to correct for a passive holder).",
        "- Single simulated run, not a distribution — no confidence interval on CAGR/Sharpe/"
        "drawdown. Treat as one realization, not an expected value.",
    ]
    return "\n".join(lines)


# ─── Orchestration ───────────────────────────────────────────────────────────────

async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 400)  # +400d warmup for the 252d window
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
    # Point-in-time membership means some weeks' eligible set includes
    # symbols NSE has since dropped from Nifty 500 (or that hadn't joined
    # yet as of `current_universe`) -- those need price history fetched too,
    # or they'd be "eligible" some weeks with nothing to rank/enter.
    fetch_universe = sorted(frozenset().union(*(s.symbols for s in universe_snapshots)))
    n_historical_extra = len(fetch_universe) - len(current_universe)
    print(f"Fetching {len(fetch_universe)} universe symbols ({len(current_universe)} current + "
          f"{n_historical_extra} historical drops/joins for point-in-time correctness, "
          f"throttled 2-concurrent, this is the slow part) ...")
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

    # Same post-warmup slice rebalance_dates() derives its picks from, so
    # daily_dates and rebal_dates are consistent with each other and the
    # Nifty benchmark shares the exact same window as the strategy.
    warmed_up_candles = nifty_candles[LOOKBACK_DAYS:]
    daily_dates = [c.timestamp for c in warmed_up_candles]
    rebal_dates = set(rebalance_dates(nifty_candles))
    print(f"  {len(daily_dates)} trading days, {len(rebal_dates)} rebalance dates")

    print(f"Simulating portfolio (top {args.top_n}, ₹{args.capital:,.0f} capital, "
          f"₹{args.position_size:,.0f}/position) ...")
    strategy = simulate_portfolio(
        daily_dates, rebal_dates, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=DELIVERY_COST_MODEL, exit_rule="rank_only",
        universe_snapshots=universe_snapshots,
    )
    print(f"  final equity ₹{strategy.final_equity:,.0f}  CAGR {strategy.cagr_pct:.1f}%  "
          f"Sharpe {strategy.sharpe:.2f}  max DD {strategy.max_drawdown_pct:.1f}%")

    nifty_closes = [(c.timestamp, c.close) for c in warmed_up_candles]
    nifty_benchmark = simulate_index_buy_and_hold(nifty_closes, initial_capital=args.capital)
    nifty_alpha = compute_alpha(strategy, nifty_benchmark)

    # Aligned by date, not by array index -- Alpha 50 and NIFTY 50 are
    # separate fetches and needn't share array positions even though both
    # trade on NSE's calendar, so filtering by daily_dates[0] (rather than
    # reusing LOOKBACK_DAYS slicing) is what actually guarantees the "same
    # window" comparison the report claims.
    window_start = daily_dates[0]
    alpha50_closes = [(c.timestamp, c.close) for c in alpha50_candles if c.timestamp >= window_start]
    alpha50_benchmark = simulate_index_buy_and_hold(alpha50_closes, initial_capital=args.capital)
    alpha50_alpha = compute_alpha(strategy, alpha50_benchmark)

    report = summarize(strategy, nifty_benchmark, nifty_alpha, alpha50_benchmark, alpha50_alpha,
                        args.top_n, args.capital, args.position_size,
                        len(symbol_series), len(fetch_universe), len(rebal_dates))
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    # Windows consoles default to cp1252, which can't encode the Rupee sign
    # this script prints throughout -- force utf-8 so stdout doesn't crash
    # after ~20 minutes of data fetching.
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
    parser.add_argument("--out", default="docs/S8_3_EQUITY_CURVE_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
