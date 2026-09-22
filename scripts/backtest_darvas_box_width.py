#!/usr/bin/env python3
"""
QuantOS — Darvas Box-Width Backtest: managed trade, cost-adjusted
────────────────────────────────────────────────────────────────
See docs/DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md for the full
pre-registration (all of the below was fixed BEFORE this script was run):

  - Full point-in-time Nifty 500 universe (core/rotation/
    nifty500_reconstitution.py — the same fix S8-3's survivorship-bias
    correction uses, not today's list applied retroactively).
  - 3-year window (2023-09-22 to 2026-09-22), time-based 80/20
    mining/holdout split at 2026-02-15.
  - core/darvas/weekly_discovery.py::analyse_symbol, unmodified, called
    with max_box_width=200.0 so every width is classified. Same three
    width buckets as the gut-check (docs/DARVAS_BOX_WIDTH_SENSITIVITY_*).
  - The managed trade uses fields analyse_symbol ALREADY computes for the
    breakout: stop = result.sl_price, target = result.mm_target. A
    same-day double-touch resolves to the stop. A 60-trading-day time-stop
    force-closes anything still open. A trade still open when the fetched
    window itself ends is excluded from metrics (incomplete outcome).
  - Cost model: scripts/backtest_rs_momentum.py's DELIVERY_COST_MODEL,
    imported unmodified, plus a Stressed variant (+15bps/leg, matching
    candidate 18's own stress convention). Stressed gates the verdict.
  - Minimum sample size to report a bucket/split combination: 30 trades
    (this project's standard bar, not the gut-check's lowered 10).

Resumable per symbol (skips symbols already in the results cache) and
backs off 10 minutes on a Fyers rate limit before retrying the SAME
symbol, same pattern as scripts/analyze_darvas_width_sensitivity.py — a
full-universe, 3-window pull is a large request count and this is
expected to span a long runtime.

Usage:
    python scripts/backtest_darvas_box_width.py
    python scripts/backtest_darvas_box_width.py --out docs/DARVAS_BOX_WIDTH_BACKTEST_RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.backtest.parser import BacktestMetrics, BacktestTrade, _compute_metrics  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.darvas.weekly_discovery import DEFAULT_CONFIG, analyse_symbol  # noqa: E402
from core.risk.costs import CostModel  # noqa: E402
from core.rotation.nifty500_reconstitution import (  # noqa: E402
    build_point_in_time_universe, eligible_symbols_asof,
)
from scripts.backtest_rs_momentum import DELIVERY_COST_MODEL  # noqa: E402

MIN_BARS = 60
WIDE_CFG = {**DEFAULT_CONFIG, "max_box_width": 200.0}
MAX_HOLD_DAYS = 60          # 12 weeks time-stop -- the gut-check's own longest horizon
NOTIONAL_PER_TRADE = 100_000.0
MIN_SAMPLE_TO_REPORT = 30   # this project's standard bar (ORB_CONDITION_MINING_METHODOLOGY.md)

STRESSED_COST_MODEL = CostModel(
    brokerage_pct=DELIVERY_COST_MODEL.brokerage_pct, brokerage_flat=DELIVERY_COST_MODEL.brokerage_flat,
    stt_pct=DELIVERY_COST_MODEL.stt_pct, exchange_txn_pct=DELIVERY_COST_MODEL.exchange_txn_pct,
    sebi_pct=DELIVERY_COST_MODEL.sebi_pct, stamp_pct=DELIVERY_COST_MODEL.stamp_pct,
    gst_pct=DELIVERY_COST_MODEL.gst_pct, slippage_bps=DELIVERY_COST_MODEL.slippage_bps + 15.0,
)

WINDOW_START = datetime(2023, 9, 22, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 22, tzinfo=timezone.utc)
MINING_HOLDOUT_SPLIT = datetime(2026, 2, 15, tzinfo=timezone.utc)

# 3 <366-day chunks spanning WINDOW_START..WINDOW_END (Fyers' daily-resolution cap).
WINDOWS = [
    (datetime(2023, 9, 22, tzinfo=timezone.utc), datetime(2024, 9, 21, tzinfo=timezone.utc)),
    (datetime(2024, 9, 21, tzinfo=timezone.utc), datetime(2025, 9, 21, tzinfo=timezone.utc)),
    (datetime(2025, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 22, tzinfo=timezone.utc)),
]

BUCKETS = (
    ("<=35% (control)", lambda w: w <= 35.0),
    ("35-50%", lambda w: 35.0 < w <= 50.0),
    ("50-100%", lambda w: 50.0 < w <= 100.0),
)


# ─── Universe (point-in-time, per DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md) ────

def load_current_universe(universe_file: Path) -> frozenset:
    return frozenset(
        ln.strip() for ln in universe_file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    )


# ─── Fetch (resumable, 10-min rate-limit backoff) ──────────────────────────────

def fetch_daily(broker, symbol: str) -> list[OHLCV]:
    seen = {}
    for f, t in WINDOWS:
        for c in broker.get_historical_data(symbol, "1d", f, t):
            seen[c.timestamp.date()] = c
    return [seen[d] for d in sorted(seen)]


# ─── Managed trade simulation ───────────────────────────────────────────────────

def _simulate_exit(daily: list[OHLCV], entry_idx: int, sl_price: float, mm_target: float) -> tuple:
    """Walk forward from entry_idx (inclusive), checking each day's low against
    the stop and high against the target. A same-day double-touch resolves to
    the stop (conservative, pre-registered). Returns (exit_idx, exit_price,
    reason) where reason is one of stop/target/time-stop/data-ended."""
    n = len(daily)
    last_idx = min(entry_idx + MAX_HOLD_DAYS - 1, n - 1)
    for j in range(entry_idx, last_idx + 1):
        bar = daily[j]
        if bar.low <= sl_price:
            return j, sl_price, "stop"
        if bar.high >= mm_target:
            return j, mm_target, "target"
    if last_idx == entry_idx + MAX_HOLD_DAYS - 1:
        return last_idx, daily[last_idx].close, "time-stop"
    return last_idx, daily[last_idx].close, "data-ended"


def find_trades(symbol: str, daily: list[OHLCV], snapshots) -> list[dict]:
    """Walks day-by-day, recording every FRESH BREAKOUT event (any width) that
    was an actual Nifty 500 constituent on its breakout date, then simulates
    the managed trade (stop/target/time-stop) that follows it."""
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
        exit_idx, exit_price, reason = _simulate_exit(
            daily, entry_idx, result.sl_price, result.mm_target,
        )
        trades.append({
            "symbol": symbol, "breakout_date": breakout_date.isoformat(),
            "width_pct": result.box_width_pct,
            "entry_date": entry_date.isoformat(), "entry_price": entry_price,
            "exit_date": daily[exit_idx].timestamp.isoformat(), "exit_price": exit_price,
            "reason": reason,
        })
    return trades


# ─── Trade construction / metrics (reuses core/backtest/parser.py unmodified) ──

def _make_trade(num: int, raw: dict, cost_model: CostModel) -> BacktestTrade:
    entry_price, exit_price = raw["entry_price"], raw["exit_price"]
    entry_date = datetime.fromisoformat(raw["entry_date"])
    exit_date = datetime.fromisoformat(raw["exit_date"])
    qty = max(1, round(NOTIONAL_PER_TRADE / entry_price))
    profit = (exit_price - entry_price) * qty
    profit_pct = (exit_price - entry_price) / entry_price * 100 if entry_price else 0.0
    costs = cost_model.cost_of(entry_price, exit_price, qty, "BUY")
    bars_held = max(1, (exit_date - entry_date).days)
    return BacktestTrade(
        trade_num=num, direction="Long", qty=qty,
        entry_date=entry_date, entry_price=entry_price,
        exit_date=exit_date, exit_price=exit_price,
        profit=profit, profit_pct=profit_pct, cum_profit=0.0,
        bars_held=bars_held, costs=costs,
    )


def all_trades(results: dict) -> list[dict]:
    out = []
    for sym_result in results.values():
        out.extend(sym_result.get("trades", []))
    return out


def _split(trades: list[dict], predicate, before_split: bool) -> list[dict]:
    matched = [t for t in trades if predicate(t["width_pct"]) and t["reason"] != "data-ended"]
    cutoff = MINING_HOLDOUT_SPLIT.isoformat()
    if before_split:
        return [t for t in matched if t["breakout_date"] < cutoff]
    return [t for t in matched if t["breakout_date"] >= cutoff]


def _metrics(trades: list[dict], cost_model: CostModel) -> Optional[BacktestMetrics]:
    if len(trades) < MIN_SAMPLE_TO_REPORT:
        return None
    bt_trades = [_make_trade(n, raw, cost_model) for n, raw in enumerate(trades, 1)]
    return _compute_metrics(bt_trades)


def _row(label: str, n_raw: int, m: Optional[BacktestMetrics]) -> str:
    if m is None:
        return f"| {label} | {n_raw} | too few (<{MIN_SAMPLE_TO_REPORT}), not a read | | | | |"
    return (f"| {label} | {m.total_trades} | {m.win_rate:.1%} | {m.profit_factor:.2f} | "
            f"{m.sharpe_ratio:.2f} | {m.net_profit_pct:+.1f}% | {m.avg_bars_held:.0f}d |")


def _passes(m: Optional[BacktestMetrics]) -> bool:
    return m is not None and m.has_positive_edge


# ─── Report ─────────────────────────────────────────────────────────────────────

def summarize(results: dict) -> str:
    events = all_trades(results)
    data_ended = [t for t in events if t["reason"] == "data-ended"]
    errors = {sym: r["error"] for sym, r in results.items() if "error" in r}

    lines = [
        "# Darvas Box-Width Backtest — Results",
        "",
        "Methodology: docs/DARVAS_BOX_WIDTH_BACKTEST_METHODOLOGY.md, "
        "pre-registered 2026-09-22 before this ran. Managed trade (real "
        "stop/target from analyse_symbol, delivery-style costs, Clean + "
        "Stressed), full point-in-time Nifty 500 universe, time-based 80/20 "
        "mining/holdout split at 2026-02-15. Stressed gates the verdict.",
        "",
        f"{len(results)} symbols attempted, {len(errors)} errored, "
        f"{len(events)} total FRESH BREAKOUT events found (any width, "
        f"point-in-time-eligible), {len(data_ended)} still open at the "
        f"fetch window's end (excluded from all metrics below).",
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

    # ── Verdict, per the pre-registered rule ────────────────────────────────
    bucket_a = bucket_metrics["<=35% (control)"]
    bucket_b = bucket_metrics["35-50%"]
    cond1 = _passes(bucket_b["mining_stressed"])
    cond2 = _passes(bucket_b["holdout_stressed"])
    cond3 = not _passes(bucket_a["holdout_stressed"])
    all_pass = cond1 and cond2 and cond3

    if bucket_b["holdout_stressed"] is None:
        verdict = "INCONCLUSIVE -- Bucket B's holdout sample is below the 30-trade minimum."
    elif all_pass:
        verdict = "CLEARS ITS BAR -- a dashboard change is warranted per the pre-registered rule."
    else:
        verdict = "DOES NOT CLEAR ITS BAR -- no dashboard change is warranted."

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


# ─── Cache I/O ──────────────────────────────────────────────────────────────────

def load_results(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_results(path: Path, results: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2))


# ─── Orchestration ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--out", default="docs/DARVAS_BOX_WIDTH_BACKTEST_RESULTS.md")
    parser.add_argument("--results-cache", default=str(Path.home() / ".quantos" / "darvas_width_backtest_results.json"))
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
                    results[sym] = {"trades": find_trades(sym, daily, snapshots)}
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
