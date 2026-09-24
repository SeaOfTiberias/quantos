#!/usr/bin/env python3
"""
QuantOS — Darvas ATR-Scaled Stop Backtest (single-variable follow-up)
────────────────────────────────────────────────────────────────
See docs/DARVAS_ATR_STOP_BACKTEST_METHODOLOGY.md for the full
pre-registration. Third link in an explicit chain: box-width (static
exit, FAILED) -> trailing stop/target (improved every cell, FAILED --
Bucket B mining exactly breakeven) -> this script. Imports shared
helpers directly from scripts/backtest_darvas_box_width.py and
scripts/backtest_darvas_trailing_stop.py so nothing can silently diverge
from the two prior runs. The ONLY difference from the trailing-stop
backtest: the stop buffer (entry stop AND every subsequent trailed stop)
is `2.0 * ATR(14)` below the governing box's ceiling, instead of the
fixed `sl_ceil_buffer_pct = 2.0%` `analyse_symbol` uses by default. ATR
is recomputed at each trail point (not frozen at entry). The target
(measured move) is untouched -- this isolates the stop distance only.

Motivated by a measured pattern: 87-90% of trades in both prior backtests
exit via stop, and WELCORP's real trailing exit was IDENTICAL to its
static exit (-5.2% in 17 days) because trailing never touches the
INITIAL stop distance, which is fixed regardless of the stock's own
volatility.

Usage:
    python scripts/backtest_darvas_atr_stop.py
    python scripts/backtest_darvas_atr_stop.py --out docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.darvas.weekly_discovery import _atr, analyse_symbol  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402
from core.rotation.nifty500_reconstitution import (  # noqa: E402
    build_point_in_time_universe, eligible_symbols_asof,
)
from scripts.backtest_darvas_box_width import (  # noqa: E402
    BUCKETS, DELIVERY_COST_MODEL, MIN_BARS, MIN_SAMPLE_TO_REPORT,
    STRESSED_COST_MODEL, WIDE_CFG, WINDOW_START,
    _make_trade, _metrics, _passes, _row, fetch_daily, load_current_universe,
    load_results, save_results,
)
from scripts.backtest_darvas_trailing_stop import _split, all_trades  # noqa: E402

OUT_DEFAULT = "docs/DARVAS_ATR_STOP_BACKTEST_RESULTS.md"
CACHE_DEFAULT = str(Path.home() / ".quantos" / "darvas_atr_stop_results.json")

ATR_MULTIPLIER = 2.0   # single pre-registered value -- the Chandelier-exit convention
ATR_PERIOD = 14


# ─── Managed trade simulation (ATR-scaled trailing stop) ───────────────────────

def _stop_from_atr(daily: list[OHLCV], as_of_idx: int, box_ceiling: float) -> float:
    atr14 = _atr(daily[: as_of_idx + 1], ATR_PERIOD)
    return box_ceiling - ATR_MULTIPLIER * atr14


def _simulate_exit_atr(symbol: str, daily: list[OHLCV], entry_idx: int,
                        stop: float, target: float, seen_ceiling: float) -> tuple:
    """Same day-by-day trailing walk as the trailing-stop backtest, but the
    stop is recomputed via ATR (not analyse_symbol's fixed sl_price) both at
    entry and at every subsequent trail point. Target still trails via
    analyse_symbol's own mm_target, unchanged."""
    n = len(daily)
    for j in range(entry_idx, n):
        bar = daily[j]
        if bar.low <= stop:
            return j, stop, "stop"
        if bar.high >= target:
            return j, target, "target"
        result = analyse_symbol(symbol, daily[: j + 1], cfg=WIDE_CFG)
        if result and result.box_ceiling and result.box_ceiling > seen_ceiling:
            new_stop = _stop_from_atr(daily, j, result.box_ceiling)
            if new_stop > stop:
                stop = new_stop
                seen_ceiling = result.box_ceiling
                if result.mm_target and result.mm_target > target:
                    target = result.mm_target
    return n - 1, daily[n - 1].close, "still-open"


def find_atr_trades(symbol: str, daily: list[OHLCV], snapshots) -> list[dict]:
    """Same entry detection as the box-width/trailing-stop backtests --
    identical FRESH BREAKOUT / point-in-time-eligibility logic -- with the
    ATR-scaled trailing exit substituted in."""
    trades = []
    n = len(daily)
    for i in range(MIN_BARS, n):
        result = analyse_symbol(symbol, daily[: i + 1], cfg=WIDE_CFG)
        if result is None or result.status != "FRESH BREAKOUT":
            continue
        if i + 1 >= n:
            continue
        breakout_date = daily[i].timestamp
        if symbol not in eligible_symbols_asof(snapshots, breakout_date):
            continue

        entry_idx = i + 1
        entry_date, entry_price = daily[entry_idx].timestamp, daily[entry_idx].open
        initial_stop = _stop_from_atr(daily, i, result.box_ceiling)
        exit_idx, exit_price, reason = _simulate_exit_atr(
            symbol, daily, entry_idx, initial_stop, result.mm_target, result.box_ceiling,
        )
        trades.append({
            "symbol": symbol, "breakout_date": breakout_date.isoformat(),
            "width_pct": result.box_width_pct,
            "entry_date": entry_date.isoformat(), "entry_price": entry_price,
            "exit_date": daily[exit_idx].timestamp.isoformat(), "exit_price": exit_price,
            "reason": reason,
        })
    return trades


# ─── Report ─────────────────────────────────────────────────────────────────────

def summarize(results: dict) -> str:
    events = all_trades(results)
    still_open = [t for t in events if t["reason"] == "still-open"]
    still_open_pnl_pct = (
        sum((t["exit_price"] - t["entry_price"]) / t["entry_price"] for t in still_open) / len(still_open) * 100
        if still_open else 0.0
    )
    errors = {sym: r["error"] for sym, r in results.items() if "error" in r}

    lines = [
        "# Darvas ATR-Scaled Stop Backtest — Results",
        "",
        "Methodology: docs/DARVAS_ATR_STOP_BACKTEST_METHODOLOGY.md, "
        "pre-registered 2026-09-23 before this ran. Third link in the chain: "
        "box-width (static exit) -> trailing stop/target -> this run "
        "(same trailing logic, stop buffer is 2.0x ATR(14) instead of a "
        "fixed 2% below the ceiling; target unchanged).",
        "",
        f"{len(results)} symbols attempted, {len(errors)} errored, "
        f"{len(events)} total FRESH BREAKOUT events found (any width, "
        f"point-in-time-eligible). {len(still_open)} still open at the "
        f"fetch window's end, marked-to-market, average unrealized "
        f"{still_open_pnl_pct:+.1f}% (included in the metrics below, not excluded).",
        "",
    ]
    if errors:
        lines.append(f"Errored symbols (excluded): {', '.join(sorted(errors))}")
        lines.append("")

    bucket_metrics: dict[str, dict] = {}
    for label, pred in BUCKETS:
        lines += [f"## Bucket: {label}", ""]
        mining = _split(events, pred, before_split=True)
        holdout = _split(events, pred, before_split=False)
        lines += [
            "| Split / variant | Trades | Win rate | Profit factor | Sharpe | Net P&L% | Avg hold |",
            "|---|---|---|---|---|---|---|",
        ]
        m_clean = _metrics(mining, DELIVERY_COST_MODEL)
        m_stressed = _metrics(mining, STRESSED_COST_MODEL)
        h_clean = _metrics(holdout, DELIVERY_COST_MODEL)
        h_stressed = _metrics(holdout, STRESSED_COST_MODEL)
        lines.append(_row("Mining -- Clean", len(mining), m_clean))
        lines.append(_row("Mining -- Stressed", len(mining), m_stressed))
        lines.append(_row("Holdout -- Clean", len(holdout), h_clean))
        lines.append(_row("Holdout -- Stressed", len(holdout), h_stressed))
        lines.append("")
        bucket_metrics[label] = {"mining_stressed": m_stressed, "holdout_stressed": h_stressed}

    bucket_a = bucket_metrics["<=35% (control)"]
    bucket_b = bucket_metrics["35-50%"]
    cond1 = _passes(bucket_b["mining_stressed"])
    cond2 = _passes(bucket_b["holdout_stressed"])
    cond3 = not _passes(bucket_a["holdout_stressed"])
    all_pass = cond1 and cond2 and cond3

    if bucket_b["holdout_stressed"] is None:
        verdict = "INCONCLUSIVE -- Bucket B's holdout sample is below the 30-trade minimum."
    elif all_pass:
        verdict = "CLEARS ITS BAR -- ATR-scaled stop recovers the edge trailing alone didn't."
    else:
        verdict = "DOES NOT CLEAR ITS BAR."

    lines += [
        "## Verdict",
        "",
        f"1. Bucket B clears `has_positive_edge` on mining/Stressed: {'YES' if cond1 else 'NO'}",
        f"2. Bucket B clears `has_positive_edge` on holdout/Stressed: "
        f"{'YES' if cond2 else ('N/A -- too few holdout trades' if bucket_b['holdout_stressed'] is None else 'NO')}",
        f"3. Bucket A (control) does NOT clear `has_positive_edge` on holdout/Stressed: "
        f"{'YES' if cond3 else 'NO'}",
        "",
        f"**{verdict}**",
        "",
    ]
    return "\n".join(lines)


# ─── Orchestration ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--out", default=OUT_DEFAULT)
    parser.add_argument("--results-cache", default=CACHE_DEFAULT)
    parser.add_argument("--max-wait-seconds", type=int, default=8 * 3600)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of symbols fetched this run (for a quick sanity check)")
    args = parser.parse_args()

    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    current_universe = load_current_universe(Path(args.universe))
    snapshots = build_point_in_time_universe(current_universe, window_start=WINDOW_START)
    fetch_universe = sorted(frozenset().union(*(s.symbols for s in snapshots)))
    n_extra = len(fetch_universe) - len(current_universe)
    print(f"{len(fetch_universe)} symbols in the point-in-time fetch universe "
          f"({len(current_universe)} current + {n_extra} historical drops/joins)")
    if args.limit:
        fetch_universe = fetch_universe[: args.limit]
        print(f"--limit set: fetching only the first {len(fetch_universe)} symbols this run")

    results_path = Path(args.results_cache)
    results = load_results(results_path)
    waited = 0

    for n, sym in enumerate(fetch_universe, 1):
        if sym in results:
            continue
        while True:
            try:
                daily = fetch_daily(broker, sym)
                if len(daily) < MIN_BARS:
                    results[sym] = {"error": "insufficient data", "bars": len(daily)}
                else:
                    results[sym] = {"trades": find_atr_trades(sym, daily, snapshots)}
                save_results(results_path, results)
                print(f"[{n}/{len(fetch_universe)}] {sym}: "
                      f"{len(results[sym].get('trades', []))} trades")
                break
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "request limit" in msg or "Bad request" in msg) and waited < args.max_wait_seconds:
                    print(f"{sym}: rate limited / transient error, waiting 2 min "
                          f"(total waited so far: {waited // 60} min)...")
                    time.sleep(120)
                    waited += 120
                    continue
                results[sym] = {"error": msg}
                save_results(results_path, results)
                print(f"{sym}: giving up -- {msg}")
                break

    report = summarize(results)
    out_path = Path(args.out)
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
