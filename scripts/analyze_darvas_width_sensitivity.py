#!/usr/bin/env python3
"""
QuantOS — Darvas Box-Width Sensitivity: unbiased forward-return gut-check
──────────────────────────────────────────────────────────────────────────
See docs/DARVAS_BOX_WIDTH_SENSITIVITY_METHODOLOGY.md for the full
pre-registration (systematic ~72-symbol sample, 2-year window, width
buckets, forward-return horizons — all pinned before this script ran).

Reuses core/darvas/weekly_discovery.py::analyse_symbol UNMODIFIED, called
with an explicit config override (`max_box_width=200.0`) so a box of any
width is classified instead of silently dropped — the module's own live
default (35%) is never touched. Walks each sampled symbol day-by-day,
records every FRESH BREAKOUT event regardless of width, and measures its
forward return at three fixed horizons with no same-day lookahead (entry
at the NEXT day's open).

Resumable per symbol (skips symbols already in the results file) and
backs off on a Fyers rate limit before retrying the SAME symbol, up to a
bounded total wait — this project's history (this module's own
WeeklyDiscoveryScanner docstring included) shows even a modest batch of
history requests can exhaust Fyers' quota.

Usage:
    python scripts/analyze_darvas_width_sensitivity.py
    python scripts/analyze_darvas_width_sensitivity.py --out docs/DARVAS_BOX_WIDTH_SENSITIVITY_RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main import load_config  # noqa: E402
from core.brokers.base import OHLCV  # noqa: E402
from core.darvas.weekly_discovery import DEFAULT_CONFIG, analyse_symbol  # noqa: E402

MIN_BARS = 60
WIDE_CFG = {**DEFAULT_CONFIG, "max_box_width": 200.0}
HORIZONS_DAYS = {"4w": 20, "8w": 40, "12w": 60}
MIN_SAMPLE_TO_REPORT = 10

WINDOWS = [
    (datetime(2024, 9, 22, tzinfo=timezone.utc), datetime(2025, 9, 21, tzinfo=timezone.utc)),
    (datetime(2025, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 22, tzinfo=timezone.utc)),
]

BUCKETS = (
    ("<=35% (control)", lambda w: w <= 35.0),
    ("35-50%", lambda w: 35.0 < w <= 50.0),
    ("50-100%", lambda w: 50.0 < w <= 100.0),
)
EXCLUDED_BUCKET = (">100% (not a real box, excluded from comparison)", lambda w: w > 100.0)


def sample_universe(universe_file: Path, stride: int = 7) -> list[str]:
    lines = [l.strip() for l in universe_file.read_text().splitlines() if l.strip()]
    return lines[::stride]


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


def fetch_daily(broker, symbol: str) -> list[OHLCV]:
    seen = {}
    for f, t in WINDOWS:
        for c in broker.get_historical_data(symbol, "1d", f, t):
            seen[c.timestamp.date()] = c
    return [seen[d] for d in sorted(seen)]


def find_breakouts(symbol: str, daily: list[OHLCV]) -> list[dict]:
    """Walks day-by-day, recording every FRESH BREAKOUT event (any width —
    the width filter is disabled via WIDE_CFG) with forward returns at the
    three pre-registered horizons. Entry is the NEXT day's open (no
    same-day lookahead); a breakout with no next-day bar yet is skipped."""
    events = []
    n = len(daily)
    for i in range(MIN_BARS, n):
        result = analyse_symbol(symbol, daily[: i + 1], cfg=WIDE_CFG)
        if result is None or result.status != "FRESH BREAKOUT":
            continue
        if i + 1 >= n:
            continue
        entry_price = daily[i + 1].open
        returns = {}
        for label, bars in HORIZONS_DAYS.items():
            target = i + 1 + bars
            if target < n:
                returns[label] = round((daily[target].close - entry_price) / entry_price * 100, 2)
        events.append({
            "symbol": symbol, "date": daily[i].timestamp.date().isoformat(),
            "width_pct": result.box_width_pct, "entry_price": entry_price, "returns": returns,
        })
    return events


def all_events(results: dict) -> list[dict]:
    out = []
    for sym_result in results.values():
        out.extend(sym_result.get("events", []))
    return out


def bucket_stats(events: list[dict], predicate, horizon: str) -> dict:
    vals = [e["returns"][horizon] for e in events if predicate(e["width_pct"]) and horizon in e["returns"]]
    n = len(vals)
    if n < MIN_SAMPLE_TO_REPORT:
        return {"n": n, "insufficient": True}
    return {
        "n": n, "insufficient": False,
        "mean_pct": round(statistics.mean(vals), 2),
        "median_pct": round(statistics.median(vals), 2),
        "hit_rate_pct": round(sum(1 for v in vals if v > 0) / n * 100, 1),
    }


def _row(label: str, stats: dict) -> str:
    if stats["insufficient"]:
        return f"| {label} | {stats['n']} | too few (<{MIN_SAMPLE_TO_REPORT}), not a read | | |"
    return (f"| {label} | {stats['n']} | {stats['mean_pct']:+.2f}% | "
           f"{stats['median_pct']:+.2f}% | {stats['hit_rate_pct']:.1f}% |")


def summarize(results: dict) -> str:
    events = all_events(results)
    errors = {sym: r["error"] for sym, r in results.items() if "error" in r}
    lines = [
        "# Darvas Box-Width Sensitivity — Results",
        "",
        "Methodology: docs/DARVAS_BOX_WIDTH_SENSITIVITY_METHODOLOGY.md, "
        "pre-registered 2026-09-22 before this ran. Gut-check only — raw "
        "forward returns, no costs, no stops. A favorable bucket here is "
        "grounds for a full cost-adjusted backtest, not a dashboard change "
        "on its own.",
        "",
        f"{len(results)} symbols attempted, {len(errors)} errored, "
        f"{len(events)} total FRESH BREAKOUT events found across all widths.",
        "",
    ]
    if errors:
        lines.append(f"Errored symbols (excluded from the analysis): {', '.join(sorted(errors))}")
        lines.append("")

    for horizon in HORIZONS_DAYS:
        lines += [f"## Forward return at {horizon}", "",
                 "| Width bucket | n | Mean | Median | Hit rate |",
                 "|---|---|---|---|---|"]
        for label, pred in BUCKETS:
            lines.append(_row(label, bucket_stats(events, pred, horizon)))
        lines.append(_row(EXCLUDED_BUCKET[0], bucket_stats(events, EXCLUDED_BUCKET[1], horizon)))
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--universe", default="agent/universe_nifty500.txt")
    parser.add_argument("--out", default="docs/DARVAS_BOX_WIDTH_SENSITIVITY_RESULTS.md")
    parser.add_argument("--results-cache", default=str(Path.home() / ".quantos" / "darvas_width_sensitivity_results.json"))
    parser.add_argument("--max-wait-seconds", type=int, default=4 * 3600)
    args = parser.parse_args()

    config = load_config(args.config)
    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')} ...")
    if not broker.connect():
        print("ERROR: broker connect() failed -- check the Fyers token.")
        return 1

    symbols = sample_universe(Path(args.universe))
    print(f"{len(symbols)} symbols in the systematic sample (every 7th name)")

    results_path = Path(args.results_cache)
    results = load_results(results_path)
    waited = 0

    for sym in symbols:
        if sym in results:
            print(f"{sym}: already have a result ({len(results[sym].get('events', []))} events), skipping")
            continue
        while True:
            try:
                daily = fetch_daily(broker, sym)
                if len(daily) < MIN_BARS:
                    results[sym] = {"error": "insufficient data", "bars": len(daily)}
                else:
                    results[sym] = {"events": find_breakouts(sym, daily)}
                save_results(results_path, results)
                print(f"{sym}: {len(results[sym].get('events', []))} breakout events")
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
