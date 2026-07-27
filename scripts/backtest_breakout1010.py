#!/usr/bin/env python3
"""
QuantOS — 10:10 Breakout on BankNifty Options Backtest (candidate 15)
──────────────────────────────────────────────────────────────────────
See docs/BREAKOUT_1010_METHODOLOGY.md for every design choice (fixed
BEFORE this script was run): reference-candle breakout on the BankNifty
INDEX, Black-Scholes-reconstructed option premium (real spot + contract
strike/expiry + contemporaneous India VIX as the IV proxy — real option
premium history is confirmed unfetchable from Fyers, see
docs/CANDIDATE15_OPTION_DATA_FEASIBILITY.md), monthly-only contract
selection, 1 lot/trade, session-flatten at 15:20 IST, reused F&O options
cost rates.

Fetch layer: Fyers 5-minute BankNifty + India VIX candles, chunked to the
confirmed 100-day-per-request intraday limit, same throttle/retry pattern
as scripts/backtest_dow_theory_trend.py. Needs a fresh Fyers auth token
(agent/config.yaml's configured broker).

Usage
─────
    python scripts/backtest_breakout1010.py
    python scripts/backtest_breakout1010.py --start 2021-06-01 --out docs/BREAKOUT_1010_RESULTS.md
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
from core.breakout1010.backtest import run_backtest  # noqa: E402
from core.brokers.base import BrokerAdapter, OHLCV  # noqa: E402

logger = logging.getLogger(__name__)

BANKNIFTY_SYMBOL = "NIFTY BANK"
VIX_SYMBOL = "INDIA VIX"
WINDOW_START = date(2021, 6, 1)   # within the confirmed-live 5m data depth for both series (back to 2021-05)

MAX_CHUNK_DAYS = 95     # Fyers' confirmed live limit is 100 days per intraday request; keep margin
REQUEST_TIMEOUT_SECS = 30.0


# ─── Fetch layer (I/O — needs a connected broker) ────────────────────────────

async def fetch_chunked_intraday(
    broker: BrokerAdapter, symbol: str, from_date: datetime, to_date: datetime,
    sem: asyncio.Semaphore, delay: float = 0.5, max_retries: int = 3,
) -> list[OHLCV]:
    """Fetch 5m candles across a date range, chunked to Fyers' confirmed
    100-day intraday limit -- same throttle/retry shape as
    scripts/backtest_dow_theory_trend.py's fetch_chunked_intraday."""
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
                        logger.warning("Timed out fetching %s %s..%s, retrying in %.0fs", symbol, chunk_start, chunk_end, wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 3.0 * (attempt + 1)
                        logger.warning("Error fetching %s %s..%s: %s, retrying in %.0fs", symbol, chunk_start, chunk_end, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        raise
        chunk_start = chunk_end
    # De-dupe (chunk boundaries can overlap by one candle) and sort.
    by_ts = {c.timestamp: c for c in all_candles}
    return sorted(by_ts.values(), key=lambda c: c.timestamp)


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
        "# 10:10 Breakout on BankNifty Options — Backtest Results (Candidate 15)",
        "",
        f"Methodology: docs/BREAKOUT_1010_METHODOLOGY.md. Black-Scholes-reconstructed "
        f"option premium (real BankNifty spot + India VIX proxy, NOT real traded "
        f"premium — see docs/CANDIDATE15_OPTION_DATA_FEASIBILITY.md), "
        f"{window_start} to {window_end}. {len(trades)} trades total (one per day, at most).",
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
        f"computed on the pooled trade set, net of the reused F&O options cost model: "
        f"**{'PASS' if overall.has_positive_edge else 'FAIL'}**.",
        "",
        "Read the per-year table above, not just the pooled row, before trusting this — "
        "same discipline every prior candidate's per-fold/per-year breakdown has used. "
        "**Remember**: every premium here is Black-Scholes theoretical, not a real traded "
        "price — see the methodology doc's central-limitation section before treating a "
        "PASS as sufficient to move toward live capital.",
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

    print(f"Fetching BankNifty 5m candles {from_dt.date()} -> {to_dt.date()} (chunked, this is the slow part) ...")
    bn_candles = await fetch_chunked_intraday(broker, BANKNIFTY_SYMBOL, from_dt, to_dt, sem)
    print(f"  {len(bn_candles)} BankNifty candles fetched")

    print(f"Fetching India VIX 5m candles {from_dt.date()} -> {to_dt.date()} (chunked) ...")
    vix_candles = await fetch_chunked_intraday(broker, VIX_SYMBOL, from_dt, to_dt, sem)
    print(f"  {len(vix_candles)} India VIX candles fetched")

    if not bn_candles or not vix_candles:
        print("ERROR: no candles fetched for one or both series.")
        return 1

    all_trades = run_backtest(bn_candles, vix_candles)
    print(f"  {len(all_trades)} trades generated")
    if not all_trades:
        print("ERROR: zero trades generated -- check data/logic before trusting an empty result.")
        return 1

    window_start = min(c.timestamp.date() for c in bn_candles)
    window_end = max(c.timestamp.date() for c in bn_candles)
    report = summarize(all_trades, window_start, window_end)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--start", type=date.fromisoformat, default=WINDOW_START)
    parser.add_argument("--out", default="docs/BREAKOUT_1010_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
