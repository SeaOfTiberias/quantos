#!/usr/bin/env python3
"""
QuantOS — S8-3: 52-Week-High RS Momentum Backtest
──────────────────────────────────────────────────────
Backtests cross-sectional 52-week-high relative-strength momentum (George &
Hwang 2004: stocks near their 52-week high tend to keep outperforming) over
the committed Nifty 500 universe — Fable's top-ranked post-Darvas candidate,
the actual documented anomaly rather than a borrowed citation.

Methodology is pre-committed in full BEFORE this script was run — see
docs/S8_3_MOMENTUM_METHODOLOGY.md. Do not tune N, the rebalance cadence, the
ranking window, or the cost model after seeing a result; that becomes a new,
separately pre-registered run, not an edit to this one.

Constructs BacktestTrade objects directly (no TradingView export exists for
a cross-sectional strategy — this is a rotation, not single-symbol trades)
and feeds the existing core/backtest/parser.py metrics machinery, same
pattern as S7-3/S8-4.

Usage:
    python scripts/backtest_rs_momentum.py
    python scripts/backtest_rs_momentum.py --years 3 --top-n 20 --out docs/S8_3_BACKTEST_RESULTS.md
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.regime.fetcher import NIFTY_SYMBOL  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402
from core.rotation.ranker import (  # noqa: E402
    SymbolSeries, TOP_N, LOOKBACK_DAYS, build_symbol_series, rank_universe, value_as_of,
)
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

NOTIONAL_PER_TRADE = 100_000.0    # representative position size, for realistic absolute cost figures

# Pre-committed delivery-style cost model — see docs/S8_3_MOMENTUM_METHODOLOGY.md
# for why each rate differs from the equity-intraday DEFAULT_COST_MODEL.
DELIVERY_COST_MODEL = CostModel(
    brokerage_pct=0.0, brokerage_flat=0.0,   # discount brokers: Rs0 delivery brokerage
    stt_pct=0.002,           # approximates delivery STT (0.1% BOTH legs) by doubling the sell-leg-only formula
    exchange_txn_pct=0.0000307,  # same as intraday, applies uniformly regardless of product type
    sebi_pct=0.000001,       # same as intraday
    stamp_pct=0.00015,       # delivery stamp duty (buy leg only, matches CostModel's structure correctly)
    gst_pct=0.18,
    slippage_bps=10.0,       # weekly-hold entries are far less fill-urgent than an intraday breakout
)


# ─── Backtest-specific logic (ranking itself lives in core/rotation/ranker.py,
# shared with live execution — see that module's docstring) ────────────────────

def rebalance_dates(nifty_candles: list[OHLCV], warmup_days: int = LOOKBACK_DAYS) -> list[datetime]:
    """Last NIFTY trading day of each ISO calendar week, after enough
    warmup for the 52-week-high window — NIFTY's own calendar is the
    master date list every symbol rebalances against."""
    if len(nifty_candles) <= warmup_days:
        return []
    candles = nifty_candles[warmup_days:]
    dates = []
    for i, c in enumerate(candles):
        is_last_of_week = (
            i == len(candles) - 1
            or candles[i + 1].timestamp.isocalendar()[:2] != c.timestamp.isocalendar()[:2]
        )
        if is_last_of_week:
            dates.append(c.timestamp)
    return dates


def run_rotation(
    rebal_dates: list[datetime], symbol_series: dict[str, SymbolSeries],
    top_n: int, cost_model: CostModel,
) -> list[BacktestTrade]:
    open_positions: dict[str, dict] = {}   # symbol -> {"entry_date", "entry_price", "qty"}
    trades: list[BacktestTrade] = []
    trade_num = 0
    last_known_price: dict[str, float] = {}

    for rebal_date in rebal_dates:
        price_lookup = {}
        for symbol, series in symbol_series.items():
            v = value_as_of(series, rebal_date)
            if v is None:
                continue
            close, _high = v
            price_lookup[symbol] = close
            last_known_price[symbol] = close
        top_set = set(rank_universe(symbol_series, rebal_date, top_n))

        # Exits: held but no longer in the top set.
        for symbol in list(open_positions.keys()):
            if symbol not in top_set:
                pos = open_positions.pop(symbol)
                exit_price = price_lookup.get(symbol, last_known_price.get(symbol, pos["entry_price"]))
                trade_num += 1
                trades.append(_make_trade(trade_num, pos, rebal_date, exit_price, cost_model))

        # Entries: newly in the top set.
        for symbol in top_set:
            if symbol not in open_positions:
                entry_price = price_lookup[symbol]
                qty = max(1, round(NOTIONAL_PER_TRADE / entry_price))
                open_positions[symbol] = {"entry_date": rebal_date, "entry_price": entry_price, "qty": qty}

    # Force-close anything still open at the final rebalance date.
    if rebal_dates:
        final_date = rebal_dates[-1]
        for symbol, pos in open_positions.items():
            exit_price = last_known_price.get(symbol, pos["entry_price"])
            trade_num += 1
            trades.append(_make_trade(trade_num, pos, final_date, exit_price, cost_model))

    trades.sort(key=lambda t: t.entry_date)
    # Backfill cumulative GROSS profit in entry-date order (matches
    # BacktestTrade.cum_profit's own convention) -- _compute_metrics itself
    # doesn't read this field (it recomputes its own running total from
    # net_profit_pct), but the returned trade objects should still be correct.
    cum = 0.0
    for t in trades:
        cum += t.profit
        t.cum_profit = cum
    return trades


def _make_trade(num: int, pos: dict, exit_date: datetime, exit_price: float, cost_model: CostModel) -> BacktestTrade:
    entry_price, qty = pos["entry_price"], pos["qty"]
    profit = (exit_price - entry_price) * qty
    profit_pct = (exit_price - entry_price) / entry_price * 100 if entry_price else 0.0
    costs = cost_model.cost_of(entry_price, exit_price, qty, "BUY")
    bars_held = max(1, (exit_date - pos["entry_date"]).days)
    return BacktestTrade(
        trade_num=num, direction="Long", qty=qty,
        entry_date=pos["entry_date"], entry_price=entry_price,
        exit_date=exit_date, exit_price=exit_price,
        profit=profit, profit_pct=profit_pct, cum_profit=0.0,
        bars_held=bars_held, costs=costs,
    )


# ─── Report ─────────────────────────────────────────────────────────────────────

def summarize(trades: list[BacktestTrade], n_symbols_used: int, n_symbols_total: int,
              rebal_count: int, top_n: int) -> str:
    lines = [
        "# S8-3 52-Week-High RS Momentum Backtest",
        "",
        f"Methodology pre-committed in `docs/S8_3_MOMENTUM_METHODOLOGY.md` before this "
        f"ran. Top {top_n} by nearness-to-52-week-high, weekly rotation, "
        f"{n_symbols_used}/{n_symbols_total} universe symbols had enough history to "
        f"ever be ranked, {rebal_count} rebalance dates.",
        "",
    ]
    if not trades:
        lines.append("**No trades generated — insufficient history across the universe for this window.**")
        return "\n".join(lines)

    m = _compute_metrics(trades)
    verdict = "POSITIVE net-of-cost edge" if m.has_positive_edge else "NO demonstrated edge"
    lines += [
        f"## Verdict: {verdict}",
        "",
        f"- Total trades (pooled rotation): {m.total_trades}",
        f"- Win rate: {m.win_rate:.1%}",
        f"- Profit factor: {m.profit_factor:.2f}",
        f"- Sharpe ratio: {m.sharpe_ratio:.2f}",
        f"- Max drawdown: {m.max_drawdown_pct:.1f}%",
        f"- Net profit (sum of per-trade net %): {m.net_profit_pct:.1f}%",
        f"- Avg holding period: {m.avg_bars_held:.0f} days",
        f"- Trades/month: {m.trades_per_month:.1f}",
        f"- Overfit risk flag: {'YES' if m.is_overfit_risk else 'no'}",
        "",
        "## Caveats",
        "",
        "- Delivery-style cost model with an approximated (doubled sell-leg) STT rate — "
        "see docs/S8_3_MOMENTUM_METHODOLOGY.md for why.",
        "- No anti-chattering buffer at the rank-20 boundary by design (pre-committed) — "
        "if turnover looks high, that's the honest cost of a pure rotation, not a bug to fix "
        "retroactively.",
        "- Survivorship note: agent/universe_nifty500.txt is the CURRENT constituent list, "
        "so this shares Darvas's survivorship bias (an upper bound, not a lower bound) — "
        "a negative result here is conclusive; a positive one still needs to clear that bar.",
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

    universe = [ln.strip() for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")]
    print(f"Fetching {len(universe)} universe symbols (throttled 2-concurrent, this is the slow part) ...")
    symbol_series: dict[str, SymbolSeries] = {}
    for n, symbol in enumerate(universe, 1):
        candles = await fetch_chunked_daily(broker, symbol, from_date, to_date, sem)
        if len(candles) >= LOOKBACK_DAYS:
            symbol_series[symbol] = build_symbol_series(candles)
        if n % 50 == 0:
            print(f"  {n}/{len(universe)} symbols fetched, {len(symbol_series)} usable so far")
    print(f"  {len(symbol_series)}/{len(universe)} symbols have enough history to ever be ranked")

    rebal_dates = rebalance_dates(nifty_candles)
    print(f"  {len(rebal_dates)} rebalance dates")
    if not rebal_dates:
        print("ERROR: not enough NIFTY history for even one rebalance after warmup.")
        return 1

    print(f"Running rotation (top {args.top_n}) ...")
    trades = run_rotation(rebal_dates, symbol_series, args.top_n, DELIVERY_COST_MODEL)
    print(f"  {len(trades)} trades generated")

    report = summarize(trades, len(symbol_series), len(universe), len(rebal_dates), args.top_n)
    Path(args.out).write_text(report + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--years", type=float, default=3.0)
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--out", default="docs/S8_3_BACKTEST_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
