#!/usr/bin/env python3
"""
QuantOS — Dow Theory / Market Structure Trend Following Backtest (candidate 14)
──────────────────────────────────────────────────────────────────────────────
See docs/DOW_THEORY_TREND_METHODOLOGY.md for every design choice (fixed
BEFORE this script was run): NIFTY spot as a disclosed proxy for futures,
5-bar Williams fractal swing structure, mechanical stop/1R-scale-out/
trailing exits, 2 lots per trade, session-flatten at 15:20 IST, cost model
reused unchanged from core/pairs/costs.py.

Fetch layer: Fyers 5-minute NIFTY candles, chunked to the confirmed
100-day-per-request intraday limit (see methodology doc's live-probe
finding), throttled + retried like every other live-broker script here.
Needs a fresh Fyers auth token (agent/config.yaml's configured broker).

Usage
─────
    python scripts/backtest_dow_theory_trend.py
    python scripts/backtest_dow_theory_trend.py --start 2022-06-01 --out docs/DOW_THEORY_TREND_RESULTS.md
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics, BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402
from core.pairs.costs import position_cost  # noqa: E402
from core.trend.dow_structure import Trade, simulate_day  # noqa: E402

logger = logging.getLogger(__name__)

NIFTY_SYMBOL = "NIFTY"
LOT_SIZE = 65          # confirmed live 2026-07-26 from cached bhavcopy IDF row, see methodology doc
LOTS_PER_TRADE = 2      # see methodology doc's "Position sizing" section
WINDOW_START = date(2022, 6, 1)   # within the confirmed-live 5m data depth (back to 2022-05-28)

MAX_CHUNK_DAYS = 95     # Fyers' confirmed live limit is 100 days per intraday request; keep margin
REQUEST_TIMEOUT_SECS = 30.0


# ─── Fetch layer (I/O — needs a connected broker) ────────────────────────────

async def fetch_chunked_intraday(
    broker: BrokerAdapter, symbol: str, from_date: datetime, to_date: datetime,
    sem: asyncio.Semaphore, delay: float = 0.5, max_retries: int = 3,
) -> list[OHLCV]:
    """Fetch 5m candles across a date range, chunked to Fyers' confirmed
    100-day intraday limit -- same throttle/retry shape as
    scripts/validate_regime_classifier.py's fetch_chunked_daily."""
    loop = asyncio.get_event_loop()
    all_candles: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=MAX_CHUNK_DAYS), to_date)
        for attempt in range(max_retries):
            async with sem:
                try:
                    candles = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda cs=chunk_start, ce=chunk_end: broker.get_historical_data(symbol, "5m", cs, ce),
                        ),
                        timeout=REQUEST_TIMEOUT_SECS,
                    )
                    await asyncio.sleep(delay)
                    all_candles.extend(candles)
                    break
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        logger.warning("Timed out fetching %s..%s, retrying in %.0fs", chunk_start, chunk_end, wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        logger.warning("Error fetching %s..%s: %s, retrying in %.0fs", chunk_start, chunk_end, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
        chunk_start = chunk_end
    # De-dupe (chunk boundaries can overlap by one candle) and sort.
    by_ts = {c.timestamp: c for c in all_candles}
    return sorted(by_ts.values(), key=lambda c: c.timestamp)


def group_by_day(candles: list[OHLCV]) -> dict[date, list[OHLCV]]:
    """UTC calendar date == IST trading-session date here: the whole
    03:45-10:00 UTC session sits inside one UTC day, never crossing
    midnight, so no timezone conversion is needed to group correctly."""
    by_day: dict[date, list[OHLCV]] = {}
    for c in candles:
        by_day.setdefault(c.timestamp.date(), []).append(c)
    for day_candles in by_day.values():
        day_candles.sort(key=lambda c: c.timestamp)
    return by_day


# ─── Trade -> BacktestTrade conversion (pure) ────────────────────────────────

def to_backtest_trade(trade: Trade, day_candles: list[OHLCV], trade_num: int) -> BacktestTrade:
    """Converts one core.trend.dow_structure.Trade (index-point terms) into
    a BacktestTrade (INR terms), applying LOT_SIZE/LOTS_PER_TRADE sizing
    and core/pairs/costs.py's reused futures cost model."""
    entry_dt = day_candles[trade.entry_index].timestamp
    exit_dt = day_candles[trade.exit_index].timestamp
    units = round(LOTS_PER_TRADE * LOT_SIZE * trade.quantity_fraction)
    num_lots = max(1, round(units / LOT_SIZE))

    sign = 1 if trade.direction == "LONG" else -1
    profit = sign * (trade.exit_price - trade.entry_price) * units
    notional = abs(trade.entry_price) * units
    profit_pct = (profit / notional * 100) if notional else 0.0

    costs = position_cost(
        entry_price=trade.entry_price, exit_price=trade.exit_price,
        lot_size=LOT_SIZE, num_lots=num_lots,
        direction="BUY" if trade.direction == "LONG" else "SELL",
        entry_date=entry_dt.date(), exit_date=exit_dt.date(),
    )

    return BacktestTrade(
        trade_num=trade_num, direction="Long" if trade.direction == "LONG" else "Short",
        qty=units, entry_date=entry_dt, entry_price=trade.entry_price,
        exit_date=exit_dt, exit_price=trade.exit_price,
        profit=profit, profit_pct=profit_pct, cum_profit=0.0,
        bars_held=trade.exit_index - trade.entry_index, costs=costs,
    )


# ─── Report ───────────────────────────────────────────────────────────────

def _metrics_row(label: str, m: BacktestMetrics) -> str:
    return (f"| {label} | {m.total_trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | "
            f"{m.sharpe_ratio:.2f} | {m.net_profit_pct:+.1f}% | {m.max_drawdown_pct:.1f}% |")


def summarize(trades: list[BacktestTrade], window_start: date, window_end: date) -> str:
    overall = _compute_metrics(trades)
    by_year: dict[int, list[BacktestTrade]] = {}
    for t in trades:
        by_year.setdefault(t.exit_date.year, []).append(t)

    lines = [
        "# Dow Theory / Market Structure Trend Following — Backtest Results (Candidate 14)",
        "",
        f"Methodology: docs/DOW_THEORY_TREND_METHODOLOGY.md. NIFTY spot (futures proxy, "
        f"see methodology doc), {window_start} to {window_end}. {len(trades)} trade legs total "
        f"(includes both halves of a scaled-out position as separate legs).",
        "",
        "## Pooled result",
        "",
        "| Period | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |",
        "|---|---|---|---|---|---|---|",
        _metrics_row("**Overall**", overall),
    ]
    for year in sorted(by_year):
        year_trades = by_year[year]
        if len(year_trades) < 3:
            lines.append(f"| {year} | {len(year_trades)} | *(too few for a metric)* | | | | |")
            continue
        lines.append(_metrics_row(str(year), _compute_metrics(year_trades)))

    lines += [
        "",
        "## Verdict",
        "",
        f"Per `core/backtest/parser.py`'s `has_positive_edge` bar (PF > 1.0 AND Sharpe > 0.5), "
        f"computed on the pooled trade-leg set, net of the reused futures cost model: "
        f"**{'PASS' if overall.has_positive_edge else 'FAIL'}**.",
        "",
        "Read the per-year table above, not just the pooled row, before trusting this — "
        "same discipline every prior candidate's per-fold/per-year breakdown has used.",
    ]
    return "\n".join(lines)


# ─── Orchestration ────────────────────────────────────────────────────────

async def main_async(args) -> int:
    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    broker.connect()

    from_dt = datetime.combine(args.start, datetime.min.time(), tzinfo=timezone.utc)
    to_dt = datetime.now(timezone.utc)
    sem = asyncio.Semaphore(2)

    print(f"Fetching NIFTY 5m candles {from_dt.date()} -> {to_dt.date()} (chunked, this is the slow part) ...")
    candles = await fetch_chunked_intraday(broker, NIFTY_SYMBOL, from_dt, to_dt, sem)
    print(f"  {len(candles)} candles fetched")
    if not candles:
        print("ERROR: no candles fetched.")
        return 1

    by_day = group_by_day(candles)
    print(f"  {len(by_day)} trading days")

    all_trades: list[BacktestTrade] = []
    trade_num = 0
    for day, day_candles in sorted(by_day.items()):
        day_trades = simulate_day(day_candles)
        for t in day_trades:
            trade_num += 1
            all_trades.append(to_backtest_trade(t, day_candles, trade_num))

    print(f"  {len(all_trades)} trade legs generated")
    if not all_trades:
        print("ERROR: zero trades generated -- check data/logic before trusting an empty result.")
        return 1

    window_start = min(by_day)
    window_end = max(by_day)
    report = summarize(all_trades, window_start, window_end)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--out", default="docs/DOW_THEORY_TREND_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
