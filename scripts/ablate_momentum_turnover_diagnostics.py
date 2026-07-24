#!/usr/bin/env python3
"""
QuantOS — Momentum Turnover Ablation: Follow-Up Diagnostics
────────────────────────────────────────────────────────────────────────────
Methodology pre-committed in
docs/MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_METHODOLOGY.md before this ran.
Addendum to scripts/ablate_momentum_turnover.py (not a modification of it —
that script's committed result stands as run). Fable's review of the
original quarterly-vs-weekly result withheld a verdict pending two checks:

1. Point-in-time coverage: core/rotation/nifty500_reconstitution.py's real
   event coverage only starts 2023-09-29 — rebalances before that use a
   static backward-projected snapshot, same class of gap Fable's review of
   Strategy 1 found. Re-runs the quarterly simulation restricted to
   coverage-clean rebalance dates only, as its own fresh account.
2. First-half/second-half stability: only 14 quarterly rebalances total in
   the original run — splits closed trades chronologically, reports pooled
   per-trade PF/Sharpe for each half.

Usage:
    python scripts/ablate_momentum_turnover_diagnostics.py
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.rotation.equity_curve import simulate_portfolio  # noqa: E402
from core.rotation.nifty500_reconstitution import (  # noqa: E402
    EVENTS, build_point_in_time_universe,
)
from core.rotation.ranker import LOOKBACK_DAYS, TOP_N, SymbolSeries, build_symbol_series  # noqa: E402
from scripts.ablate_momentum_turnover import quarterly_rebalance_dates  # noqa: E402
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

NIFTY_SYMBOL = "NIFTY 50"

# The real point-in-time coverage start, derived from the module's own data
# (not hardcoded independently) -- rebalances before this use a static
# backward-projected snapshot, not true point-in-time membership.
COVERAGE_START = min(e.effective_date for e in EVENTS)


def _pooled_trade_stats(trades: list) -> dict:
    """Profit factor + Sharpe on per-trade pct returns, pooled (not
    capital-tracked) -- same has_positive_edge-style convention used
    throughout this project for split diagnostics (matches Strategy 1's
    _split_metrics_section)."""
    if not trades:
        return {"n": 0, "profit_factor": 0.0, "sharpe": 0.0}
    returns = [(t.exit_price - t.entry_price) / t.entry_price * 100 for t in trades]
    gains = sum(r for r in returns if r > 0)
    losses = -sum(r for r in returns if r < 0)
    pf = (gains / losses) if losses > 0 else float("inf") if gains > 0 else 0.0
    n = len(returns)
    mean = sum(returns) / n
    if n < 2:
        sharpe = 0.0
    else:
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = variance ** 0.5
        sharpe = (mean / std) if std > 1e-9 else 0.0
    return {"n": n, "profit_factor": round(pf, 3), "sharpe": round(sharpe, 3)}


def half_split_diagnostic(trades: list) -> dict:
    trades_sorted = sorted(trades, key=lambda t: t.entry_date)
    mid = len(trades_sorted) // 2
    first_half = _pooled_trade_stats(trades_sorted[:mid])
    second_half = _pooled_trade_stats(trades_sorted[mid:])
    degradation = (first_half["sharpe"] - second_half["sharpe"]) > 0.5
    return {"first_half": first_half, "second_half": second_half, "degradation_flag": degradation}


def _report(coverage_result, coverage_rebal_count, half_split) -> str:
    fh, sh = half_split["first_half"], half_split["second_half"]
    return "\n".join([
        "# Momentum Turnover Ablation — Follow-Up Diagnostics",
        "",
        f"Methodology: docs/MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_METHODOLOGY.md. "
        f"Addendum to docs/MOMENTUM_TURNOVER_ABLATION_RESULTS.md (original quarterly "
        f"run, not modified here). Real point-in-time coverage starts "
        f"{COVERAGE_START.date()} (core/rotation/nifty500_reconstitution.py's "
        f"earliest EVENTS entry).",
        "",
        "## Diagnostic 1 — coverage-clean sub-period",
        "",
        f"Quarterly rebalances on/after {COVERAGE_START.date()} only, as a fresh "
        f"₹1,000,000 account: {coverage_rebal_count} rebalance dates.",
        "",
        f"- Total return: {coverage_result.total_return_pct:.1f}%",
        f"- CAGR: {coverage_result.cagr_pct:.1f}%",
        f"- Sharpe: {coverage_result.sharpe:.2f}",
        f"- Max drawdown: {coverage_result.max_drawdown_pct:.1f}%",
        f"- Trades: {len(coverage_result.trades)}",
        "",
        "Compare to the original full-window quarterly result (CAGR 10.2%, Sharpe "
        "0.81, 244 trades) — a large gap between these two numbers means the "
        "original result was meaningfully propped up by the pre-coverage static "
        "snapshot period.",
        "",
        "## Diagnostic 2 — first-half vs second-half stability (full-window trades, "
        "pooled per-trade)",
        "",
        f"- First half:  n={fh['n']}, PF={fh['profit_factor']}, Sharpe={fh['sharpe']}",
        f"- Second half: n={sh['n']}, PF={sh['profit_factor']}, Sharpe={sh['sharpe']}",
        f"- Degradation flag (first-half Sharpe minus second-half Sharpe > 0.5): "
        f"{'YES' if half_split['degradation_flag'] else 'NO'}",
        "",
        "## Interpretation",
        "",
        "Neither diagnostic alone is a pass/fail verdict — see the methodology "
        "doc's framing. A clean coverage-clean result AND no degradation flag "
        "makes quarterly momentum a stronger candidate for a full, separately "
        "pre-registered strategy test. Either one failing means the original "
        "ablation's headline number was doing less work than it looked like.",
    ])


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
    print(f"  {len(symbol_series)}/{len(fetch_universe)} symbols usable")

    warmed_up_candles = nifty_candles[LOOKBACK_DAYS:]
    daily_dates = [c.timestamp for c in warmed_up_candles]
    all_rebal_dates = quarterly_rebalance_dates(nifty_candles)
    rebal_dates_q = set(all_rebal_dates)
    print(f"  {len(daily_dates)} trading days, {len(rebal_dates_q)} quarterly rebalance dates")
    print(f"  rebalance dates: {[d.date().isoformat() for d in sorted(all_rebal_dates)]}")

    # ── Full-window run (needed for the half-split diagnostic) ──────────────
    print("Simulating full-window quarterly portfolio (for half-split diagnostic) ...")
    full = simulate_portfolio(
        daily_dates, rebal_dates_q, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=DELIVERY_COST_MODEL, exit_rule="rank_only",
        universe_snapshots=universe_snapshots,
    )
    half_split = half_split_diagnostic(full.trades)
    print(f"  first-half Sharpe {half_split['first_half']['sharpe']}, "
          f"second-half Sharpe {half_split['second_half']['sharpe']}")

    # ── Coverage-clean sub-period, fresh account ─────────────────────────────
    coverage_rebal_dates = {d for d in all_rebal_dates if d >= COVERAGE_START}
    coverage_daily_dates = [d for d in daily_dates if d >= min(coverage_rebal_dates, default=daily_dates[-1])]
    print(f"Simulating coverage-clean quarterly portfolio ({len(coverage_rebal_dates)} "
          f"rebalance dates on/after {COVERAGE_START.date()}) ...")
    coverage_result = simulate_portfolio(
        coverage_daily_dates, coverage_rebal_dates, symbol_series, top_n=args.top_n,
        initial_capital=args.capital, position_size=args.position_size,
        cost_model=DELIVERY_COST_MODEL, exit_rule="rank_only",
        universe_snapshots=universe_snapshots,
    )
    print(f"  final equity ₹{coverage_result.final_equity:,.0f}  CAGR {coverage_result.cagr_pct:.1f}%  "
          f"Sharpe {coverage_result.sharpe:.2f}")

    report = _report(coverage_result, len(coverage_rebal_dates), half_split)
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
    parser.add_argument("--out", default="docs/MOMENTUM_TURNOVER_ABLATION_DIAGNOSTICS_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
