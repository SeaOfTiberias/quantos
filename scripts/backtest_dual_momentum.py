#!/usr/bin/env python3
"""
QuantOS — Strategy 1: Regime-Filtered Dual-Momentum Backtest
──────────────────────────────────────────────────────────────
Methodology pre-committed in `docs/S1_DUAL_MOMENTUM_METHODOLOGY.md` before
this ran. Do not tune the score weighting, the 90d/180d windows, the
15/25 entry-exit band, or the ATR multipliers after seeing a result —
that becomes a new, separately pre-registered run.

Pure logic lives in `core/rotation/dual_momentum.py` (deliberately NOT
built on S8-3's live-critical `ranker.py`/`equity_curve.py` — see that
methodology doc's "why a new module" section). Reuses
`scripts/backtest_rs_momentum.py`'s `rebalance_dates`/`DELIVERY_COST_MODEL`
directly (generic, not S8-3-specific) and `core/backtest/parser.py`'s
`BacktestTrade`/`_compute_metrics` for pooled-trade PF/Sharpe/win-rate,
same two-report structure S8-3 used (pooled stats + capital-tracked
equity curve).

Per S8-1's finding (regime-conditioning has a 0-for-2 record in this
project) and the methodology doc: the UNFILTERED run is the headline;
the regime-gated run (NIFTY 50 vs its own EMA200) is informational only.

**Point-in-time Nifty 200 universe** (added 2026-07-24, after the first
run's clean-looking result raised the same survivorship-bias flag S8-3's
original run did): `core/rotation/nifty200_reconstitution.py` reconstructs
real point-in-time membership from NSE press releases, same discipline as
S8-3's own fix. Fetches the UNION of every symbol that was EVER a Nifty
200 constituent during the backtest window (not just today's 200), so
historical drops are actually rankable in the weeks they were real
constituents.

Usage:
    python scripts/backtest_dual_momentum.py
    python scripts/backtest_dual_momentum.py --years 3 --out docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md
"""

import argparse
import asyncio
import functools
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.regime.fetcher import ALPHA50_SYMBOL, NIFTY_SYMBOL  # noqa: E402
from core.rotation.dual_momentum import (  # noqa: E402
    EMA_TREND_SLOW, SymbolIndicators, build_indicators, simulate_dual_momentum, walk_forward_ema,
)
from core.rotation.equity_curve import compute_alpha, simulate_index_buy_and_hold  # noqa: E402
from core.rotation.nifty200_reconstitution import (  # noqa: E402
    NIFTY200_RECONSTITUTION_COVERAGE_START, build_point_in_time_nifty200, nifty200_eligible_asof,
)
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL, rebalance_dates  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

WARMUP_DAYS = 220   # >= EMA_TREND_SLOW(200) and RETURN_WINDOW_180D(180), + small buffer
INITIAL_CAPITAL = 1_000_000.0
POSITION_SIZE = 60_000.0   # ~15 positions from Rs10L, roughly even weight


def _closed_trades_to_backtest_trades(closed_trades) -> list[BacktestTrade]:
    """Converts core.rotation.dual_momentum.ClosedTrade -> BacktestTrade so
    the existing core/backtest/parser.py metrics machinery can be reused
    unchanged — same "construct BacktestTrade objects directly" pattern
    S8-3 used for its own cross-sectional (non-TradingView-exportable)
    trades."""
    sorted_trades = sorted(closed_trades, key=lambda t: t.entry_date)
    out = []
    cum = 0.0
    for i, t in enumerate(sorted_trades, 1):
        profit = (t.exit_price - t.entry_price) * t.qty
        profit_pct = (t.exit_price - t.entry_price) / t.entry_price * 100 if t.entry_price else 0.0
        cum += profit
        bars_held = max(1, (t.exit_date - t.entry_date).days)
        out.append(BacktestTrade(
            trade_num=i, direction="Long", qty=t.qty,
            entry_date=t.entry_date, entry_price=t.entry_price,
            exit_date=t.exit_date, exit_price=t.exit_price,
            profit=profit, profit_pct=profit_pct, cum_profit=cum,
            bars_held=bars_held, costs=t.costs,
        ))
    return out


def _regime_ok_by_date(nifty_candles: list[OHLCV]) -> dict:
    """NIFTY 50 close > its own walk-forward EMA200, as of each trading
    day — Filter 3 from the methodology doc, computed once here and
    reused for the informational regime-split run only."""
    closes = [c.close for c in nifty_candles]
    ema200 = walk_forward_ema(closes, EMA_TREND_SLOW)
    return {
        c.timestamp: (ema200[i] is not None and c.close > ema200[i])
        for i, c in enumerate(nifty_candles)
    }


def _split_metrics_section(trades: list[BacktestTrade]) -> list[str]:
    """First-half vs second-half pooled-trade Sharpe, chronological by
    entry date — Fable-recommended check (2026-07-24): a large Sharpe drop
    in the second half is a real overfit/degradation signal, same
    BacktestSplitMetrics.has_degradation convention core/backtest/parser.py
    already defines but scripts/backtest_rs_momentum.py never invoked."""
    sorted_trades = sorted(trades, key=lambda t: t.entry_date)
    mid = len(sorted_trades) // 2
    first, second = sorted_trades[:mid], sorted_trades[mid:]
    if len(first) < 5 or len(second) < 5:
        return ["*(too few trades to split first-half/second-half meaningfully)*"]
    m1, m2 = _compute_metrics(first), _compute_metrics(second)
    degrading = (m1.sharpe_ratio - m2.sharpe_ratio) > 0.5
    return [
        f"- First half:  n={m1.total_trades}, PF={m1.profit_factor:.2f}, Sharpe={m1.sharpe_ratio:.2f}",
        f"- Second half: n={m2.total_trades}, PF={m2.profit_factor:.2f}, Sharpe={m2.sharpe_ratio:.2f}",
        f"- Degradation flag (first-half Sharpe minus second-half Sharpe > 0.5): "
        f"{'YES' if degrading else 'no'}",
    ]


def summarize(
    unfiltered_trades: list[BacktestTrade], unfiltered_curve_result,
    filtered_trades: list[BacktestTrade], filtered_curve_result,
    n_symbols_used: int, n_symbols_total: int, rebal_count: int,
    coverage_clean_trades: list[BacktestTrade], coverage_clean_curve_result,
    coverage_clean_rebal_count: int,
    nifty_benchmark, nifty_alpha: dict,
    alpha50_benchmark, alpha50_alpha: dict,
) -> str:
    lines = [
        "# Strategy 1 — Regime-Filtered Dual-Momentum Backtest",
        "",
        f"Methodology pre-committed in `docs/S1_DUAL_MOMENTUM_METHODOLOGY.md` "
        f"before this ran. Nifty 200 universe, {n_symbols_used}/{n_symbols_total} "
        f"symbols had enough history to ever be ranked, {rebal_count} weekly "
        f"rebalance dates. Top 15 entry / Top 25 hold-eligible band, "
        f"2.5xATR initial stop, 2xATR Chandelier trail.",
        "",
    ]

    def _section(title: str, trades: list[BacktestTrade], curve_result) -> list[str]:
        out = [f"## {title}", ""]
        if not trades:
            out.append("**No trades generated.**")
            return out
        m = _compute_metrics(trades)
        verdict = "POSITIVE net-of-cost edge" if m.has_positive_edge else "NO demonstrated edge"
        out += [
            f"**Verdict: {verdict}** (pooled-trade `has_positive_edge`: profit factor > 1.0 AND Sharpe > 0.5)",
            "",
            "### Pooled per-trade stats",
            f"- Total trades: {m.total_trades}",
            f"- Win rate: {m.win_rate:.1%}",
            f"- Profit factor: {m.profit_factor:.2f}",
            f"- Sharpe ratio: {m.sharpe_ratio:.2f}",
            f"- Net profit (sum of per-trade net %): {m.net_profit_pct:.1f}%",
            f"- Avg holding period: {m.avg_bars_held:.0f} days",
            f"- Trades/month: {m.trades_per_month:.1f}",
            f"- Overfit risk flag: {'YES' if m.is_overfit_risk else 'no'}",
            "",
            "### Capital-tracked equity curve (Rs10L start)",
            f"- Final equity: Rs{curve_result.final_equity:,.0f}",
            f"- Total return: {curve_result.total_return_pct:.1f}%",
            f"- CAGR: {curve_result.cagr_pct:.1f}%",
            f"- Sharpe (equity-curve daily returns): {curve_result.sharpe:.2f}",
            f"- Max drawdown: {curve_result.max_drawdown_pct:.1f}%",
            "",
        ]
        return out

    lines += _section("Unfiltered (headline result)", unfiltered_trades, unfiltered_curve_result)
    lines += _section(
        "Regime-gated (NIFTY 50 > its own EMA200) — INFORMATIONAL ONLY, not the go/no-go basis",
        filtered_trades, filtered_curve_result,
    )

    # ── Fable-recommended diagnostics (2026-07-24), both run BEFORE seeing
    # whether they'd rescue or sink the headline number ──────────────────
    lines += [
        "## Coverage-gap sub-period check (rebalances on/after "
        f"{NIFTY200_RECONSTITUTION_COVERAGE_START.date()} only)",
        "",
        "Real point-in-time Nifty 200 events only go back to "
        f"{NIFTY200_RECONSTITUTION_COVERAGE_START.date()} — the full backtest's early "
        "rebalances (before that date) run against one static backward-projected "
        "snapshot, not true point-in-time membership. This re-runs the UNFILTERED "
        "strategy restricted to the period where the point-in-time fix is fully "
        "real, as its own fresh Rs10L account (not a slice of the full-window curve) "
        f"— {coverage_clean_rebal_count} rebalance dates.",
        "",
    ]
    lines += _section("Coverage-clean sub-period", coverage_clean_trades, coverage_clean_curve_result)

    lines += [
        "## Benchmark comparison (unfiltered strategy vs buy-and-hold, same window/capital)",
        "",
        "### NIFTY 50",
        f"- Benchmark final equity: Rs{nifty_benchmark.final_equity:,.0f}  "
        f"(total return {nifty_benchmark.total_return_pct:.1f}%, CAGR {nifty_benchmark.cagr_pct:.1f}%, "
        f"Sharpe {nifty_benchmark.sharpe:.2f})",
        f"- Alpha (strategy total return − benchmark total return): {nifty_alpha['alpha_total_return_pct']:+.1f}pp",
        f"- Alpha (CAGR): {nifty_alpha['alpha_cagr_pct']:+.1f}pp",
        f"- Strategy beats benchmark: {'YES' if nifty_alpha['strategy_beats_benchmark'] else 'NO'}",
        "",
        "### NIFTY ALPHA 50 (sharper peer bar — itself a momentum/alpha index)",
        f"- Benchmark final equity: Rs{alpha50_benchmark.final_equity:,.0f}  "
        f"(total return {alpha50_benchmark.total_return_pct:.1f}%, CAGR {alpha50_benchmark.cagr_pct:.1f}%, "
        f"Sharpe {alpha50_benchmark.sharpe:.2f})",
        f"- Alpha (strategy total return − benchmark total return): {alpha50_alpha['alpha_total_return_pct']:+.1f}pp",
        f"- Alpha (CAGR): {alpha50_alpha['alpha_cagr_pct']:+.1f}pp",
        f"- Strategy beats benchmark: {'YES' if alpha50_alpha['strategy_beats_benchmark'] else 'NO'}",
        "",
        "## First-half vs second-half Sharpe (unfiltered, pooled trades, chronological by entry date)",
        "",
    ]
    lines += _split_metrics_section(unfiltered_trades)
    lines += [
        "",
        "## Caveats",
        "",
        "- Point-in-time Nifty 200 universe (core/rotation/nifty200_reconstitution.py), "
        "same fix S8-3 needed after its own first result turned out to be pure "
        "survivorship bias — reconstructed from real NSE press releases, not assumed. "
        "Real events only go back to 2023-09-29 "
        "(NIFTY200_RECONSTITUTION_COVERAGE_START); dates before that use one static "
        "backward-projected snapshot, not true point-in-time.",
        "- Regime filter is informational only per S8-1's 0-for-2 "
        "regime-conditioning record in this project — never the basis for "
        "the go/no-go verdict.",
        "- Stop-loss trigger checked against the daily CLOSE, not an "
        "intrabar low — the simplest, most auditable construction, "
        "pre-registered before running.",
        "- DELIVERY_COST_MODEL reused unchanged from S8-3 "
        "(scripts/backtest_rs_momentum.py) — same asset class and holding "
        "style, no reason to build a second cost model.",
    ]
    return "\n".join(lines)


async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=365 * args.years + 400)
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY 50 daily candles {from_date.date()} -> {to_date.date()} ...")
    nifty_candles = await fetch_chunked_daily(broker, NIFTY_SYMBOL, from_date, to_date, sem)
    print(f"  {len(nifty_candles)} candles")

    print(f"Fetching NIFTY ALPHA 50 daily candles {from_date.date()} -> {to_date.date()} ...")
    alpha50_candles = await fetch_chunked_daily(broker, ALPHA50_SYMBOL, from_date, to_date, sem)
    print(f"  {len(alpha50_candles)} candles")

    current_universe = frozenset(
        ln.strip() for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    )
    snapshots = build_point_in_time_nifty200(current_universe)
    # Point-in-time membership means some weeks' eligible set includes
    # symbols NSE has since dropped from Nifty 200 (or that hadn't joined
    # yet as of `current_universe`) -- those need price history fetched
    # too, or they'd be "eligible" some weeks with nothing to rank/enter.
    # Same pattern scripts/backtest_equity_curve.py already uses for S8-3.
    universe = sorted(frozenset().union(*(s.symbols for s in snapshots)))
    n_historical_extra = len(universe) - len(current_universe)
    print(f"Fetching {len(universe)} universe symbols ({len(current_universe)} current + "
          f"{n_historical_extra} historical drops/joins for point-in-time correctness, "
          f"throttled 2-concurrent, this is the slow part) ...")
    indicators: dict[str, SymbolIndicators] = {}
    for n, symbol in enumerate(universe, 1):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(candles) >= WARMUP_DAYS:
            indicators[symbol] = build_indicators(candles)
        if n % 50 == 0:
            print(f"  {n}/{len(universe)} symbols fetched, {len(indicators)} usable so far")
    print(f"  {len(indicators)}/{len(universe)} symbols have enough history to ever be ranked")

    rebal_dates_list = rebalance_dates(nifty_candles, warmup_days=WARMUP_DAYS)
    rebal_dates = set(rebal_dates_list)
    print(f"  {len(rebal_dates)} rebalance dates")
    if not rebal_dates:
        print("ERROR: not enough NIFTY history for even one rebalance after warmup.")
        return 1

    daily_dates = [c.timestamp for c in nifty_candles if c.timestamp >= rebal_dates_list[0]]
    regime_ok = _regime_ok_by_date(nifty_candles)

    eligible_asof_fn = functools.partial(nifty200_eligible_asof, snapshots)

    print("Running UNFILTERED simulation (headline, point-in-time universe) ...")
    unfiltered_result = simulate_dual_momentum(
        daily_dates, rebal_dates, indicators, INITIAL_CAPITAL, POSITION_SIZE, DELIVERY_COST_MODEL,
        eligible_asof_fn=eligible_asof_fn,
    )
    print(f"  {len(unfiltered_result.trades)} trades")

    print("Running REGIME-GATED simulation (informational only, point-in-time universe) ...")
    filtered_result = simulate_dual_momentum(
        daily_dates, rebal_dates, indicators, INITIAL_CAPITAL, POSITION_SIZE, DELIVERY_COST_MODEL,
        eligible_asof_fn=eligible_asof_fn, regime_ok_by_date=regime_ok,
    )
    print(f"  {len(filtered_result.trades)} trades")

    unfiltered_bt = _closed_trades_to_backtest_trades(unfiltered_result.trades)
    filtered_bt = _closed_trades_to_backtest_trades(filtered_result.trades)

    # ── Fable-recommended diagnostics (2026-07-24) ────────────────────────
    coverage_rebal_dates_list = [d for d in rebal_dates_list if d >= NIFTY200_RECONSTITUTION_COVERAGE_START]
    coverage_rebal_dates = set(coverage_rebal_dates_list)
    coverage_daily_dates = [d for d in daily_dates if d >= NIFTY200_RECONSTITUTION_COVERAGE_START]
    print(f"Running COVERAGE-CLEAN sub-period simulation ({len(coverage_rebal_dates)} "
          f"rebalances on/after {NIFTY200_RECONSTITUTION_COVERAGE_START.date()}) ...")
    coverage_clean_result = simulate_dual_momentum(
        coverage_daily_dates, coverage_rebal_dates, indicators, INITIAL_CAPITAL, POSITION_SIZE,
        DELIVERY_COST_MODEL, eligible_asof_fn=eligible_asof_fn,
    )
    print(f"  {len(coverage_clean_result.trades)} trades")
    coverage_clean_bt = _closed_trades_to_backtest_trades(coverage_clean_result.trades)

    window_start = daily_dates[0]
    nifty_closes = [(c.timestamp, c.close) for c in nifty_candles if c.timestamp >= window_start]
    nifty_benchmark = simulate_index_buy_and_hold(nifty_closes, initial_capital=INITIAL_CAPITAL)
    nifty_alpha = compute_alpha(unfiltered_result, nifty_benchmark)

    alpha50_closes = [(c.timestamp, c.close) for c in alpha50_candles if c.timestamp >= window_start]
    alpha50_benchmark = simulate_index_buy_and_hold(alpha50_closes, initial_capital=INITIAL_CAPITAL)
    alpha50_alpha = compute_alpha(unfiltered_result, alpha50_benchmark)

    report = summarize(
        unfiltered_bt, unfiltered_result, filtered_bt, filtered_result,
        len(indicators), len(universe), len(rebal_dates),
        coverage_clean_bt, coverage_clean_result, len(coverage_rebal_dates),
        nifty_benchmark, nifty_alpha, alpha50_benchmark, alpha50_alpha,
    )
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--universe", default="agent/universe_nifty200.txt")
    parser.add_argument("--out", default="docs/S1_DUAL_MOMENTUM_BACKTEST_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
