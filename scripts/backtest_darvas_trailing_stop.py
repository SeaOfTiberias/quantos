#!/usr/bin/env python3
"""
QuantOS — Darvas Trailing-Stop Backtest (single-variable follow-up)
────────────────────────────────────────────────────────────────
See docs/DARVAS_TRAILING_STOP_BACKTEST_METHODOLOGY.md for the full
pre-registration. This is a minimal-diff variant of
scripts/backtest_darvas_box_width.py — same universe, window, signal,
width buckets, cost model, mining/holdout split, minimum sample size, and
verdict structure, imported directly from that module wherever unchanged
so nothing can silently drift between the two runs. The ONLY difference:

  - The static stop/target (fixed at the entry box's values) is replaced
    by a trailing one: each day, if analyse_symbol reports a NEW,
    higher-ceiling box, both the stop (its sl_price) and target (its
    mm_target) are raised to match (never lowered). Same algorithm as
    entry detection (weekly_discovery.py), not core/darvas/box.py's
    next_trailing_stop() -- that function calls a differently-parameterized
    box detector (8% max width) built for the Stage-B intraday scanner and
    would silently swap in a different signal; ruled out explicitly (see
    the methodology doc).
  - No fixed 60-day time-stop -- trailing is meant to let a real trend run.
  - A trade still open when the fetch window ends is marked-to-market at
    the last close and INCLUDED in metrics (the box-width backtest
    excluded these as incomplete; here that would systematically discard
    the still-running winners this variant exists to capture).

Usage:
    python scripts/backtest_darvas_trailing_stop.py
    python scripts/backtest_darvas_trailing_stop.py --out docs/DARVAS_TRAILING_STOP_BACKTEST_RESULTS.md
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.darvas.weekly_discovery import analyse_symbol  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402
from core.rotation.nifty500_reconstitution import (  # noqa: E402
    build_point_in_time_universe, eligible_symbols_asof,
)
from scripts.backtest_darvas_box_width import (  # noqa: E402
    BUCKETS, DELIVERY_COST_MODEL, MIN_BARS, MIN_SAMPLE_TO_REPORT,
    MINING_HOLDOUT_SPLIT, STRESSED_COST_MODEL, WIDE_CFG, WINDOW_START,
    _make_trade, _metrics, _passes, _row, fetch_daily, load_current_universe,
    load_results, save_results,
)

OUT_DEFAULT = "docs/DARVAS_TRAILING_STOP_BACKTEST_RESULTS.md"
CACHE_DEFAULT = str(Path.home() / ".quantos" / "darvas_trailing_stop_results.json")


# ─── Managed trade simulation (trailing) ────────────────────────────────────────

def _simulate_exit_trailing(symbol: str, daily: list[OHLCV], entry_idx: int,
                             sl_price: float, mm_target: float, seen_ceiling: float) -> tuple:
    """Same day-by-day walk as the static-exit backtest, but re-evaluates
    analyse_symbol once per day and raises both the stop and target if a
    new, higher box has confirmed. No time-stop -- runs to a stop/target
    hit or the fetch window's end (marked-to-market, reason 'still-open')."""
    n = len(daily)
    stop, target = sl_price, mm_target
    for j in range(entry_idx, n):
        bar = daily[j]
        if bar.low <= stop:
            return j, stop, "stop"
        if bar.high >= target:
            return j, target, "target"
        result = analyse_symbol(symbol, daily[: j + 1], cfg=WIDE_CFG)
        if (result and result.box_ceiling and result.box_ceiling > seen_ceiling
                and result.sl_price and result.sl_price > stop):
            stop = result.sl_price
            seen_ceiling = result.box_ceiling
            if result.mm_target and result.mm_target > target:
                target = result.mm_target
    return n - 1, daily[n - 1].close, "still-open"


def find_trailing_trades(symbol: str, daily: list[OHLCV], snapshots) -> list[dict]:
    """Same entry detection as scripts/backtest_darvas_box_width.py's
    find_trades -- identical FRESH BREAKOUT / point-in-time-eligibility
    logic -- with the trailing exit simulation substituted in."""
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
        exit_idx, exit_price, reason = _simulate_exit_trailing(
            symbol, daily, entry_idx, result.sl_price, result.mm_target, result.box_ceiling,
        )
        trades.append({
            "symbol": symbol, "breakout_date": breakout_date.isoformat(),
            "width_pct": result.box_width_pct,
            "entry_date": entry_date.isoformat(), "entry_price": entry_price,
            "exit_date": daily[exit_idx].timestamp.isoformat(), "exit_price": exit_price,
            "reason": reason,
        })
    return trades


def all_trades(results: dict) -> list[dict]:
    out = []
    for sym_result in results.values():
        out.extend(sym_result.get("trades", []))
    return out


def _split(trades: list[dict], predicate, before_split: bool) -> list[dict]:
    """Unlike the static-exit backtest, 'still-open' trades are NOT excluded
    here -- see the methodology doc for why (excluding them would discard
    exactly the still-running winners this variant is meant to capture)."""
    matched = [t for t in trades if predicate(t["width_pct"])]
    cutoff = MINING_HOLDOUT_SPLIT.isoformat()
    if before_split:
        return [t for t in matched if t["breakout_date"] < cutoff]
    return [t for t in matched if t["breakout_date"] >= cutoff]


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
        "# Darvas Trailing-Stop Backtest — Results",
        "",
        "Methodology: docs/DARVAS_TRAILING_STOP_BACKTEST_METHODOLOGY.md, "
        "pre-registered 2026-09-22 before this ran. Single-variable "
        "follow-up to docs/DARVAS_BOX_WIDTH_BACKTEST_RESULTS.md -- same "
        "universe/window/buckets/costs/split, only the exit rule differs "
        "(trailing stop+target, no time-stop, still-open trades "
        "marked-to-market and INCLUDED rather than excluded).",
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
        verdict = "CLEARS ITS BAR -- trailing recovers an edge the static-exit backtest didn't find."
    else:
        verdict = "DOES NOT CLEAR ITS BAR -- trailing the stop/target does not rescue this."

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
                    results[sym] = {"trades": find_trailing_trades(sym, daily, snapshots)}
                save_results(results_path, results)
                print(f"[{n}/{len(fetch_universe)}] {sym}: "
                      f"{len(results[sym].get('trades', []))} trades")
                break
            except Exception as e:
                msg = str(e)
                if ("429" in msg or "request limit" in msg) and waited < args.max_wait_seconds:
                    print(f"{sym}: rate limited, waiting 10 min "
                          f"(total waited so far: {waited // 60} min)...")
                    time.sleep(600)
                    waited += 600
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
