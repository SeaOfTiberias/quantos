#!/usr/bin/env python3
"""
QuantOS — "Good Night" Scalper Backtest (candidate 20)
──────────────────────────────────────────────────────────────────────
See docs/GOODNIGHT_SCALPER_METHODOLOGY.md for every design choice (fixed
BEFORE this script was run): Setup A/B only (Setup C excluded), Nifty200
Momentum 30 universe minus SAIL, 09:15-09:30 IST entry/exit window,
+10%/-15%/flatten premium bracket, per-stock trailing-20-day realized-vol
IV proxy, Clean/Stressed (real measured spread) cost split, pooled
validation (not per-symbol/per-setup).

Fetch layer: 1-minute candles (the whole session per day, sliced down to
the 09:15-09:31 IST window after fetching -- Fyers has no way to request
only part of a day) and daily candles (realized-vol lookback), both
chunked and throttled. The 1-minute chunk size (ONE_MIN_CHUNK_DAYS) is a
conservative, DISCLOSED guess, not a precisely re-probed Fyers limit the
way candidate 18's 5-minute chunk size was -- if a chunk comes back empty
or errors past the retention wall, that is treated as "no more data", not
a failure (see _fetch_1m_history()). Needs a fresh Fyers auth token.

Usage
─────
    python scripts/backtest_goodnight_scalper.py
    python scripts/backtest_goodnight_scalper.py --out docs/GOODNIGHT_SCALPER_RESULTS.md
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import _load_universe, load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics, BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers import get_broker  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.goodnight_scalper.costs import clean_trade_cost, stressed_trade_cost  # noqa: E402
from core.goodnight_scalper.premium import (  # noqa: E402
    REALIZED_VOL_LOOKBACK_DAYS,
    realized_volatility,
    reconstruct_trade,
)
from core.goodnight_scalper.signal import detect_entry  # noqa: E402
from core.orb_scalping.backtest import group_by_day  # noqa: E402
from core.orb_scalping.contract_selection import select_expiry  # noqa: E402
from core.options import fyers_symbol_master as sm  # noqa: E402
from scripts.validate_regime_classifier import fetch_chunked_daily  # noqa: E402

logger = logging.getLogger(__name__)

UNIVERSE_PATH = "agent/universe_nifty200momentum30.txt"
# Methodology doc's universe section: 10 independent readings, all >70%
# round-trip spread -- a confirmed, not hypothetical, illiquid name.
EXCLUDED_SYMBOLS = {"SAIL"}

MAX_LOOKBACK_CALENDAR_DAYS = 72     # feasibility probe confirmed >=70 days; small margin
VOL_BUFFER_CALENDAR_DAYS = 45       # comfortably >=20 TRADING days before window start
DTE_FLOOR_DAYS = 2                  # methodology doc's stated floor

SESSION_WINDOW_START_UTC = time(3, 45)   # 09:15 IST
SESSION_WINDOW_END_UTC = time(4, 1)      # 09:31 IST -- one candle past the 09:30 flatten

ONE_MIN_CHUNK_DAYS = 15   # conservative, disclosed guess -- see module docstring
DAILY_CHUNK_DAYS = 300
REQUEST_TIMEOUT_SECS = 30.0
SLEEP_BETWEEN_CALLS_SECS = 2.0     # tuned for Fyers' tight rate limit, same as the feasibility probe
MAX_RETRIES = 4
RETRY_BASE_WAIT_SECS = 6.0


# ─── Fetch layer ────────────────────────────────────────────────────────

async def _fetch_1m_history(broker, symbol: str, from_date: datetime, to_date: datetime,
                             sem: asyncio.Semaphore) -> list[OHLCV]:
    """Chunked 1-minute fetch. A chunk past Fyers' retention wall returns
    empty or raises -- both are logged and treated as "no more history
    that far back", not a fatal error, since the methodology doc's window
    is deliberately "whatever the real fetch confirms", not a hardcoded
    assumption."""
    loop = asyncio.get_event_loop()
    all_candles: list[OHLCV] = []
    chunk_start = from_date
    while chunk_start < to_date:
        chunk_end = min(chunk_start + timedelta(days=ONE_MIN_CHUNK_DAYS), to_date)
        for attempt in range(MAX_RETRIES):
            async with sem:
                try:
                    candles = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda cs=chunk_start, ce=chunk_end: broker.get_historical_data(symbol, "1m", cs, ce),
                        ),
                        timeout=REQUEST_TIMEOUT_SECS,
                    )
                    await asyncio.sleep(SLEEP_BETWEEN_CALLS_SECS)
                    all_candles.extend(candles)
                    break
                except asyncio.TimeoutError:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BASE_WAIT_SECS * (attempt + 1))
                        continue
                    logger.warning("%s: 1m chunk %s..%s timed out, treating as no data", symbol,
                                    chunk_start.date(), chunk_end.date())
                except Exception as e:
                    if "429" in str(e) and attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_BASE_WAIT_SECS * (attempt + 1))
                        continue
                    logger.info("%s: 1m chunk %s..%s unavailable (%s) -- treating as beyond retention wall",
                                symbol, chunk_start.date(), chunk_end.date(), e)
                    break
        chunk_start = chunk_end
    return all_candles


def _session_window(day_candles: list[OHLCV]) -> list[OHLCV]:
    return sorted(
        (c for c in day_candles if SESSION_WINDOW_START_UTC <= c.timestamp.time() < SESSION_WINDOW_END_UTC),
        key=lambda c: c.timestamp,
    )


def _infer_strike_interval(broker, underlying: str, expiry: date) -> float | None:
    """Minimum gap between consecutive listed strikes for `underlying` at
    `expiry`, from a single live option-chain fetch -- methodology doc's
    "measured per symbol, not assumed uniform" rule. Returns None if fewer
    than 2 distinct strikes are listed (can't infer an interval)."""
    expiry_epoch = sm.get_expiry_epoch(underlying, expiry)
    raw_chain = broker.get_option_chain(underlying, expiry_epoch)
    strikes = sorted({row.get("strike_price") for row in raw_chain.get("optionsChain", [])
                       if row.get("strike_price")})
    if len(strikes) < 2:
        return None
    gaps = [round(b - a, 2) for a, b in zip(strikes, strikes[1:]) if b > a]
    return min(gaps) if gaps else None


# ─── Trade construction ─────────────────────────────────────────────────

def _to_backtest_trade(entry_dt: datetime, exit_dt: datetime, entry_premium: float,
                        exit_premium: float, lot_size: int, trade_num: int,
                        bars_held: int, variant: str) -> BacktestTrade:
    profit = (exit_premium - entry_premium) * lot_size
    notional = entry_premium * lot_size
    profit_pct = (profit / notional * 100) if notional else 0.0

    if variant == "clean":
        costs = clean_trade_cost(entry_premium, exit_premium, lot_size, entry_dt.date()).total
    elif variant == "stressed":
        costs = stressed_trade_cost(entry_premium, exit_premium, lot_size, entry_dt.date()).total
    else:
        raise ValueError(f"unsupported variant: {variant!r}")

    return BacktestTrade(
        trade_num=trade_num, direction="Long", qty=lot_size,
        entry_date=entry_dt, entry_price=entry_premium,
        exit_date=exit_dt, exit_price=exit_premium,
        profit=profit, profit_pct=profit_pct, cum_profit=0.0,
        bars_held=bars_held, costs=costs,
    )


def run_symbol_backtest(symbol: str, one_min_candles: list[OHLCV], daily_candles: list[OHLCV],
                         strike_interval: float, lot_size: int, trading_days: list[date],
                         trade_num_start: int) -> tuple[list[BacktestTrade], list[BacktestTrade], list[dict]]:
    """Per-day simulation for ONE symbol. Returns (clean_trades,
    stressed_trades, trade_meta) -- trade_meta carries {symbol, setup} for
    the per-setup/per-symbol breakdowns the results doc reports
    (BacktestTrade itself has no room for either)."""
    by_day = group_by_day(one_min_candles)
    daily_sorted = sorted(daily_candles, key=lambda c: c.timestamp)

    clean_trades: list[BacktestTrade] = []
    stressed_trades: list[BacktestTrade] = []
    trade_meta: list[dict] = []
    trade_num = trade_num_start

    for day in trading_days:
        day_candles = by_day.get(day)
        if not day_candles:
            continue
        window = _session_window(day_candles)
        entry_signal = detect_entry(window)
        if entry_signal is None:
            continue

        prior_closes = [c.close for c in daily_sorted if c.timestamp.date() < day]
        needed = REALIZED_VOL_LOOKBACK_DAYS + 1
        if len(prior_closes) < needed:
            continue  # not enough vol history yet -- skipped, not approximated
        implied_vol = realized_volatility(prior_closes[-needed:])

        expiries = sm.list_expiries(symbol)
        expiry = select_expiry(expiries, day, DTE_FLOOR_DAYS)
        if expiry is None:
            continue

        trade = reconstruct_trade(symbol, entry_signal, window, strike_interval, expiry, implied_vol)

        trade_num += 1
        bars_held = int((trade.exit_timestamp - trade.entry_timestamp).total_seconds() // 60)
        common = dict(
            entry_dt=trade.entry_timestamp, exit_dt=trade.exit_timestamp,
            entry_premium=trade.entry_premium, exit_premium=trade.exit_premium,
            lot_size=lot_size, trade_num=trade_num, bars_held=bars_held,
        )
        clean_trades.append(_to_backtest_trade(**common, variant="clean"))
        stressed_trades.append(_to_backtest_trade(**common, variant="stressed"))
        trade_meta.append({"symbol": symbol, "setup": trade.setup, "direction": trade.direction,
                            "exit_reason": trade.exit_reason, "month": day.strftime("%Y-%m")})

    return clean_trades, stressed_trades, trade_meta


# ─── Report ──────────────────────────────────────────────────────────────

def _metrics_row(label: str, m: BacktestMetrics) -> str:
    return (f"| {label} | {m.total_trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | "
            f"{m.sharpe_ratio:.2f} | {m.net_profit_pct:+.1f}% | {m.max_drawdown_pct:.1f}% |")


def build_report(clean: list[BacktestTrade], stressed: list[BacktestTrade],
                  meta: list[dict], window_start: date, window_end: date,
                  universe_size: int, excluded: set) -> str:
    clean_m = _compute_metrics(clean)
    stressed_m = _compute_metrics(stressed)

    by_setup: dict[str, list[BacktestTrade]] = defaultdict(list)
    for t, m in zip(stressed, meta):
        by_setup[m["setup"]].append(t)

    by_symbol_count: dict[str, int] = defaultdict(int)
    for m in meta:
        by_symbol_count[m["symbol"]] += 1

    by_month: dict[str, list[BacktestTrade]] = defaultdict(list)
    for t, m in zip(stressed, meta):
        by_month[m["month"]].append(t)

    lines = [
        "# \"Good Night\" Scalper — Backtest Results (Candidate 20)",
        "",
        "Methodology: docs/GOODNIGHT_SCALPER_METHODOLOGY.md. Setup A + B, pooled "
        "(never split into separate gates) -- see the methodology doc for why.",
        "",
        f"Universe: {universe_size} symbols from {UNIVERSE_PATH} "
        f"({', '.join(sorted(excluded))} excluded — confirmed persistently illiquid).",
        f"Window: {window_start.isoformat()} to {window_end.isoformat()} "
        f"(re-verified at run time by the actual 1-minute fetch, not assumed).",
        "",
        "## Pooled (validation gate)",
        "",
        "| Variant | Trades | Win rate | Profit factor | Sharpe | Net P&L % | Max DD % |",
        "|---|---|---|---|---|---|---|",
        _metrics_row("Clean", clean_m),
        _metrics_row("Stressed (real measured spread)", stressed_m),
        "",
        f"**Verdict (gates on Stressed, per the pre-registered methodology doc)**: "
        f"{'PASS' if stressed_m.has_positive_edge else 'FAIL'} "
        f"(PF {stressed_m.profit_factor:.2f}, Sharpe {stressed_m.sharpe_ratio:.2f}, "
        f"bar is PF > 1.0 AND Sharpe > 0.5).",
        "",
        "## Per-setup breakdown (Stressed, supplementary — not a separate gate)",
        "",
        "| Setup | Trades | Win rate | Profit factor | Sharpe | Net P&L % |",
        "|---|---|---|---|---|---|",
    ]
    for setup in sorted(by_setup):
        sm_ = _compute_metrics(by_setup[setup])
        lines.append(f"| {setup} | {sm_.total_trades} | {sm_.win_rate:.1%} | "
                      f"{sm_.profit_factor:.2f} | {sm_.sharpe_ratio:.2f} | {sm_.net_profit_pct:+.1f}% |")

    lines += ["", "## Per-month breakdown (Stressed)", "",
              "| Month | Trades | Win rate | Profit factor | Sharpe | Net P&L % |",
              "|---|---|---|---|---|---|"]
    for month in sorted(by_month):
        mm = _compute_metrics(by_month[month])
        lines.append(f"| {month} | {mm.total_trades} | {mm.win_rate:.1%} | "
                      f"{mm.profit_factor:.2f} | {mm.sharpe_ratio:.2f} | {mm.net_profit_pct:+.1f}% |")

    lines += ["", "## Trade count by symbol (Stressed)", "",
              "| Symbol | Trades |", "|---|---|"]
    for symbol in sorted(by_symbol_count):
        lines.append(f"| {symbol} | {by_symbol_count[symbol]} |")

    return "\n".join(lines) + "\n"


# ─── Orchestration ───────────────────────────────────────────────────────

async def main_async(out_path: str) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = load_config("agent/config.yaml")
    broker = get_broker(config)
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    universe = [s for s in _load_universe(UNIVERSE_PATH) if s not in EXCLUDED_SYMBOLS]
    print(f"Universe: {len(universe)} symbols ({', '.join(sorted(EXCLUDED_SYMBOLS))} excluded)")

    today = datetime.now(timezone.utc)
    window_start = today - timedelta(days=MAX_LOOKBACK_CALENDAR_DAYS)
    daily_fetch_start = window_start - timedelta(days=VOL_BUFFER_CALENDAR_DAYS)

    sem = asyncio.Semaphore(1)   # sequential -- same tight-rate-limit lesson as the feasibility probe
    all_clean: list[BacktestTrade] = []
    all_stressed: list[BacktestTrade] = []
    all_meta: list[dict] = []
    earliest_seen, latest_seen = None, None

    for i, symbol in enumerate(universe, 1):
        print(f"[{i}/{len(universe)}] {symbol} ...")
        try:
            expiries = sm.list_expiries(symbol)
            nearest_expiry = select_expiry(expiries, today.date(), DTE_FLOOR_DAYS)
            lot_size = sm.get_lot_size(symbol)
            # The one live call per symbol not already behind _fetch_1m_history's/
            # fetch_chunked_daily's throttle -- explicit sleep either side so this
            # loop's per-symbol option-chain fetch doesn't hammer Fyers back-to-back
            # the way the feasibility probe's first run did before it was throttled.
            async with sem:
                strike_interval = _infer_strike_interval(broker, symbol, nearest_expiry) if nearest_expiry else None
                await asyncio.sleep(SLEEP_BETWEEN_CALLS_SECS)
            if strike_interval is None:
                print(f"  {symbol}: could not resolve a strike interval, skipping.")
                continue

            one_min = await _fetch_1m_history(broker, symbol, window_start, today, sem)
            daily = await fetch_chunked_daily(broker, symbol, daily_fetch_start, today, sem,
                                               delay=SLEEP_BETWEEN_CALLS_SECS)
            if not one_min:
                print(f"  {symbol}: no 1-minute history returned, skipping.")
                continue

            trading_days = sorted(group_by_day(one_min).keys())
            if trading_days:
                earliest_seen = min(earliest_seen, trading_days[0]) if earliest_seen else trading_days[0]
                latest_seen = max(latest_seen, trading_days[-1]) if latest_seen else trading_days[-1]

            clean, stressed, meta = run_symbol_backtest(
                symbol, one_min, daily, strike_interval, lot_size, trading_days,
                trade_num_start=len(all_clean),
            )
            all_clean.extend(clean)
            all_stressed.extend(stressed)
            all_meta.extend(meta)
            print(f"  {symbol}: {len(clean)} trades")
        except Exception as e:
            print(f"  {symbol}: failed ({e}) -- skipping, not counted as a zero-trade day.")
            continue

    print(f"\nTotal pooled trades: {len(all_stressed)}")
    report = build_report(all_clean, all_stressed, all_meta,
                           earliest_seen or window_start.date(), latest_seen or today.date(),
                           len(universe), EXCLUDED_SYMBOLS)
    Path(out_path).write_text(report, encoding="utf-8")
    print(f"Report written to {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/GOODNIGHT_SCALPER_RESULTS.md")
    args = parser.parse_args()
    return asyncio.run(main_async(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
