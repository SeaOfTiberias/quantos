#!/usr/bin/env python3
"""
QuantOS — Stage A Discovery Diagnostic
─────────────────────────────────────────
Standalone, read-only tool to see *why* the discovery scan produced the
candidate count it did — per-symbol status breakdown (fetch errors,
insufficient history, filtered-too-wide boxes, BOX FORMING/APPROACHING/
WATCHING/FRESH BREAKOUT), not just the final "N candidates" summary that
agent/main.py logs.

Doesn't touch ~/.quantos/discovery_watchlist.json, doesn't sync to the
cloud, doesn't place orders — pure market-data reads via the broker
already configured in agent/config.yaml.

Usage:
    python agent/debug_discovery_scan.py
    python agent/debug_discovery_scan.py --symbols RELIANCE,TCS,INFY
    python agent/debug_discovery_scan.py --config agent/config.yaml
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.main import load_config, _load_universe
from core.darvas.weekly_discovery import analyse_symbol, DEFAULT_CONFIG


def main():
    parser = argparse.ArgumentParser(description="Diagnose Stage A discovery scan results")
    parser.add_argument("--config", default="agent/config.yaml")
    parser.add_argument("--symbols", default=None,
                         help="Comma-separated override; default = universe_file from config")
    parser.add_argument("--universe-file", default=None)
    args = parser.parse_args()

    config = load_config(args.config)

    from core.brokers import get_broker
    broker = get_broker(config)
    print(f"Connecting to broker: {config.get('broker')}")
    broker.connect()
    print(f"Broker connected: {broker}\n")

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        universe_path = (args.universe_file
                          or config.get("scanner", {}).get("universe_file", "agent/universe.txt"))
        symbols = _load_universe(universe_path)
        print(f"Universe file: {universe_path}")

    print(f"Scanning {len(symbols)} symbols (sequential, no throttle — this is a debug run)...\n")

    status_counts = Counter()
    rows = []
    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=DEFAULT_CONFIG["history_days"])

    for i, symbol in enumerate(symbols, 1):
        print(f"  [{i}/{len(symbols)}] {symbol}" + " " * 20, end="\r")
        try:
            candles = broker.get_historical_data(symbol, "1d", from_date, to_date)
        except Exception as e:
            status_counts["FETCH_ERROR"] += 1
            rows.append((symbol, "FETCH_ERROR", str(e)[:70]))
            continue

        if len(candles) < 60:
            status_counts["INSUFFICIENT_CANDLES"] += 1
            rows.append((symbol, "INSUFFICIENT_CANDLES", f"only {len(candles)} candles returned"))
            continue

        result = analyse_symbol(symbol, candles)
        if result is None:
            status_counts["FILTERED (too wide / not enough weekly bars)"] += 1
            rows.append((symbol, "FILTERED", f"{len(candles)} daily candles were not enough weekly bars, or box > max_box_width"))
            continue

        status_counts[result.status] += 1
        rows.append((
            symbol, result.status,
            f"tier={result.alert_tier or '-'} ceiling={result.box_ceiling} "
            f"dist_to_ceil={result.dist_to_ceil} rr={result.rr_ratio}"
        ))

    print(" " * 60)
    print("\n── Status breakdown ──────────────────────────────")
    for status, count in status_counts.most_common():
        print(f"  {status:<45} {count}")

    print("\n── Everything except BOX FORMING / INSUFFICIENT_CANDLES ──")
    interesting = [r for r in rows if r[1] not in ("BOX FORMING", "INSUFFICIENT_CANDLES")]
    if not interesting:
        print("  (none — every symbol was either still forming a box or had too little history)")
    for symbol, status, detail in interesting:
        print(f"  {symbol:<15} {status:<12} {detail}")


if __name__ == "__main__":
    main()
